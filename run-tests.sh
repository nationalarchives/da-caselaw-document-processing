#!/bin/bash

# Script to run tests locally in Docker container
# Usage: ./run-tests.sh

set -e

PLATFORM="linux/amd64"

echo "🔨 Building test Docker image..."
docker buildx create --use --name run-tests-builder >/dev/null 2>&1 || true
docker buildx inspect --bootstrap >/dev/null 2>&1 || true
docker run --rm --privileged tonistiigi/binfmt:latest --install all >/dev/null 2>&1 || true

echo "Building for platform: $PLATFORM"
docker buildx build \
	--platform "$PLATFORM" \
	--target test \
	-t document-cleaner-test \
	--load \
	-f lambda_strip_docx/Dockerfile \
	lambda_strip_docx/

echo "🧪 Running tests in Docker container..."
docker run --rm document-cleaner-test

echo "✅ Tests completed!"
