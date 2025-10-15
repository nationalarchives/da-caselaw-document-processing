#!/bin/bash

# Script to run tests locally in Docker container
# Usage: ./run-tests.sh

set -e

echo "🔨 Building test Docker image..."
docker build --target test -t document-cleaner-test lambda_strip_docx/

echo "🧪 Running tests in Docker container..."
docker run --rm document-cleaner-test

echo "✅ Tests completed!"
