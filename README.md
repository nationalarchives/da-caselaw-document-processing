# DA Caselaw Document Processing

This repository contains AWS Lambda functions and supporting code for document processing in the DA Caselaw project.

## DOCX Author Metadata Stripping Lambda

**Purpose:**
Removes author and related metadata from Microsoft Word DOCX files to ensure privacy compliance before publication.

**Location:** `lambda_strip_docx/`

**Key features:**

- Accepts DOCX files as input (base64-encoded via API Gateway or S3 event).
- Removes author metadata from document properties.
- Preserves document content and formatting.
- Handles errors and logs to CloudWatch.

## Deployment

This project uses Terraform for infrastructure deployment. See the Terraform section below for deployment instructions.

### Local Development and Testing

#### 1. Python Environment

It is strongly recommended to use a Python virtual environment to ensure reproducibility and isolation:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

#### 2. Install Dependencies

Install the required dependencies for the DOCX Lambda:

```sh
pip install -r lambda_strip_docx/requirements-dev.txt
```

#### 3. Run Unit Tests

Place a sample DOCX with author metadata in `lambda_strip_docx/test_files/sample_with_author.docx` and run:

**Option A: Run tests locally with Python:**

```sh
cd lambda_strip_docx
pytest
```

**Option B: Run tests in Docker container (recommended - matches CI/CD):**

```sh
# From project root
./run-tests.sh
```

This builds the test Docker image with all required system dependencies (including pdfcpu for PDF processing) and runs the complete test suite in the same environment used in CI/CD, ensuring consistency between local development and deployment.

#### 4. Test Lambda Locally

You can test the Lambda locally using Docker:

```sh
docker build -t docx-lambda-test -f lambda_strip_docx/Dockerfile lambda_strip_docx/
docker run -d --name docx-lambda-test -p 9000:8080 docx-lambda-test
sleep 10
curl -s -X POST "http://localhost:9000/2015-03-31/functions/function/invocations" \
	-H "Content-Type: application/json" \
	--data-binary @test-event.json > response.json
```

`test-event.json` should be a valid Lambda event payload for your handler (see AWS docs for examples).

#### 5. Linting and Pre-commit

Install and run pre-commit hooks to ensure code quality:

```sh
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

#### 6. Making Changes & Pull Requests

- Ensure all tests pass locally before opening a PR.
- Follow repo and code style guidelines.
- Document any new environment variables or requirements in the README.

#### 7. Development Guidelines

- Always use the provided `requirements.txt` for dependency management.
- Use a virtual environment for all development work.
- If you need to update dependencies, regenerate `requirements.txt` and document the change in the PR.
- Ensure all tests pass locally before opening a PR.
- Follow repo and code style guidelines.
- Document any new environment variables or requirements in the README.

---

## Terraform Infrastructure Deployment

**Current Status**: ✅ Successfully deployed and working in staging environment after manual deployment.

### Overview

The Terraform configuration in the `terraform/` directory deploys the DOCX metadata stripping Lambda function with production-ready VPC networking, security groups, and IAM permissions.

### Architecture

The infrastructure creates:

#### Security & Networking

- **VPC Integration**: Lambda runs in the existing caselaw VPC using private subnets across all 3 availability zones
- **Security Group**: Dedicated security group allowing only HTTPS egress to S3 via VPC endpoint (using prefix list)
- **Network Isolation**: No internet access - Lambda can only communicate with S3 through VPC endpoints

#### IAM & Permissions

- **Dedicated IAM Role**: Lambda execution role with minimal required permissions:
  - `s3:GetObject`, `s3:GetObjectTagging`, `s3:PutObject`, `s3:PutObjectTagging` on unpublished-assets bucket
  - `ec2:CreateNetworkInterface`, `ec2:DescribeNetworkInterfaces`, `ec2:DeleteNetworkInterface` for VPC access
  - `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` for CloudWatch logging
  - `kms:Decrypt`, `kms:GenerateDataKey` for KMS access to decrypt S3 objects

#### Lambda Configuration

- **Runtime**: Python 3.13
- **Memory**: 256 MB
- **Timeout**: 30 seconds
- **VPC**: Deployed to private subnets across all AZs
- **Trigger**: Automatic S3 event notification for `.docx` files

#### Monitoring & Logging

- **CloudWatch Logs**: Dedicated log group with 30-day retention
- **Comprehensive Outputs**: ARNs and IDs for validation and monitoring

### Prerequisites

Before deploying this infrastructure, ensure you have:

1. **Existing caselaw VPC** with:
   - Private subnets tagged with `Tier = "private"` across 3 AZs
   - S3 VPC endpoint configured
   - S3 prefix list ID available

2. **Unpublished assets S3 bucket** with:
   - Bucket name
   - KMS key ARN used for encryption

3. **Terraform** >= 1.0 installed
4. **AWS CLI** configured with appropriate permissions

### Terraform Deployment Steps

Navigate to the terraform directory:

```bash
cd terraform
```

#### 1. Configure Variables

Copy the example variables file and fill in your values:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your actual values:

```hcl
caselaw_vpc_id                = "vpc-your-actual-vpc-id"
unpublished_assets_bucket_name = "your-unpublished-assets-bucket"
unpublished_assets_kms_key_arn = "arn:aws:kms:region:account:key/key-id"
s3_prefix_list_id             = "pl-your-s3-prefix-list"
```

#### 2. Initialize and Plan

```bash
terraform init
terraform plan
```

#### 3. Deploy

```bash
terraform apply
```

#### 4. Validate Deployment

After successful deployment, verify:

```bash
# Check Lambda function status
aws lambda get-function --function-name docx-cleanser-lambda

