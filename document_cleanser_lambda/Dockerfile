# Base stage - common setup
FROM public.ecr.aws/lambda/python:3.13@sha256:47b6c63b5a03a6748ee0a98335977a2fef17c07915fabe88547e1b925cda5433 AS base

# Set HOME to /tmp to avoid permission issues during builds
ENV HOME=/tmp

# Install system dependencies for PDF processing tests
RUN microdnf update -y && \
    microdnf install -y \
        # Utility dependencies needed for installing dependencies
        tar-2:1.34-1.amzn2023.0.4 \
        gzip-1.12-1.amzn2023.0.1 \
        wget-1.21.3-1.amzn2023.0.4 \
        # Dependencies needed for LibreOffice
        libXinerama \
        cups-libs \
        dbus-glib \
        libxslt \
        openssl \
        nss \
        cairo \
        libX11-xcb \
        # Dependencies needed for ExifTool
        perl-4:5.32.1-477.amzn2023.0.7 \
        make-1:4.3-5.amzn2023.0.2 \
        # Dependencies needed for pdfcpu
        golang-1.24.7-1.amzn2023.0.1 \
        # QPDF for PDF processing
        qpdf-10.6.3-4.amzn2023.0.4 \
        && \
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

# Verify ExifTool installation
RUN exiftool -ver

# Install pdfcpu to /usr/local/bin (accessible by Lambda runtime user)
RUN go install github.com/pdfcpu/pdfcpu/cmd/pdfcpu@v0.11.1 && \
    cp /tmp/go/bin/pdfcpu /usr/local/bin/ && \
    chmod 755 /usr/local/bin/pdfcpu && \
    rm -rf /root/go && \
    rm -rf /usr/lib/golang

# Verify pdfcpu installation
RUN pdfcpu version


# Install LibreOffice headless
RUN wget https://download.documentfoundation.org/libreoffice/stable/25.8.2/rpm/x86_64/LibreOffice_25.8.2_Linux_x86-64_rpm.tar.gz

RUN tar -xzf LibreOffice_25.8.2_Linux_x86-64_rpm.tar.gz && \
    cd LibreOffice_25.8.2.2_Linux_x86-64_rpm/  && \
    cd RPMS/ && \
    rpm -Uvh *.rpm && \
    cd ../.. && \
    rm -rf LibreOffice_25.8.2_Linux_x86-64_rpm LibreOffice_25.8.2_Linux_x86-64_rpm.tar.gz

RUN export LD_LIBRARY_PATH=:/usr/lib/libreoffice25.8/program
RUN ln -sf /opt/libreoffice25.8/program/soffice /usr/bin/soffice

# Verify LibreOffice installation
RUN /usr/bin/soffice --version

# Install Poetry
RUN pip install --upgrade pip==25.2 --no-cache-dir && \
    pip install poetry==2.2.0 --no-cache-dir

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
RUN poetry install --with dev --no-root

# Override the entrypoint for tests
ENTRYPOINT []
# Default command for test stage - run all pytest tests
CMD ["poetry", "run", "python", "-m", "pytest", "tests/"]

# Production stage - minimal runtime image
FROM base AS production

# Set the CMD to your handler
CMD ["lambda_function.lambda_handler"]
