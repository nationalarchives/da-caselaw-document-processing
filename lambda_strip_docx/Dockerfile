# Multi-stage Dockerfile for both Lambda deployment and development/testing
FROM public.ecr.aws/lambda/python:3.13@sha256:a0ca8c190db48ddbb341ce893f4a4ecf04b1adf9b696e0b26066c29211e4cdff AS lambda-base

# Install Python dependencies for Lambda
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY lambda_function.py /var/task/

# Set the CMD to your handler
CMD ["lambda_function.lambda_handler"]

# Development/Testing stage
FROM python:3.13-slim AS development

# Install system dependencies for visual regression testing
RUN apt-get update && apt-get install -y \
    libreoffice \
    imagemagick \
    ghostscript \
    fonts-liberation \
    fonts-dejavu-core \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Configure ImageMagick to allow PDF processing
RUN find /etc -name "policy.xml" -type f -exec sed -i '/disable ghostscript format types/,+6d' {} \; 2>/dev/null || true && \
    find /etc -name "policy.xml" -type f -exec sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' {} \; 2>/dev/null || true

# Set up working directory
WORKDIR /app

# Install Python dependencies (both runtime and dev)
COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install -r requirements-dev.txt

# Copy all source code and tests
COPY . .

# Create directory for test outputs
RUN mkdir -p /app/test_outputs

# Set environment variables
ENV PYTHONPATH=/app
ENV MPLBACKEND=Agg

# Default command for development (can be overridden)
CMD ["python", "-m", "pytest", "-v"]

# Production Lambda stage (default)
FROM lambda-base AS production
