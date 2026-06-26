# DA Caselaw Document Processing

AWS Lambda function for document processing (privacy, metadata stripping, etc.).

## Local Development and Testing

### 1. Run Tests in Docker container (matches CI/CD)

```sh
# From project root
./run-tests.sh
```

This builds the test Docker image with all required system dependencies (including pdfcpu for PDF processing) and runs the complete test suite in the same environment used in CI/CD, ensuring consistency between local development and deployment.

### 2. Test Lambda Locally

You can test the Lambda locally using Docker:

```sh
script/server
```

will start the server and

```
script/upload document_cleanser_lambda/test-event.json
```

will submit a valid Lambda event payload to your handler (see AWS docs for examples).

Output will be at the same filename with `.output.json` appended.

### 3. Linting and Pre-commit

Install and run pre-commit hooks to ensure code quality:

```sh
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

### 4. Updating dependencies with poetry

Dependencies should be managed by renovate (see [renovate.json](renovate.json)).
If you need to update dependencies, run `poetry update`; see [pyproject.toml](document_cleanser_lambda/pyproject.toml)

### 5. Development Guidelines

Ensure all tests pass locally before opening a PR via `./script/test`

Follow repo and code style guidelines.

Document new environment variables or requirements in the README.

## Release process

1. Update the code
   - Create a branch `release/v{major}.{minor}.{patch}`
   - Update the version number in `document_cleanser_lambda/lambda_function.py`
   - Update `CHANGELOG.md` for the release
   - Commit and push
   - Open a PR from that branch to main
   - Get approval on the PR
1. Create a GitHub Release
   - Create a new tag on main with the same version number.
   - Generate release notes
   - Publish the release
1. Deploy to production
   - Go to the [docker-build-and-deploy action](https://github.com/nationalarchives/da-caselaw-document-processing/actions/workflows/docker-build-and-deploy.yml)
   - Run a workflow using the newly tagged released against production
   - Get approval for the action

## Deployment

[Terraform configuration](docs/terraform.md)

[Detailed CI documentation](docs/ci.md)

- Changes to the `main` branch are deployed to staging.
- Creating a new Github version and running a GitHub action is required for deploying to
  production.
