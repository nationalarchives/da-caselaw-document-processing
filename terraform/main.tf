# Document Cleansing Lambda Infrastructure
# This Terraform configuration deploys a Lambda function for stripping author metadata
# from documents (DOCX, PDF, etc.) with production-ready VPC networking and security controls.
# Uses DA Terraform modules for consistent infrastructure patterns.

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# AWS Provider configuration
provider "aws" {
  region = "eu-west-2"
}

# Get current AWS account and region information
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Common tags for all resources
locals {
  common_tags = {
    Project   = "da-caselaw-document-processing"
    Service   = "document-cleanser-lambda"
    ManagedBy = "terraform"
  }




}

variable "backend_bucket" {
  description = "S3 bucket for Terraform backend state"
  type        = string
}

variable "caselaw_vpc_id" {
  description = "The ID of the existing caselaw VPC"
  type        = string
}

variable "unpublished_assets_bucket_name" {
  description = "Name of the unpublished assets S3 bucket"
  type        = string
}

variable "unpublished_assets_kms_key_arn" {
  description = "ARN of the primary KMS key used to encrypt the unpublished assets bucket"
  type        = string
}

variable "legacy_kms_key_arns" {
  description = "List of legacy/historical KMS key ARNs for objects encrypted with older keys"
  type        = list(string)
  default     = []
}

variable "s3_prefix_list_id" {
  description = "Prefix list ID for S3 VPC endpoints (pl-...). Required for VPC endpoint access to S3."
  type        = string

  validation {
    condition     = can(regex("^pl-[a-f0-9]{8}$", var.s3_prefix_list_id))
    error_message = "S3 prefix list ID must be in format 'pl-xxxxxxxx' where x is a hexadecimal character."
  }
}

# Validation: Ensure we have subnets in at least 2 AZs for high availability
resource "terraform_data" "az_validation" {
  count = local.az_count >= 2 ? 0 : 1

  lifecycle {
    precondition {
      condition     = local.az_count >= 2
      error_message = "Need at least 2 availability zones for high availability. Found ${local.az_count} AZs."
    }
  }
}

# DA Terraform modules are sourced directly from GitHub
# Note: Module sources must be static strings, cannot use variables

# Data sources for existing VPC infrastructure
data "aws_vpc" "caselaw" {
  id = var.caselaw_vpc_id
}

# Get all available private subnets in the VPC (should cover all 3 AZs)
data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [var.caselaw_vpc_id]
  }

  filter {
    name   = "tag:Name"
    values = ["*private*"]
  }
}

# Get subnet details to ensure we have subnets across all 3 AZs
data "aws_subnet" "private" {
  for_each = toset(data.aws_subnets.private.ids)
  id       = each.value
}

# Validate we have subnets in all 3 AZs for high availability
locals {
  subnet_azs = [for subnet in data.aws_subnet.private : subnet.availability_zone]
  unique_azs = toset(local.subnet_azs)

  # Ensure we have at least 2 AZs (preferably 3 for production)
  az_count = length(local.unique_azs)
}

# ✅ SECURE CONTAINER LAMBDA WITH VPC ENDPOINTS - NO INTERNET ACCESS ✅
#
# This configuration provides complete network isolation for container-based Lambda:
# ✅ S3 VPC endpoint (existing: vpce-0d124fbf21e85da62) - for Lambda runtime/layers
# ✅ ECR API VPC endpoint (created below) - for container image metadata
# ✅ ECR DKR VPC endpoint (created below) - for container image data
# ✅ CloudWatch Logs VPC endpoint (created below) - for Lambda logging
#
# SECURITY STATUS: Lambda operates with ZERO internet access
# - All AWS service communication via VPC endpoints only
# - No NAT Gateway or Internet Gateway access required
# - Security groups restrict traffic to HTTPS on port 443 only
#
# TODO: Move VPC endpoints to main VPC infrastructure Terraform for better organization

