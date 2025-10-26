# Base stage - common setup
FROM public.ecr.aws/lambda/python:3.13@sha256:1512a39bdac0d141114ec3d8f10371b79af088f9ce6026c10a503ba429e806f3 AS base

# Install system dependencies for PDF processing tests
RUN microdnf update -y && \
    microdnf install -y \
        wget-1.21.3-1.amzn2023.0.4 \
        golang-1.24.7-1.amzn2023.0.1 \
        qpdf-10.6.3-4.amzn2023.0.4 \
        perl-4:5.32.1-477.amzn2023.0.7 \
        make-1:4.3-5.amzn2023.0.2 \
        tar-2:1.34-1.amzn2023.0.4 \
        gzip-1.12-1.amzn2023.0.1 && \
    microdnf clean all

# Install ExifTool from GitHub releases
RUN wget https://github.com/exiftool/exiftool/archive/refs/tags/13.38.tar.gz && \
    tar -xzf 13.38.tar.gz && \
    cd exiftool-13.38 && \
    perl Makefile.PL && \
    make && \
    make install && \
    cd .. && \
    rm -rf exiftool-13.38 13.38.tar.gz

# Install pdfcpu to /usr/local/bin (accessible by Lambda runtime user)
RUN go install github.com/pdfcpu/pdfcpu/cmd/pdfcpu@v0.11.0 && \
    cp /root/go/bin/pdfcpu /usr/local/bin/ && \
    chmod 755 /usr/local/bin/pdfcpu && \
    rm -rf /root/go

# Install Poetry
RUN pip install --upgrade pip==25.2 && \
    pip install poetry==2.2.0

# Configure Poetry and install dependencies
ENV POETRY_NO_INTERACTION=1

COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false && \
    poetry install --only=main --no-root

# Copy function code
COPY . /var/task/

# Test stage - for running tests locally and in CI
FROM base AS test

# Install test dependencies using Poetry
RUN poetry install --with=dev --no-root

# Override the entrypoint for tests
ENTRYPOINT []
# Default command for test stage - run all pytest tests
CMD ["python", "-m", "pytest", "tests/"]

# Production stage - minimal runtime image
FROM base AS production

# Set the CMD to your handler
CMD ["lambda_function.lambda_handler"]
