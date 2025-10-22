# DA Caselaw Document Processing

AWS Lambda function for document processing (privacy, metadata stripping, etc.).

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

#### Outputs

See `main.tf` for all outputs, including Lambda ARNs, security group IDs, subnet IDs, and VPC endpoint details.

#### Security & Compliance

- Lambda runs in a private VPC with no internet access
- All AWS service access via VPC endpoints
- Minimal IAM permissions
- KMS integration for encrypted S3 objects

#### Notes

- Temporary VPC endpoints are included here for ECR and CloudWatch Logs; these should be migrated to main VPC infrastructure in future.
- All deployments are now explicit and controlled via workflow inputs.

#### Reference

See the main repository `README.md` for full documentation and deployment flow.

---

## CI/CD Deployment with GitHub Actions

### Overview

This repository uses GitHub Actions for CI/CD automation. The workflow builds and pushes Docker images, then triggers the Terraform deployment workflow by passing the Docker image tag as an input variable. This approach keeps infrastructure and application versioning separate and avoids automated commits to tfvars files.

### Application vs Infrastructure Versioning

- **Application versioning**: Docker images are always tagged with the current GitHub reference (`GITHUB_REF`). For staging and branch builds, this is typically a branch or commit reference. For production releases, this must be a GitHub release tag (e.g., `refs/tags/v1.2.3`).
- **Infrastructure versioning**: Managed via git commits/tags in the Terraform code.

You deploy a new application version by building and pushing a Docker image tagged with the current GitHub reference. The workflow then passes this tag as an input to the Terraform workflow. Infrastructure changes are deployed by updating and applying Terraform code.

### Staging and Production Deployments

- **Staging**: Used for testing new app versions and infra changes. The workflow is triggered automatically or manually, and always uses the current GitHub reference as the Docker image tag.
- **Production**: Used for live deployments. The workflow must be triggered manually, and the environment must be explicitly set to `production` in the workflow dispatch. For production, the workflow verifies that the GitHub reference is a release tag (`refs/tags/v*`). If the reference is not a release tag, the workflow will fail and not deploy to production.

### Deployment Steps

1. **Build and push Docker image**
   - Automated by GitHub Actions (`.github/workflows/docker-build-and-deploy.yml`).
   - The Docker image is tagged with the current GitHub reference (`GITHUB_REF`).
2. **Trigger Terraform deployment workflow**
   - The workflow passes `image_tag` (the current GitHub reference) as an input to the Terraform plan/apply workflow.
   - For production: only allowed if the reference is a release tag (`refs/tags/v*`).
3. **Terraform deployment**
   - The Terraform workflow uses the provided image tag variable to deploy the specified version.

#### Example: Manual Production Deployment

1. Manually trigger the workflow in GitHub Actions and select `production` as the environment.
2. Ensure the GitHub reference is a release tag (e.g., `refs/tags/v1.2.3`).
3. The workflow uses the release tag as the Docker image tag and deploys to production.
4. Approve the deployment if required by environment protection rules.

#### Example: Automated Staging Deployment

1. Workflow is triggered automatically on PR merge to main, or manually with environment set to `staging`.
2. The specified GitHub reference is used as the Docker image tag.
3. Terraform deploys the new version to staging.

### Why This Approach?

- No automated commits to tfvars files (all changes are explicit and auditable).
- All production deployments require manual approval and must use a GitHub release tag as the image tag.
- Maintains clear separation between application and infrastructure versioning.
- Avoids complexity of GPG signing in CI/CD.

---

# Pre-commit and Repo Standards

This repository uses [pre-commit](https://pre-commit.com/) and [detect-secrets](https://github.com/Yelp/detect-secrets) to enforce code quality and prevent secrets leakage. See [The Engineering Handbook](https://national-archives.atlassian.net/wiki/spaces/DAAE/pages/47775767/Engineering+Handbook) for more details.

---

## Coming Soon

**PDF author metadata cleansing Lambda** will be added in a separate PR.