# Security Group for Lambda - STRICTLY NO INTERNET ACCESS
module "document_cleanser_security_group" {
  source = "github.com/nationalarchives/da-terraform-modules//security_group?ref=93712ba9b01e10aad16b331a0d8cb16322924222"

  vpc_id      = var.caselaw_vpc_id
  name        = "document-cleanser-lambda-sg"
  description = "Security group for document cleanser Lambda - AWS services via VPC endpoints only (no internet)"

  rules = {
    # No ingress rules - Lambda doesn't need incoming connections
    ingress = []

    # Egress rules - HTTPS to AWS services via VPC endpoints only (no internet access)
    egress = [
      {
        port           = 443
        description    = "HTTPS to S3 VPC endpoint for Lambda runtime and layers"
        prefix_list_id = var.s3_prefix_list_id
      }
      # Note: No egress rule needed for interface VPC endpoints (ECR, CloudWatch Logs)
      # Interface endpoints create ENIs in VPC subnets with their own security groups
    ]
  }

  common_tags = local.common_tags
}

# IAM Policies for Lambda with minimal permissions using DA modules
module "s3_access_policy" {
  source = "github.com/nationalarchives/da-terraform-modules//iam_policy?ref=93712ba9b01e10aad16b331a0d8cb16322924222"

  name        = "document-cleanser-lambda-s3-access"
  description = "Allows document cleanser Lambda to access unpublished assets bucket"

  policy_string = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectTagging",
          "s3:PutObject",
          "s3:PutObjectTagging"
        ]
        Resource = "arn:aws:s3:::${var.unpublished_assets_bucket_name}/*"
      }
    ]
  })

  tags = local.common_tags
}

module "kms_access_policy" {
  source = "github.com/nationalarchives/da-terraform-modules//iam_policy?ref=93712ba9b01e10aad16b331a0d8cb16322924222"

  name        = "document-cleanser-lambda-kms-access"
  description = "Allows document cleanser Lambda to decrypt unpublished assets bucket"

  policy_string = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = concat([var.unpublished_assets_kms_key_arn], var.legacy_kms_key_arns)
        Condition = {
          StringEquals = {
            "kms:ViaService" = "s3.${data.aws_region.current.id}.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

# ================================================================
# TEMPORARY VPC ENDPOINTS - MOVE TO MAIN VPC INFRASTRUCTURE LATER
# ================================================================
#
# TODO: These VPC endpoints should eventually be defined in the main VPC
# infrastructure Terraform configuration, not here. They are included
# temporarily to make the container Lambda functional without internet access.
#
# When moving these:
# 1. Add to main VPC Terraform configuration
# 2. Remove from this file
# 3. Reference existing endpoints as data sources
# 4. Update security group to reference endpoint security groups

# Security group for VPC endpoints - allows HTTPS from Lambda and private subnets
resource "aws_security_group" "vpc_endpoints" {
  name_prefix = "document-lambda-vpc-endpoints-"
  description = "Security group for VPC endpoints used by document cleanser Lambda"
  vpc_id      = var.caselaw_vpc_id

  ingress {
    description = "HTTPS from VPC CIDR (includes Lambda in private subnets)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.caselaw.cidr_block]
  }


  tags = merge(local.common_tags, {
    Name = "document-lambda-vpc-endpoints-sg"
    Note = "TODO: Move to main VPC infrastructure"
  })
}

# ECR API VPC Endpoint - Required for container image metadata
resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id             = var.caselaw_vpc_id
  service_name       = "com.amazonaws.${data.aws_region.current.id}.ecr.api"
  vpc_endpoint_type  = "Interface"
  subnet_ids         = data.aws_subnets.private.ids
  security_group_ids = [aws_security_group.vpc_endpoints.id]

  private_dns_enabled = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = "*"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:GetRepositoryPolicy",
          "ecr:DescribeRepositories",
          "ecr:ListImages",
          "ecr:DescribeImages",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "document-lambda-ecr-api-endpoint"
    Note = "TODO: Move to main VPC infrastructure"
  })
}

