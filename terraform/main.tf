# Document Cleanser Lambda Infrastructure
# This Terraform configuration deploys a Lambda function for stripping author metadata
# from documents (DOCX, PDF, etc.) with production-ready VPC networking and security controls.
# Uses DA Terraform modules for consistent infrastructure patterns.

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.29.0"
    }
  }
  backend "s3" {
    key          = "terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
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

variable "ECR_IMAGE_TAG" {
  description = "Tag of the Docker image to deploy for the Lambda"
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

variable "pdf_generation_queue_arn" {
  description = "ARN of the SQS queue for PDF generation that will subscribe to the S3 event SNS topic"
  type        = string
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
  image_url = "${module.document_cleanser_ecr.repository_url}:${var.ECR_IMAGE_TAG}"

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

  # Lambda permissions are now handled via SNS (see aws_lambda_permission.allow_sns_invoke)
  lambda_invoke_permissions = {}

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

# ================================================================
# SNS TOPIC FOR S3 EVENTS - FAN-OUT TO LAMBDA AND SQS
# ================================================================

# KMS key for SNS topic and SQS queues encryption
resource "aws_kms_key" "sns_topic" {
  description             = "KMS key for document processing SNS topic and SQS queues encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow S3 to use the key"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action = [
          "kms:GenerateDataKey*",
          "kms:Decrypt"
        ]
        Resource = "*"
      },
      {
        Sid    = "Allow SNS to use the key"
        Effect = "Allow"
        Principal = {
          Service = "sns.amazonaws.com"
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      },
      {
        Sid    = "Allow SQS to use the key"
        Effect = "Allow"
        Principal = {
          Service = "sqs.amazonaws.com"
        }
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      },
      {
        Sid    = "Allow Lambda to use the key"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = [
          "kms:Decrypt"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "document-processing-sns-sqs-key"
  })
}

resource "aws_kms_alias" "sns_topic" {
  name          = "alias/document-processing-sns-sqs"
  target_key_id = aws_kms_key.sns_topic.key_id
}

# SNS Topic for S3 events - allows fan-out to multiple subscribers
# Uses customer-managed KMS key for at-rest encryption
resource "aws_sns_topic" "s3_document_events" {
  name              = "document-processing-s3-events"
  display_name      = "Document Processing S3 Events"
  kms_master_key_id = aws_kms_key.sns_topic.arn

  tags = merge(local.common_tags, {
    Name = "document-processing-s3-events"
  })
}

# SNS Topic Policy - allow S3 bucket to publish events
resource "aws_sns_topic_policy" "s3_publish_policy" {
  arn = aws_sns_topic.s3_document_events.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3ToPublish"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.s3_document_events.arn
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
          ArnLike = {
            "aws:SourceArn" = "arn:aws:s3:::${var.unpublished_assets_bucket_name}"
          }
        }
      }
    ]
  })
}

# ================================================================
# SQS QUEUE FOR LAMBDA PROCESSING WITH DLQ
# ================================================================
# This queue sits between SNS and Lambda to provide:
# - Message buffering if Lambda is down (e.g., ECR image issues)
# - Automatic retries with exponential backoff
# - Dead Letter Queue (DLQ) for permanently failed messages
# - No message loss during Lambda downtime

module "document_processing_queue" {
  source = "github.com/nationalarchives/da-terraform-modules//sqs?ref=93712ba9b01e10aad16b331a0d8cb16322924222"

  queue_name = "document-processing-lambda-queue"

  # DLQ Configuration - messages move here after max retries exhausted
  create_dlq               = true
  redrive_maximum_receives = 3 # Try processing 3 times before sending to DLQ

  # Timeout Configuration
  # Lambda has 300s timeout, so we need visibility timeout > 300s
  # This prevents messages being reprocessed while Lambda is still working
  visibility_timeout = 360 # 6 minutes (Lambda timeout + buffer)

  # Message Retention - keep messages for 4 days in main queue
  message_retention_seconds = 345600 # 4 days

  # DLQ Retention - keep failed messages for 14 days for investigation
  dlq_message_retention_seconds = 1209600 # 14 days

