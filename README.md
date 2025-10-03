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

### Deployment

This Lambda function supports **two deployment methods** via AWS SAM:

#### Option 1: ZIP Deployment (Recommended)

Packages Python code and dependencies as a ZIP file:

```sh
sam build TNACaselawDocxStripAuthorFunctionZip --use-container
sam deploy --guided
```

#### Option 2: Container Deployment

Packages the Lambda as a Docker container:

```sh
sam build TNACaselawDocxStripAuthorFunctionContainer --use-container
sam deploy --guided
```

**Automated Deployment:**

- Deployment is managed via GitHub Actions on pushes to `main`
- See `.github/workflows/deploy-docx-strip-author.yml` for the CI/CD pipeline
- See `template.yml` for the complete AWS SAM template defining both deployment options

### Local Development, Testing, and Deployment

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

```sh
cd lambda_strip_docx
pytest
```

#### 4. Test Lambda End-to-End Locally

You can test both the ZIP-based and Docker (container) Lambda locally using AWS SAM CLI:

**a) ZIP-based Lambda:**

```sh
sam build -t template.yml --use-container -m lambda_strip_docx/requirements.txt
sam local invoke TNACaselawDocxStripAuthorFunctionZip -e test-event.json
```

**b) Docker/Container Lambda:**

```sh
sam build -t template.yml --use-container
sam local invoke TNACaselawDocxStripAuthorFunctionContainer -e test-event.json
```

Or, using Docker directly:

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

---

# Pre-commit and Repo Standards

This repository uses [pre-commit](https://pre-commit.com/) and [detect-secrets](https://github.com/Yelp/detect-secrets) to enforce code quality and prevent secrets leakage. See [The Engineering Handbook](https://national-archives.atlassian.net/wiki/spaces/DAAE/pages/47775767/Engineering+Handbook) for more details.

---

## Coming Soon

**PDF author metadata cleansing Lambda** will be added in a separate PR.