# ECR Docker Registry VPC Endpoint - Required for container image data
resource "aws_vpc_endpoint" "ecr_dkr" {
  vpc_id             = var.caselaw_vpc_id
  service_name       = "com.amazonaws.${data.aws_region.current.id}.ecr.dkr"
  vpc_endpoint_type  = "Interface"
  subnet_ids         = data.aws_subnets.private.ids
  security_group_ids = [aws_security_group.vpc_endpoints.id]

  private_dns_enabled = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = "*"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "document-lambda-ecr-dkr-endpoint"
    Note = "TODO: Move to main VPC infrastructure"
  })
}

# CloudWatch Logs VPC Endpoint - Required for Lambda logging
resource "aws_vpc_endpoint" "logs" {
  vpc_id             = var.caselaw_vpc_id
  service_name       = "com.amazonaws.${data.aws_region.current.id}.logs"
  vpc_endpoint_type  = "Interface"
  subnet_ids         = data.aws_subnets.private.ids
  security_group_ids = [aws_security_group.vpc_endpoints.id]

  private_dns_enabled = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = "*"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams"
        ]
        Resource = "*"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "document-lambda-logs-endpoint"
    Note = "TODO: Move to main VPC infrastructure"
  })
}

# ================================================================
# END TEMPORARY VPC ENDPOINTS
# ================================================================

# ECR Repository for Lambda container images using DA modules
module "document_cleanser_ecr" {
  source = "github.com/nationalarchives/da-terraform-modules//ecr?ref=93712ba9b01e10aad16b331a0d8cb16322924222"

  repository_name             = "document-cleanser-lambda"
  expire_untagged_images_days = 7
  image_source_url            = "https://github.com/nationalarchives/da-caselaw-document-processing"

  # Allow Lambda service to pull images
  allowed_principals = [
    data.aws_caller_identity.current.account_id
  ]

  common_tags = local.common_tags
}

# Document Cleanser Lambda Function using DA Terraform modules (Container-based)
# ⚠️  WARNING: This container Lambda requires ECR VPC endpoints to work in isolated VPC
module "document_cleanser_lambda" {
  source = "github.com/nationalarchives/da-terraform-modules//lambda?ref=93712ba9b01e10aad16b331a0d8cb16322924222"

  function_name = "document-cleanser-lambda"
  description   = "Lambda function to strip author metadata from documents (DOCX, PDF, etc.)"

  # Container configuration - REQUIRES ECR VPC endpoints for offline operation
  use_image = true
  image_url = "${module.document_cleanser_ecr.repository_url}:latest"

  memory_size     = 512
  timeout_seconds = 300

  # VPC Configuration for network isolation
  vpc_config = {
    subnet_ids         = data.aws_subnets.private.ids
    security_group_ids = [module.document_cleanser_security_group.security_group_id]
  }

  # Environment variables
  plaintext_env_vars = {
    PRIVATE_ASSET_BUCKET = var.unpublished_assets_bucket_name
  }

  # IAM policies with minimal permissions
  policies = {}

  # Remove policy_attachments from module to avoid for_each issues with AWS Provider v6
  # We'll handle these separately below
  policy_attachments = toset([])

  # Lambda permissions for S3 to invoke the function
  lambda_invoke_permissions = {
    "s3.amazonaws.com" = "arn:aws:s3:::${var.unpublished_assets_bucket_name}"
  }

  # CloudWatch logging configuration
  log_retention = 30

  tags = local.common_tags

  depends_on = [
    module.s3_access_policy,
    module.kms_access_policy,
    module.document_cleanser_security_group,
    module.document_cleanser_ecr
  ]
}

# Extract role name from Lambda module ARN for policy attachments
locals {
  lambda_role_name = split("/", module.document_cleanser_lambda.lambda_role_arn)[1]
}