# Check security group rules
aws ec2 describe-security-groups --group-ids $(terraform output -raw lambda_security_group_id)

# Check VPC configuration
aws lambda get-function-configuration --function-name docx-cleanser-lambda --query 'VpcConfig'
```

### Infrastructure Testing

#### End-to-End Test

1. Upload a DOCX file to the unpublished assets bucket:

```bash
aws s3 cp sample.docx s3://your-unpublished-assets-bucket/test/sample.docx
```

2. Check CloudWatch logs:

```bash
aws logs tail /aws/lambda/docx-cleanser-lambda --follow
```

3. Verify the file was processed (check for `DOCUMENT_PROCESSOR_VERSION` tag):

```bash
aws s3api get-object-tagging --bucket your-unpublished-assets-bucket --key test/sample.docx
```

#### Network Connectivity Test

To verify no internet access:

1. Temporarily modify the Lambda to attempt an external HTTP request
2. Deploy and test - it should fail with a timeout/connection error
3. Revert the changes

### Security Validation

#### Verify Network Isolation

- Lambda security group has no ingress rules
- Lambda security group only allows HTTPS egress to S3 prefix list
- No internet gateway access from private subnets

#### Verify IAM Permissions

- Lambda role has only the minimal required permissions
- S3 access limited to the specific bucket
- KMS access limited to the specific key

#### Verify KMS Integration

- Lambda can decrypt objects in the unpublished assets bucket
- KMS key policy includes the Lambda execution role

### Infrastructure Outputs

The Terraform configuration provides these outputs for monitoring and validation:

- `lambda_function_arn`: ARN of the deployed Lambda function
- `lambda_function_name`: Name of the Lambda function
- `lambda_execution_role_arn`: ARN of the IAM execution role
- `lambda_security_group_id`: Security group ID
- `lambda_log_group_name`: CloudWatch log group name
- `private_subnets_used`: List of private subnet IDs
- `vpc_id`: VPC ID where Lambda is deployed

### Troubleshooting

#### Common Issues

1. **VPC Timeout Errors**: Check that S3 VPC endpoint is properly configured
2. **Permission Errors**: Verify KMS key policy includes the Lambda role
3. **Subnet Issues**: Ensure private subnets are properly tagged
4. **Prefix List**: Verify the S3 prefix list ID is correct for your region

#### Logs and Monitoring

- CloudWatch Logs: `/aws/lambda/docx-cleanser-lambda`
- CloudWatch Metrics: Check Lambda duration, errors, and invocations
- VPC Flow Logs: Monitor network traffic (if enabled)

### Infrastructure Maintenance

#### Updates

- Lambda code updates: Run `terraform apply` after code changes
- Infrastructure changes: Modify Terraform and run plan/apply
- Dependency updates: Update `requirements.txt` in lambda_strip_docx directory

#### Monitoring

- Set up CloudWatch alarms for Lambda errors and duration
- Monitor S3 processing metrics
- Review security group and IAM changes regularly

### Compliance

This configuration meets the specified security requirements:

✅ Lambda deployed in caselaw VPC
✅ Uses private subnets across all 3 AZs
✅ Dedicated security group with S3-only access
✅ No internet connectivity
✅ Minimal IAM permissions
✅ KMS integration for encrypted S3 objects
✅ CloudWatch logging enabled
✅ Infrastructure as Code deployment
✅ Comprehensive resource tagging

### VPC Endpoints Migration

**Note**: The current Terraform configuration temporarily includes VPC endpoints (ECR API, ECR DKR, CloudWatch Logs) to enable secure, offline operation. These endpoints should eventually be moved to the main VPC infrastructure configuration for better organization and reusability.

**Current Temporary VPC Endpoints**:

- ECR API (`com.amazonaws.eu-west-2.ecr.api`) - Container image metadata
- ECR DKR (`com.amazonaws.eu-west-2.ecr.dkr`) - Container image data
- CloudWatch Logs (`com.amazonaws.eu-west-2.logs`) - Lambda logging

**Migration Steps** (when ready):

1. Create VPC endpoints in main VPC infrastructure configuration
2. Update DOCX cleanser to use data sources referencing existing endpoints
3. Remove temporary endpoint resources from Lambda configuration
4. Deploy main VPC endpoints first, then update Lambda configuration

This approach provides better separation of concerns and allows endpoint reuse across multiple Lambda functions.

### Deployment Checklist

#### Pre-Deployment Validation

- [ ] AWS CLI configured and authenticated
- [ ] Terraform variables configured correctly
- [ ] VPC and subnet IDs verified
- [ ] S3 bucket exists and is accessible
- [ ] Required AWS permissions available

#### Deployment Steps

- [ ] Run `terraform init` successfully
- [ ] Review `terraform plan` output
- [ ] Apply Terraform configuration
- [ ] Verify Lambda function created
- [ ] Confirm VPC configuration applied
- [ ] Test S3 trigger configuration

#### Post-Deployment Testing

- [ ] Run validation script (`terraform/validate-deployment.sh`)
- [ ] Execute integration tests (`terraform/integration_tests.py`)
- [ ] Test with sample DOCX file
- [ ] Verify metadata removal
- [ ] Check CloudWatch logs
- [ ] Confirm network isolation

### Performance & Monitoring

#### Recommended CloudWatch Alarms

- Error rate > 5%
- Duration > 60 seconds
- Memory utilization > 80%
- Failed invocations

#### Maintenance Schedule

- **Monthly**: Review CloudWatch metrics and costs
- **Quarterly**: Update Python dependencies
- **Bi-annually**: Review and audit IAM permissions
- **Annually**: Update to latest Lambda runtime

---

## CI/CD Deployment with GitHub Actions

### Using Secrets for Terraform S3 Backend

To securely set the S3 backend bucket for Terraform, add a secret (e.g., `STAGING_TF_BACKEND_BUCKET`) to your GitHub environment. Then use it in your workflow:

```yaml
- name: Terraform Init (Staging)
  run: terraform init -backend-config="bucket=${{ secrets.STAGING_TF_BACKEND_BUCKET }}"
  working-directory: terraform
