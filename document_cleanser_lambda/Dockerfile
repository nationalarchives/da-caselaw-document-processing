# Base stage - common setup
FROM public.ecr.aws/lambda/python:3.14@sha256:b36fc51af756d0ce015b717154f3b1237f2ae37904ef9171203621826a9f55e0 AS base

# get arm64 -> aarch64 / amd64 -> x86_64 for LibreOffice download path
ARG TARGETARCH

ENV LIBREOFFICE=26.2.2.2
ENV LIBREOFFICE_MAJOR=26.2
# Set HOME to /tmp to avoid permission issues during builds
ENV HOME=/tmp

# Install system dependencies for PDF processing tests
RUN microdnf install -y \
        # Utility dependencies needed for installing dependencies
        tar-2:1.34-1.amzn2023.0.4 \
        gzip-1.12-1.amzn2023.0.1 \
        wget-1.21.3-1.amzn2023.0.4 \
        # Poppler utils for pdf2image
        poppler-utils-22.08.0-3.amzn2023.0.1 \
        # Dependencies needed for LibreOffice
        libXinerama-1.1.5-6.amzn2023.0.1 \
        cups-libs-2.4.14-1.amzn2023.0.2 \
        dbus-glib-0.110-11.amzn2023.0.2 \
        libxslt-1.1.43-1.amzn2023.0.3 \
        openssl-3.2.2-1.amzn2023.0.4 \
        nss-3.90.0-6.amzn2023.0.1 \
        cairo-1.18.0-4.amzn2023.0.2 \
        libX11-xcb-1.8.10-2.amzn2023.0.1 \
        # Dependencies needed for ExifTool
        perl-4:5.32.1-477.amzn2023.0.7 \
        make-1:4.3-5.amzn2023.0.2 \
        # Dependencies needed for pdfcpu
        golang-1.24.9-1.amzn2023.0.1 \
        # QPDF for PDF processing
        qpdf-10.6.3-4.amzn2023.0.5 \
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
RUN ARCH=$(echo "${TARGETARCH}" | sed s/^arm64$/aarch64/ | sed s/^amd64$/x86_64/) ARCHHYPHEN=$(echo "${TARGETARCH}" | sed s/^arm64$/aarch64/ | sed s/^amd64$/x86-64/) sh -c "wget -v https://downloadarchive.documentfoundation.org/libreoffice/old/\${LIBREOFFICE}/rpm/\${ARCH}/LibreOffice_\${LIBREOFFICE}_Linux_\${ARCHHYPHEN}_rpm.tar.gz -O libreoffice.tar.gz"

RUN tar -xzf libreoffice.tar.gz && \
    cd LibreOffice_*/  && \
    cd RPMS/ && \
    rpm -Uvh *.rpm && \
    cd ../.. && \
    rm -rf LibreOffice_* libreoffice.tar.gz

RUN export LD_LIBRARY_PATH=:/usr/lib/libreoffice${LIBREOFFICE_MAJOR}/program
RUN ln -sf /opt/libreoffice${LIBREOFFICE_MAJOR}/program/soffice /usr/bin/soffice

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