  # Encryption using the same KMS key as SNS
  encryption_type = "kms"
  kms_key_id      = aws_kms_key.sns_topic.id

  # Enable long polling to reduce costs
  receive_wait_time_seconds = 20

  # CloudWatch Alarms for queue monitoring
  alarm_name_prefix    = "document-processing"
  alarm_sns_topic_arns = [] # TODO: Add SNS topic for alarms if needed

  # Monitor when messages are in the queue for too long
  create_delayed_message_alert = true
  delayed_message_threshold    = 10 # Alert if > 10 messages delayed

  # Monitor DLQ for failed messages
  create_dlq_alert       = true
  dlq_alarm_threshold    = 1 # Alert immediately when any message hits DLQ
  dlq_evaluation_periods = 1

  tags = merge(local.common_tags, {
    Purpose = "Lambda message buffering with retry and DLQ"
  })
}

# SQS Queue Policy - allow SNS topic to send messages + enforce encryption in transit
resource "aws_sqs_queue_policy" "document_queue_sns_policy" {
  queue_url = module.document_processing_queue.sqs_url

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSNSToSendMessage"
        Effect = "Allow"
        Principal = {
          Service = "sns.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = module.document_processing_queue.sqs_arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_sns_topic.s3_document_events.arn
          }
        }
      },
      {
        Sid    = "DenyInsecureTransport"
        Effect = "Deny"
        Principal = {
          AWS = "*"
        }
        Action   = "sqs:*"
        Resource = module.document_processing_queue.sqs_arn
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

# ================================================================
# END SQS QUEUE CONFIGURATION
# ================================================================

# SNS Subscription: Document Processing SQS Queue (with raw message delivery)
# This replaces the direct SNS -> Lambda subscription
resource "aws_sns_topic_subscription" "document_queue_subscription" {
  topic_arn            = aws_sns_topic.s3_document_events.arn
  protocol             = "sqs"
  endpoint             = module.document_processing_queue.sqs_arn
  raw_message_delivery = false # Keep SNS envelope for debugging

  depends_on = [
    aws_sqs_queue_policy.document_queue_sns_policy
  ]
}

# Lambda Permission - allow SQS to invoke Lambda (replaces SNS permission)
resource "aws_lambda_permission" "allow_sqs_invoke" {
  statement_id  = "AllowExecutionFromSQS"
  action        = "lambda:InvokeFunction"
  function_name = module.document_cleanser_lambda.lambda_function.function_name
  principal     = "sqs.amazonaws.com"
  source_arn    = module.document_processing_queue.sqs_arn

  depends_on = [module.document_cleanser_lambda]
}

# Lambda Event Source Mapping - connect SQS queue to Lambda
# This enables Lambda to poll the SQS queue and process messages with retries
resource "aws_lambda_event_source_mapping" "sqs_to_lambda" {
  event_source_arn = module.document_processing_queue.sqs_arn
  function_name    = module.document_cleanser_lambda.lambda_function.function_name

  # Batch Configuration
  batch_size                         = 1 # Process one message at a time for reliability
  maximum_batching_window_in_seconds = 0 # Process immediately

  # Error Handling
  # With 3 retries configured, Lambda will attempt processing 3 times
  # before the message goes to the DLQ (configured in SQS redrive_maximum_receives)
  function_response_types = ["ReportBatchItemFailures"] # Enable partial batch failures

  # Scaling Configuration
  scaling_config {
    maximum_concurrency = 5 # Limit concurrent executions to prevent overwhelming Lambda
  }

  depends_on = [
    aws_lambda_permission.allow_sqs_invoke,
    module.document_processing_queue
  ]
}

# IAM Policy for Lambda to consume from SQS
resource "aws_iam_role_policy" "lambda_sqs_policy" {
  name = "document-cleanser-lambda-sqs-access"
  role = local.lambda_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = module.document_processing_queue.sqs_arn
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = aws_kms_key.sns_topic.arn
      }
    ]
  })

  depends_on = [
    module.document_cleanser_lambda
  ]
}

