# DA Caselaw Document Processing

AWS Lambda function for document processing (privacy, metadata stripping, etc.).

## Local Development and Testing

#### 1. Python Environment

It is strongly recommended to use a Python virtual environment to ensure reproducibility and isolation:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

#### 2. Install Dependencies

#### 3. Run Tests in Docker container (matches CI/CD)

```sh
# From project root
./run-tests.sh
```

This builds the test Docker image with all required system dependencies (including pdfcpu for PDF processing) and runs the complete test suite in the same environment used in CI/CD, ensuring consistency between local development and deployment.

#### 4. Test Lambda Locally

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

## Deployment

[Terraform configuration](docs/terraform.md)
[Detailed documentation](docs/ci.md)

- Changes to the `main` branch are deployed to staging.
- Creating a new Github version deploys to production.