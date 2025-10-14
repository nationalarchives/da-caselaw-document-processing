# Base stage - common setup
FROM public.ecr.aws/lambda/python:3.13@sha256:ac4766a9047fed7306ed92aedc567c4b5114cdfee591d3d5e3f0cabd89f0acc6 AS base

# Install system dependencies for PDF processing tests
RUN dnf update -y && \
    dnf install -y wget golang qpdf perl make tar gzip && \
    dnf clean all

# Install ExifTool from GitHub releases
RUN wget https://github.com/exiftool/exiftool/archive/refs/tags/12.96.tar.gz && \
    tar -xzf 12.96.tar.gz && \
    cd exiftool-12.96 && \
    perl Makefile.PL && \
    make && \
    make install && \
    cd .. && \
    rm -rf exiftool-12.96 12.96.tar.gz

# Install pdfcpu (required for PDF processing tests)
RUN go install github.com/pdfcpu/pdfcpu/cmd/pdfcpu@latest
ENV PATH="/root/go/bin:${PATH}"

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt --target "/var/task"

# Copy function code
COPY . /var/task/

# Test stage - for running tests locally and in CI
FROM base AS test

# Install test dependencies
COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt --target "/var/task"

# Override the entrypoint for tests
ENTRYPOINT []
# Default command for test stage - run all pytest tests
CMD ["python", "-m", "pytest", "tests/", "-vvv"]

# Production stage - minimal runtime image
FROM base AS production

# Set the CMD to your handler
CMD ["lambda_function.lambda_handler"]
