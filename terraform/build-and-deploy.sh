#!/bin/bash
# Build and Deploy Script for DOCX Cleanser Lambda Container
# This script builds the Docker image, pushes it to ECR, and optionally updates the Lambda function

set -euo pipefail

# Configuration
AWS_REGION=${AWS_REGION:-"eu-west-2"}
AWS_PROFILE=${AWS_PROFILE:-"AdministratorAccess-626206937213"}
ENVIRONMENT=${ENVIRONMENT:-"production"}
REPOSITORY_NAME="document-cleanser-lambda"
IMAGE_TAG=${IMAGE_TAG:-"latest"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

# Help function
show_help() {
    cat << EOF
DOCX Cleanser Lambda Container Build & Deploy Script

Usage: $0 [OPTIONS] COMMAND

Commands:
    build           Build Docker image locally
    login           Login to ECR
    push            Build, tag, and push image to ECR
    deploy          Build, push, and update Lambda function
    validate        Run deployment validation after deploy

Options:
    -r, --region    AWS region (default: eu-west-2)
    -e, --env       Environment (default: production)
    -t, --tag       Image tag (default: latest)
    -h, --help      Show this help message

Examples:
    $0 build                    # Build image locally
    $0 push                     # Build and push to ECR
    $0 deploy                   # Full deployment pipeline
    $0 -t v1.2.3 deploy         # Deploy with specific tag

Environment Variables:
    AWS_REGION                  AWS region for deployment
    AWS_ACCOUNT_ID              AWS account ID (auto-detected if not set)
    ENVIRONMENT                 Deployment environment
    IMAGE_TAG                   Docker image tag

Prerequisites:
    - AWS CLI configured
    - Docker installed and running
    - Terraform applied (ECR repository exists)
    - Appropriate AWS permissions

EOF
}

# Get AWS account ID
get_aws_account_id() {
    if [ -z "${AWS_ACCOUNT_ID:-}" ]; then
        AWS_ACCOUNT_ID=$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)
        if [ $? -ne 0 ] || [ -z "$AWS_ACCOUNT_ID" ]; then
            log_error "Failed to get AWS account ID. Ensure AWS CLI is configured."
            exit 1
        fi
    fi
    echo "$AWS_ACCOUNT_ID"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed"
        exit 1
    fi

    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi

    # Check Docker daemon
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi

    # Check Terraform state (if ECR repository exists)
    ECR_URI=$(aws ecr describe-repositories --profile "$AWS_PROFILE" --repository-names "$REPOSITORY_NAME" --region "$AWS_REGION" --query 'repositories[0].repositoryUri' --output text 2>/dev/null || echo "")
    if [ -z "$ECR_URI" ] || [ "$ECR_URI" = "None" ]; then
        log_error "ECR repository '$REPOSITORY_NAME' not found. Please run 'terraform apply' first."
        exit 1
    fi

    log_success "Prerequisites check completed"
}

# Build Docker image
build_image() {
    log_info "Building Docker image for DOCX Cleanser Lambda..."

    cd "$(dirname "$0")/../document_cleanser_lambda"

    # Build with explicit platform for Lambda (linux/amd64)
    docker build --platform linux/amd64 -t "$REPOSITORY_NAME:$IMAGE_TAG" .

    if [ $? -eq 0 ]; then
        log_success "Docker image built successfully: $REPOSITORY_NAME:$IMAGE_TAG"
    else
        log_error "Docker image build failed"
        exit 1
    fi
}

# Login to ECR
ecr_login() {
    log_info "Logging into Amazon ECR..."

    local account_id=$(get_aws_account_id)

    # Get ECR login token and login
    aws ecr get-login-password --profile "$AWS_PROFILE" --region "$AWS_REGION" | docker login --username AWS --password-stdin "$account_id.dkr.ecr.$AWS_REGION.amazonaws.com"

    if [ $? -eq 0 ]; then
        log_success "Successfully logged into ECR"
    else
        log_error "ECR login failed"
        exit 1
    fi
}

# Tag and push image to ECR
push_image() {
    log_info "Pushing image to ECR..."

    local account_id=$(get_aws_account_id)
    local ecr_uri="$account_id.dkr.ecr.$AWS_REGION.amazonaws.com/$REPOSITORY_NAME:$IMAGE_TAG"

    # Tag image for ECR
    docker tag "$REPOSITORY_NAME:$IMAGE_TAG" "$ecr_uri"

    # Push to ECR
    docker push "$ecr_uri"

    if [ $? -eq 0 ]; then
        log_success "Image pushed successfully to ECR: $ecr_uri"
        echo "ECR_URI=$ecr_uri"
    else
        log_error "Failed to push image to ECR"
        exit 1
    fi
}

# Update Lambda function with new image
update_lambda() {
    log_info "Updating Lambda function with new container image..."

    local account_id=$(get_aws_account_id)
    local ecr_uri="$account_id.dkr.ecr.$AWS_REGION.amazonaws.com/$REPOSITORY_NAME:$IMAGE_TAG"
    local lambda_name="document-cleanser-lambda"

    # Update Lambda function code
    aws lambda update-function-code \
        --profile "$AWS_PROFILE" \
        --region "$AWS_REGION" \
        --function-name "$lambda_name" \
        --image-uri "$ecr_uri" \
        --output table

    if [ $? -eq 0 ]; then
        log_success "Lambda function updated successfully"

        # Wait for update to complete
        log_info "Waiting for Lambda function update to complete..."
        aws lambda wait function-updated --profile "$AWS_PROFILE" --region "$AWS_REGION" --function-name "$lambda_name"
        log_success "Lambda function update completed"
    else
        log_error "Failed to update Lambda function"
        exit 1
    fi
}

# Run validation script
run_validation() {
    log_info "Running deployment validation..."

    cd "$(dirname "$0")"

    if [ -f "./validate-deployment.sh" ]; then
        ./validate-deployment.sh
    else
        log_warning "Validation script not found, skipping validation"
    fi
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -r|--region)
                AWS_REGION="$2"
                shift 2
                ;;
            -e|--env)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -t|--tag)
                IMAGE_TAG="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            build)
                COMMAND="build"
                shift
                ;;
            login)
                COMMAND="login"
                shift
                ;;
            push)
                COMMAND="push"
                shift
                ;;
            deploy)
                COMMAND="deploy"
                shift
                ;;
            validate)
                COMMAND="validate"
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                show_help
                exit 1
                ;;
        esac
    done

    if [ -z "${COMMAND:-}" ]; then
        log_error "No command specified"
        show_help
        exit 1
    fi
}

# Main execution
main() {
    log_info "DOCX Cleanser Lambda Container Deployment"
    log_info "Region: $AWS_REGION, Environment: $ENVIRONMENT, Tag: $IMAGE_TAG"
    echo "============================================================"

    case $COMMAND in
        build)
            check_prerequisites
            build_image
            ;;
        login)
            ecr_login
            ;;
        push)
            check_prerequisites
            build_image
            ecr_login
            push_image
            ;;
        deploy)
            check_prerequisites
            build_image
            ecr_login
            push_image
            update_lambda
            log_success "Deployment completed successfully!"
            echo ""
            log_info "Next steps:"
            echo "  1. Run: $0 validate"
            echo "  2. Test with sample DOCX file"
            echo "  3. Monitor CloudWatch logs"
            ;;
        validate)
            run_validation
            ;;
        *)
            log_error "Unknown command: $COMMAND"
            exit 1
            ;;
    esac
}

# Parse arguments and run
parse_args "$@"
main