# SNS Subscription: PDF Generation SQS Queue (with raw message delivery)
resource "aws_sns_topic_subscription" "pdf_queue_subscription" {
  topic_arn            = aws_sns_topic.s3_document_events.arn
  protocol             = "sqs"
  endpoint             = var.pdf_generation_queue_arn
  raw_message_delivery = true

  filter_policy_scope = "MessageBody"
  filter_policy = jsonencode({
    Records = {
      s3 = {
        object = {
          key = [
            {
              suffix = ".docx"
            }
          ]
        }
      }
    }
  })

  depends_on = [
    aws_sqs_queue_policy.pdf_queue_sns_policy
  ]
}

# SQS Queue Policy - allow SNS topic to send messages to PDF generation queue + enforce encryption in transit
resource "aws_sqs_queue_policy" "pdf_queue_sns_policy" {
  queue_url = replace(var.pdf_generation_queue_arn, "arn:aws:sqs:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:", "https://sqs.${data.aws_region.current.id}.amazonaws.com/${data.aws_caller_identity.current.account_id}/")

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowSNSToSendMessage"
        Effect = "Allow"
        Principal = {
          Service = "sns.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = var.pdf_generation_queue_arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_sns_topic.s3_document_events.arn
          }
        }
      },
      {
        Sid    = "DenyInsecureTransport"
        Effect = "Deny"
        Principal = {
          AWS = "*"
        }
        Action   = "sqs:*"
        Resource = var.pdf_generation_queue_arn
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

# ================================================================
# END SNS TOPIC CONFIGURATION
# ================================================================

# S3 Bucket Notification - trigger SNS topic (not Lambda directly)
# This allows fan-out to multiple subscribers (Lambda and SQS)
resource "aws_s3_bucket_notification" "document_processing" {
  bucket = var.unpublished_assets_bucket_name

  topic {
    topic_arn = aws_sns_topic.s3_document_events.arn
    events    = ["s3:ObjectCreated:*"]
  }

  depends_on = [
    aws_sns_topic_policy.s3_publish_policy
  ]
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

# SNS Topic outputs for monitoring and debugging
output "sns_topic_arn" {
  description = "ARN of the SNS topic for S3 document events"
  value       = aws_sns_topic.s3_document_events.arn
}

output "sns_topic_name" {
  description = "Name of the SNS topic for S3 document events"
  value       = aws_sns_topic.s3_document_events.name
}

output "sns_document_queue_subscription_arn" {
  description = "ARN of the SNS subscription for document processing queue"
  value       = aws_sns_topic_subscription.document_queue_subscription.arn
}

output "sns_pdf_queue_subscription_arn" {
  description = "ARN of the SNS subscription for PDF generation queue"
  value       = aws_sns_topic_subscription.pdf_queue_subscription.arn
}

output "sns_sqs_kms_key_arn" {
  description = "ARN of the KMS key used for SNS topic and SQS queues encryption"
  value       = aws_kms_key.sns_topic.arn
}

output "sns_sqs_kms_key_id" {
  description = "ID of the KMS key used for SNS topic and SQS queues encryption"
  value       = aws_kms_key.sns_topic.key_id
}

# SQS Queue outputs for monitoring and debugging
output "document_processing_queue_url" {
  description = "URL of the document processing SQS queue"
  value       = module.document_processing_queue.sqs_url
}

output "document_processing_queue_arn" {
  description = "ARN of the document processing SQS queue"
  value       = module.document_processing_queue.sqs_arn
}

output "document_processing_dlq_url" {
  description = "URL of the document processing DLQ (Dead Letter Queue)"
  value       = module.document_processing_queue.dlq_sqs_url
}

output "document_processing_dlq_arn" {
  description = "ARN of the document processing DLQ (Dead Letter Queue)"
  value       = module.document_processing_queue.dlq_sqs_arn
}

output "lambda_event_source_mapping_uuid" {
  description = "UUID of the Lambda event source mapping (SQS to Lambda)"
  value       = aws_lambda_event_source_mapping.sqs_to_lambda.uuid
}
