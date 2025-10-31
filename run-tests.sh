#!/bin/bash

# Script to run tests locally in Docker container
# Usage: ./run-tests.sh [--platform linux/amd64|linux/arm64]

set -euo pipefail

PLATFORM=""
while [[ $# -gt 0 ]]; do
	case "$1" in
		--platform)
			PLATFORM="$2"
			shift 2
			;;
		-h|--help)
			echo "Usage: $0 [--platform linux/amd64|linux/arm64]"; exit 0
			;;
		*) echo "Unknown arg: $1"; exit 1 ;;
	esac
done

echo "🔨 Building test Docker image..."
if [ -n "$PLATFORM" ]; then
	if ! docker buildx version >/dev/null 2>&1; then
		echo "ERROR: docker buildx not available. Please enable Docker Buildx." >&2
		exit 1
	fi

	docker buildx create --use --name run-tests-builder >/dev/null 2>&1 || true
	docker buildx inspect --bootstrap >/dev/null 2>&1 || true
	docker run --rm --privileged tonistiigi/binfmt:latest --install all >/dev/null 2>&1 || true

	echo "Building for platform: $PLATFORM"
	docker buildx build \
		--platform "$PLATFORM" \
		--build-arg TARGETARCH=$(echo "$PLATFORM" | awk -F/ '{print $2}') \
		--target test \
		-t document-cleaner-test:$(echo "$PLATFORM" | tr '/' '-') \
		--load \
		-f lambda_strip_docx/Dockerfile \
		lambda_strip_docx/
else
	docker build --target test -t document-cleaner-test lambda_strip_docx/
fi

echo "🧪 Running tests in Docker container..."
if [ -n "$PLATFORM" ]; then
	docker run --rm document-cleaner-test:$(echo "$PLATFORM" | tr '/' '-')
else
	docker run --rm document-cleaner-test
fi

echo "✅ Tests completed!"