```

This ensures the bucket name is not hardcoded and is securely managed like your other secrets.

### Overview

For automated deployment using GitHub Actions, you'll need to securely manage Terraform variables. The recommended approach uses GitHub Environments with encrypted secrets.

### Setup GitHub Actions Deployment

#### 1. Create GitHub Environments

1. Go to your repository → **Settings** → **Environments**
2. Create environments: `development`, `staging`, `production`

#### 2. Add Secrets to Each Environment

**AWS Credentials:**

```
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=eu-west-2
AWS_ACCOUNT_ID=123456789012
```

**Terraform Variables (with TF*VAR* prefix):**

```
TF_VAR_environment=production
TF_VAR_caselaw_vpc_id=vpc-xxxxxxxxx
TF_VAR_unpublished_assets_bucket_name=da-prod-unpublished-assets
TF_VAR_unpublished_assets_kms_key_arn=arn:aws:kms:eu-west-2:123456789012:key/xxxxx
TF_VAR_s3_prefix_list_id=pl-xxxxxxxx
```

#### 3. GitHub Actions Workflow Example

```yaml
name: Deploy DOCX Cleanser Lambda

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production # Controls which secrets are loaded

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Terraform Init
        run: terraform init -backend-config="bucket=${{ secrets.TF_BACKEND_BUCKET }}"
        working-directory: terraform

      - name: Terraform Plan
        run: terraform plan
        working-directory: terraform
        env:
          TF_VAR_caselaw_vpc_id: ${{ secrets.TF_VAR_caselaw_vpc_id }}
          TF_VAR_unpublished_assets_bucket_name: ${{ secrets.TF_VAR_unpublished_assets_bucket_name }}
          TF_VAR_unpublished_assets_kms_key_arn: ${{ secrets.TF_VAR_unpublished_assets_kms_key_arn }}
          TF_VAR_s3_prefix_list_id: ${{ secrets.TF_VAR_s3_prefix_list_id }}

      - name: Terraform Apply
        run: terraform apply -auto-approve
        working-directory: terraform
        env:
          TF_VAR_caselaw_vpc_id: ${{ secrets.TF_VAR_caselaw_vpc_id }}
          TF_VAR_unpublished_assets_bucket_name: ${{ secrets.TF_VAR_unpublished_assets_bucket_name }}
          TF_VAR_unpublished_assets_kms_key_arn: ${{ secrets.TF_VAR_unpublished_assets_kms_key_arn }}
          TF_VAR_s3_prefix_list_id: ${{ secrets.TF_VAR_s3_prefix_list_id }}
