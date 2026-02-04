# CHANGELOG

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

It is part of the [TRE template repository](https://github.com/nationalarchives/da-tre-template)

## [1.1.0] - 2026-01-23

### Added

- Added SQS and DLQ buffering layer for message processing resilience

### Fixed

- Set mimetype of docx files to "binary/octet-stream" like the original files to ensure backwards compatability with browser file download behaviour in the Microsoft Edge browser (Edge attempts to preview Word Documents in browser so we avoid that)

## [1.0.0] - 2026-01-23

### Added

- Document cleaning functionality for DOCX, PDF, PNG, and JPEG files
- AWS Lambda function for automated document processing
- Visual comparison checks for all document types (DOCX, PDF, PNG, JPEG)
- PDF rendering and cleaning capabilities with annotation and metadata removal
- Image metadata cleaning for PNG and JPEG files with ICC profile preservation

## [0.0.1] - 2025-11-31

### Added

- The keep a change log CHANGELOG

### Fixed

- Minor typos