# Manual policy attachments to avoid for_each issues with AWS Provider v6
resource "aws_iam_role_policy_attachment" "lambda_s3_policy" {
  role       = local.lambda_role_name
  policy_arn = module.s3_access_policy.policy_arn

  depends_on = [
    module.document_cleanser_lambda,
    module.s3_access_policy
  ]
}

resource "aws_iam_role_policy_attachment" "lambda_kms_policy" {
  role       = local.lambda_role_name
  policy_arn = module.kms_access_policy.policy_arn

  depends_on = [
    module.document_cleanser_lambda,
    module.kms_access_policy
  ]
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = local.lambda_role_name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

  depends_on = [
    module.document_cleanser_lambda
  ]
}

# S3 Bucket Notification (Note: This assumes the bucket already exists)
# In practice, this might need to be applied separately if the bucket
# is managed by a different Terraform configuration
resource "aws_s3_bucket_notification" "document_processing" {
  bucket = var.unpublished_assets_bucket_name

  lambda_function {
    lambda_function_arn = module.document_cleanser_lambda.lambda_arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".docx"
  }

  lambda_function {
    lambda_function_arn = module.document_cleanser_lambda.lambda_arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".pdf"
  }

  depends_on = [module.document_cleanser_lambda]
}

# Outputs for validation and monitoring
output "lambda_function_arn" {
  description = "ARN of the document cleanser Lambda function"
  value       = module.document_cleanser_lambda.lambda_arn
}

output "lambda_function_name" {
  description = "Name of the document cleanser Lambda function"
  value       = module.document_cleanser_lambda.lambda_function.function_name
}

output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = module.document_cleanser_lambda.lambda_role_arn
}

output "lambda_security_group_id" {
  description = "Security group ID for the Lambda function"
  value       = module.document_cleanser_security_group.security_group_id
}

output "lambda_log_group_name" {
  description = "CloudWatch log group name for the Lambda function"
  value       = "/aws/lambda/document-cleanser-lambda"
}

output "private_subnets_used" {
  description = "Private subnet IDs where the Lambda is deployed"
  value       = data.aws_subnets.private.ids
}

output "vpc_id" {
  description = "VPC ID where the Lambda is deployed"
  value       = var.caselaw_vpc_id
}

output "availability_zones" {
  description = "Availability zones where the Lambda subnets are located"
  value       = local.unique_azs
}

output "s3_access_policy_arn" {
  description = "ARN of the S3 access policy"
  value       = module.s3_access_policy.policy_arn
}

output "kms_access_policy_arn" {
  description = "ARN of the KMS access policy"
  value       = module.kms_access_policy.policy_arn
}

output "ecr_repository_url" {
  description = "URL of the ECR repository for Lambda container images"
  value       = module.document_cleanser_ecr.repository_url
}

output "ecr_repository_arn" {
  description = "ARN of the ECR repository"
  value       = module.document_cleanser_ecr.repository_arn
}

# VPC Endpoints outputs (temporary - remove when moved to main VPC infrastructure)
output "vpc_endpoints" {
  description = "VPC endpoint IDs created for Lambda functionality (TODO: move to main VPC)"
  value = {
    ecr_api_endpoint_id         = aws_vpc_endpoint.ecr_api.id
    ecr_dkr_endpoint_id         = aws_vpc_endpoint.ecr_dkr.id
    logs_endpoint_id            = aws_vpc_endpoint.logs.id
    endpoints_security_group_id = aws_security_group.vpc_endpoints.id
  }
}

output "vpc_endpoints_dns_names" {
  description = "DNS names for VPC endpoints (for verification)"
  value = {
    ecr_api_dns = aws_vpc_endpoint.ecr_api.dns_entry[0]["dns_name"]
    ecr_dkr_dns = aws_vpc_endpoint.ecr_dkr.dns_entry[0]["dns_name"]
    logs_dns    = aws_vpc_endpoint.logs.dns_entry[0]["dns_name"]
  }
}
