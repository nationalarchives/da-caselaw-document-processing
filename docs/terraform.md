## Terraform Infrastructure Deployment

**Current Status**: ✅ Successfully deployed and working in staging environment after manual deployment.

### Overview

The Terraform configuration in the `terraform/` directory deploys the DOCX metadata stripping Lambda function with production-ready VPC networking, security groups, and IAM permissions. The Docker image tag for the Lambda is now passed as an explicit input variable (`ECR_IMAGE_TAG`) from the GitHub Actions workflow. There is **no longer any automated commit or update to tfvars files** for image tags. All deployments are explicit and auditable.

### How Image Tag Deployment Works

- The workflow triggers this Terraform deployment and supplies the image tag using `-var="ECR_IMAGE_TAG=..."`.
- For production, the workflow enforces that only GitHub release tags (e.g., `refs/tags/v1.2.3`) are used as image tags.
- Image tag must match a pushed image in ECR. The Lambda will use the image tag you provide.

### Usage

1. **Configure your variables** in `terraform.tfvars` (see example file for required values).
2. **Run Terraform** via the CI/CD workflow, or manually:

   ```sh
   terraform plan -var="ECR_IMAGE_TAG=<your-image-tag>"
   terraform apply -var="ECR_IMAGE_TAG=<your-image-tag>"
   ```

3. **Image tag must match a pushed image in ECR**. The Lambda will use the image tag you provide.

#### Inputs

- `ECR_IMAGE_TAG`: Docker image tag to deploy (required)
- `caselaw_vpc_id`: VPC ID for Lambda deployment
- `unpublished_assets_bucket_name`: S3 bucket for unpublished assets
- `unpublished_assets_kms_key_arn`: KMS key ARN for bucket encryption
- `s3_prefix_list_id`: Prefix list ID for S3 VPC endpoint
- `pdf_generation_queue_arn`: ARN of the SQS queue for PDF generation that subscribes to S3 events via SNS

#### Outputs

See `main.tf` for all outputs, including Lambda ARNs, security group IDs, subnet IDs, and VPC endpoint details.

#### Security & Compliance

- Lambda runs in a private VPC with no internet access
- All AWS service access via VPC endpoints
- Minimal IAM permissions
- KMS integration for encrypted S3 objects

#### Architecture

The infrastructure uses an SNS topic as an intermediary between S3 bucket notifications and downstream consumers, with SQS queue buffering for the Lambda:

```
S3 Bucket (Object Created)
    ↓
SNS Topic (document-processing-s3-events)
    ├→ SQS Queue (document-processing-lambda-queue)
    │   ├→ Lambda Function (document cleanser)
    │   └→ DLQ (document-processing-lambda-queue-dlq) [after 3 failed retries]
    └→ SQS Queue (PDF generation - raw message delivery)
```

This architecture provides resilience against Lambda downtime:

- **Message buffering**: SQS queue holds messages if Lambda is unavailable (e.g., ECR image issues)
- **Automatic retries**: Failed messages are retried up to 3 times with exponential backoff
- **Dead Letter Queue (DLQ)**: Messages that fail all retries are moved to the DLQ for investigation
- **No message loss**: S3 events are preserved during Lambda failures or deployment issues
- **Fan-out pattern**: SNS enables multiple subscribers to receive the same S3 events

#### Operations

##### Monitoring and handling Failed Messages

To address failed messages, we can:

1. view the failed messages that end up in the queue
2. analyse why they failed to be processed successfully by looking at logs
3. fix the underlying issue
4. attempt to redrive the messages back into the main queue to be processed

For details on how to do this in the console or aws cli, see: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html

##### CloudWatch Alarms

The infrastructure includes CloudWatch alarms for:

- **Main queue**: Alerts when >10 messages are visible (potential processing backlog)
- **DLQ**: Alerts immediately when any message enters the DLQ (processing failure)

Note: there is no subscriber to these alert events yet. For automatic monitoring, we should add this.

#### Notes

- Temporary VPC endpoints are included here for ECR and CloudWatch Logs; these should be migrated to main VPC infrastructure in future.
- All deployments are now explicit and controlled via workflow inputs.
