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

Ensure all tests pass locally before opening a PR via `./run-tests.sh`

Follow repo and code style guidelines.

Document new environment variables or requirements in the README.

## Deployment

[Terraform configuration](docs/terraform.md)

[Detailed CI documentation](docs/ci.md)

- Changes to the `main` branch are deployed to staging.
- Creating a new Github version deploys to production.