```

#### 4. Get Required AWS Values

```bash
# Get VPC ID
aws ec2 describe-vpcs --filters "Name=tag:Name,Values=*caselaw*" --query 'Vpcs[0].VpcId'

# Get S3 prefix list
aws ec2 describe-managed-prefix-lists --filters "Name=prefix-list-name,Values=com.amazonaws.vpce.eu-west-2.s3"

# Get KMS key ARN (find the correct key for your S3 bucket)
aws kms list-keys --query 'Keys[].KeyId'
```

### Security Best Practices for CI/CD

#### Use Environment Protection Rules

Configure environment protection rules in GitHub to require manual approval for production deployments.

#### OIDC Authentication (Recommended)

Instead of long-lived access keys, use OpenID Connect:

```yaml
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::123456789012:role/github-actions-role
    role-session-name: GitHubActions
    aws-region: eu-west-2
```

#### Required IAM Permissions

GitHub Actions user needs permissions for:

- `lambda:*` - Lambda function management
- `ecr:*` - Container registry access
- `iam:PassRole` - IAM role assignment
- `ec2:Describe*` - VPC and network queries
- `s3:*` - S3 bucket operations
- `kms:Decrypt`, `kms:GenerateDataKey` - KMS operations

### Alternative CI/CD Methods

**Terraform Cloud**: For team environments, use Terraform Cloud with workspace variables
**AWS Parameter Store**: Store variables in AWS Systems Manager for retrieval during deployment
**Encrypted .tfvars**: Use Mozilla SOPS to encrypt variable files in the repository

---

# Pre-commit and Repo Standards

This repository uses [pre-commit](https://pre-commit.com/) and [detect-secrets](https://github.com/Yelp/detect-secrets) to enforce code quality and prevent secrets leakage. See [The Engineering Handbook](https://national-archives.atlassian.net/wiki/spaces/DAAE/pages/47775767/Engineering+Handbook) for more details.

---

## Coming Soon

**PDF author metadata cleansing Lambda** will be added in a separate PR.
