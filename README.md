# DA Caselaw Document Processing

AWS Lambda function for document processing (privacy, metadata stripping, etc.).

## Local Development and Testing

#### 1. Run Tests in Docker container (matches CI/CD)

```sh
# From project root
./run-tests.sh
```

This builds the test Docker image with all required system dependencies (including pdfcpu for PDF processing) and runs the complete test suite in the same environment used in CI/CD, ensuring consistency between local development and deployment.

#### 2. Test Lambda Locally

You can test the Lambda locally using Docker:

```sh
docker build -t docx-lambda-test -f **document_cleanser_lambda**/Dockerfile document_cleanser_lambda/
docker run -d --name docx-lambda-test -p 9000:8080 docx-lambda-test
sleep 10
curl -s -X POST "http://localhost:9000/2015-03-31/functions/function/invocations" \
	-H "Content-Type: application/json" \
	--data-binary @test-event.json > response.json
```

`test-event.json` should be a valid Lambda event payload for your handler (see AWS docs for examples).

#### 3. Linting and Pre-commit

Install and run pre-commit hooks to ensure code quality:

```sh
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

#### 4. Making Changes & Pull Requests

- Ensure all tests pass locally before opening a PR.
- Follow repo and code style guidelines.
- Document any new environment variables or requirements in the README.

#### 5. Development Guidelines

- If you need to update dependencies, run `poetry update`; see [pyproject.toml](pyproject.toml)
- Ensure all tests pass locally before opening a PR via `./run-tests.sh`
- Follow repo and code style guidelines.
- Document any new environment variables or requirements in the README.

## Deployment

[Terraform configuration](docs/terraform.md)
[Detailed CI documentation](docs/ci.md)

- Changes to the `main` branch are deployed to staging.
- Creating a new Github version deploys to production.
