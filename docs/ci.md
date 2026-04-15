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
