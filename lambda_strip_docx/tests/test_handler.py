import urllib
import logging
from moto import mock_aws
from clean_docx import strip_docx_author_metadata_from_docx
from lambda_function import lambda_handler, __version__
from exceptions import VisuallyDifferentError
from unittest.mock import patch
import re

def create_s3_event(bucket_name="test-bucket", object_key="test.docx"):
    """Create a mock S3 event structure"""
    return {
        "Records": [
            {
                "eventID": "test-event-id",
                "s3": {
                    "bucket": {
                        "name": bucket_name
                    },
                    "object": {
                        "key": object_key
                    }
                }
            }
        ]
    }

class TestLambdaHandler:
    """Tests for the lambda_handler function"""
    def test_lambda_handler_processes_docx_files_without_version_tag(self, s3_with_docx_file, input_docx):
        """Test lambda handler processes files without a version tag"""
        s3_client, bucket_name, object_key = s3_with_docx_file

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler
        lambda_handler(event, {})

        # Get the processed file and verify it's different from original
        processed_response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        processed_content = processed_response['Body'].read()
        assert processed_content != input_docx
        assert len(processed_content) > 0

    def test_lambda_handler_processes_jpeg_files(self, s3_with_jpeg_file, input_jpeg):
        """Test lambda handler processes files without a version tag"""
        s3_client, bucket_name, object_key = s3_with_jpeg_file

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler
        lambda_handler(event, {})

        # Get the processed file and verify it's different from original
        processed_response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        processed_content = processed_response['Body'].read()
        assert processed_content != input_jpeg
        assert len(processed_content) > 0

    def test_lambda_handler_processes_png_files(self, s3_with_png_file, input_png):
        """Test lambda handler processes files without a version tag"""
        s3_client, bucket_name, object_key = s3_with_png_file

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler
        lambda_handler(event, {})

        # Get the processed file and verify it's different from original
        processed_response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        processed_content = processed_response['Body'].read()
        assert processed_content != input_png
        assert len(processed_content) > 0

    def test_lambda_handler_processes_pdf_files_without_version_tag(self, s3_with_multipage_pdf_file, input_multipage_pdf):
        # We use the multipage pdf because the normal PDF contains annotations which cause differences in output
        # which raise errors when we compare the images
        """Test lambda handler processes files without a version tag"""
        s3_client, bucket_name, object_key = s3_with_multipage_pdf_file

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler
        lambda_handler(event, {})

        # Get the processed file and verify it's different from original
        processed_response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        processed_content = processed_response['Body'].read()
        assert processed_content != input_multipage_pdf
        assert len(processed_content) > 0

    @patch("exceptions.VisuallyDifferentError")
    def test_lambda_handler_does_not_overwrite_visually_different_pdf_files(self, vis_diff_error, s3_with_pdf_file, input_pdf, caplog):
        """The default PDF file contains annotations which cause a visual difference when removed.
        Ensure that, at least for now, it does not cause the PDF to be saved with that difference"""
        s3_client, bucket_name, object_key = s3_with_pdf_file

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler: note the VisuallyDifferentError is caught and silenced.
        with caplog.at_level(logging.INFO):
            lambda_handler(event, {})

        # Get the processed file and verify it's same as original
        processed_response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        processed_content = processed_response['Body'].read()
        assert processed_content == input_pdf
        assert "exceptions.VisuallyDifferentError: S3 key sample_pdf_with_author.pdf was visually different after cleaning." in caplog.text




    def test_lambda_handler_skips_non_docx_files(self, s3_setup, caplog):
        """Test lambda handler skips non-DOCX files"""
        s3_client, bucket_name = s3_setup
        original_content = b"text file content"

        # Upload a non-DOCX file
        non_docx_key = "test.txt"
        s3_client.put_object(Bucket=bucket_name, Key=non_docx_key, Body=original_content)

        # Create S3 event for the non-DOCX file
        event = create_s3_event(bucket_name=bucket_name, object_key=non_docx_key)

        # Call lambda handler
        with caplog.at_level(logging.INFO):
            lambda_handler(event, {})

        # Verify the file was not modified (content should remain the same)
        response = s3_client.get_object(Bucket=bucket_name, Key=non_docx_key)
        current_content = response['Body'].read()
        assert current_content == original_content

        # Verify no version tag was added
        tag_response = s3_client.get_object_tagging(Bucket=bucket_name, Key=non_docx_key)
        tags = {tag['Key']: tag['Value'] for tag in tag_response.get('TagSet', [])}
        assert 'DOCUMENT_PROCESSOR_VERSION' not in tags

        # Verify expected log messages
        assert "Processing file: test.txt from bucket: test-bucket" in caplog.text
        assert "Skipping unrecognised unknown file: test.txt b'text '" in caplog.text

    def test_lambda_handler_handles_missing_file(self, s3_setup):
        """Test lambda handler handles missing S3 files gracefully"""
        s3_client, bucket_name = s3_setup

        # Create S3 event for a file that doesn't exist
        event = create_s3_event(bucket_name=bucket_name, object_key="nonexistent.docx")

        # Call lambda handler - should not raise exception
        lambda_handler(event, {})

        # Verify no processed files were created
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        contents = response.get('Contents', [])
        assert len(contents) == 0, "No files should be created when source file is missing"

    @patch("filetype.guess")
    def test_lambda_handler_handles_corrupted_docx_files(self, filetype_guess, s3_with_corrupted_file, caplog):
        """Test lambda handler handles corrupted DOCX files"""
        filetype_guess.return_value.mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        s3_client, bucket_name, object_key = s3_with_corrupted_file

        # Get original content before processing
        original_response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        original_content = original_response['Body'].read()

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler - should not raise exception
        with caplog.at_level(logging.INFO):
            lambda_handler(event, {})

        # Verify the file was not modified due to corruption
        current_response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        current_content = current_response['Body'].read()
        assert current_content == original_content

        # Verify no version tag was added
        tag_response = s3_client.get_object_tagging(Bucket=bucket_name, Key=object_key)
        tags = {tag['Key']: tag['Value'] for tag in tag_response.get('TagSet', [])}
        assert 'DOCUMENT_PROCESSOR_VERSION' not in tags

        # Verify expected log messages
        assert "Processing file: corrupted.docx from bucket: test-bucket" in caplog.text
        assert "File is not a valid DOCX (zip) file." in caplog.text

    def test_lambda_handler_processes_multiple_records(self, s3_setup, input_docx):
        """Test lambda handler processes multiple S3 records"""
        s3_client, bucket_name = s3_setup

        # Upload multiple DOCX files
        files = ["file1.docx", "file2.docx"]
        for file_key in files:
            s3_client.put_object(
                Bucket=bucket_name,
                Key=file_key,
                Body=input_docx,
                ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )

        # Create S3 event with multiple records
        event = {
            "Records": [
                {
                    "eventID": f"test-event-id-{i}",
                    "s3": {
                        "bucket": {"name": bucket_name},
                        "object": {"key": file_key}
                    }
                } for i, file_key in enumerate(files, 1)
            ]
        }

        # Call lambda handler
        lambda_handler(event, {})

        # Verify both files were processed in place
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        object_keys = [obj['Key'] for obj in response.get('Contents', [])]

        # Should still have exactly the original files (processed in place)
        assert set(files).issubset(set(object_keys))
        assert len(object_keys) == len(files)

        # Verify both files were actually processed (content changed and version tagged)
        for file_key in files:
            # Check content was processed
            processed_response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
            processed_content = processed_response['Body'].read()
            assert processed_content != input_docx

            # Check version tag was added
            tag_response = s3_client.get_object_tagging(Bucket=bucket_name, Key=file_key)
            tags = {tag['Key']: tag['Value'] for tag in tag_response.get('TagSet', [])}
            assert tags.get('DOCUMENT_PROCESSOR_VERSION') == __version__


    def test_lambda_handler_empty_records(self, s3_setup):
        """Test lambda handler handles empty Records gracefully"""
        s3_client, bucket_name = s3_setup

        # Create S3 event with no records
        event = {"Records": []}

        # Call lambda handler - should not raise exception
        lambda_handler(event, {})

        # Verify no files were created
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        contents = response.get('Contents', [])
        assert len(contents) == 0

    def test_lambda_handler_no_records_key(self, s3_setup):
        """Test lambda handler handles missing Records key gracefully"""
        s3_client, bucket_name = s3_setup

        # Create S3 event with no Records key
        event = {}

        # Call lambda handler - should not raise exception
        lambda_handler(event, {})

        # Verify no files were created
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        contents = response.get('Contents', [])
        assert len(contents) == 0

    def test_lambda_handler_skips_already_processed_files(self, s3_setup, input_docx):
        """Test lambda handler skips files that have already been processed with the current version"""
        s3_client, bucket_name = s3_setup
        object_key = "already_processed.docx"

        # First, process the file to get the processed content
        processed_bytes = strip_docx_author_metadata_from_docx(input_docx)

        # Upload a DOCX file with processed content and current version tag (simulating already processed file)
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=processed_bytes,
            ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            Tagging=f'DOCUMENT_PROCESSOR_VERSION={__version__}'
        )

        # Get modification time before lambda execution
        response_before = s3_client.head_object(Bucket=bucket_name, Key=object_key)
        last_modified_before = response_before['LastModified']

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler
        lambda_handler(event, {})

        # Verify file was not re-processed (content and metadata should be unchanged)
        response_after = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        current_content = response_after['Body'].read()
        current_last_modified = response_after['LastModified']

        # Content should remain the same (not re-processed)
        assert current_content == processed_bytes

        # Last modified time should be the same (file was not updated)
        assert current_last_modified == last_modified_before

        # Version tag should still be present and unchanged
        tag_response = s3_client.get_object_tagging(Bucket=bucket_name, Key=object_key)
        tags = {tag['Key']: tag['Value'] for tag in tag_response.get('TagSet', [])}
        assert tags.get('DOCUMENT_PROCESSOR_VERSION') == __version__

        # Verify we only have 1 file total (the original)
        list_response = s3_client.list_objects_v2(Bucket=bucket_name)
        object_keys = [obj['Key'] for obj in list_response.get('Contents', [])]
        assert len(object_keys) == 1

    def test_lambda_handler_processes_files_with_different_major_version(self, s3_setup, input_docx):
        """Test lambda handler processes files that have a different major version tag"""
        s3_client, bucket_name = s3_setup
        object_key = "old_major_version.docx"

        current_major = __version__.split('.')[0]
        version = f"1{current_major[1:]}.0.0"

        # Upload a DOCX file with a different major version tag
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=input_docx,
            ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            Tagging=f'DOCUMENT_PROCESSOR_VERSION={version}'
        )

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler
        lambda_handler(event, {})

        # Verify the file was re-processed (content should be different from original)
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        processed_content = response['Body'].read()
        assert processed_content != input_docx

        # Verify the file has the current version tag
        tag_response = s3_client.get_object_tagging(Bucket=bucket_name, Key=object_key)
        tags = {tag['Key']: tag['Value'] for tag in tag_response['TagSet']}
        assert tags['DOCUMENT_PROCESSOR_VERSION'] == __version__

        # Verify we only have 1 file total (the original, processed in place)
        list_response = s3_client.list_objects_v2(Bucket=bucket_name)
        object_keys = [obj['Key'] for obj in list_response.get('Contents', [])]
        assert len(object_keys) == 1
        assert object_key in object_keys

    def test_lambda_handler_skips_files_with_same_major_version(self, s3_setup, input_docx, caplog):
        """Test lambda handler skips files that have the same major version but different minor/patch version"""
        s3_client, bucket_name = s3_setup
        object_key = "same_major_version.docx"

        # Create a version with same major version but different minor/patch
        current_major = __version__.split('.')[0]
        version = f"{current_major}.2.5"

        # First, process the file to get the processed content
        processed_bytes = strip_docx_author_metadata_from_docx(input_docx)

        # Upload a DOCX file with same major version but different minor/patch
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=processed_bytes,
            ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            Tagging=f'DOCUMENT_PROCESSOR_VERSION={version}'
        )

        # Get modification time before lambda execution
        response_before = s3_client.head_object(Bucket=bucket_name, Key=object_key)
        last_modified_before = response_before['LastModified']

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler
        with caplog.at_level(logging.INFO):
            lambda_handler(event, {})

        # Verify file was not re-processed (content and metadata should be unchanged)
        response_after = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        current_content = response_after['Body'].read()
        current_last_modified = response_after['LastModified']

        # Content should remain the same (not re-processed)
        assert current_content == processed_bytes

        # Last modified time should be the same (file was not updated)
        assert current_last_modified == last_modified_before

        # Version tag should still be the old one (unchanged)
        tag_response = s3_client.get_object_tagging(Bucket=bucket_name, Key=object_key)
        tags = {tag['Key']: tag['Value'] for tag in tag_response.get('TagSet', [])}
        assert tags.get('DOCUMENT_PROCESSOR_VERSION') == version

        # Verify the log message indicates skipping due to compatible version
        assert f"has already been processed with compatible version {version}" in caplog.text
        assert f"current: {__version__}" in caplog.text

    def test_lambda_handler_handles_malformed_version_tags(self, s3_setup, input_docx):
        """Test lambda handler handles malformed version tags gracefully"""
        s3_client, bucket_name = s3_setup
        object_key = "malformed_version.docx"

        # Use a malformed version that can't be parsed normally
        malformed_version = "invalid-version-format"

        # Upload a DOCX file with a malformed version tag
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=input_docx,
            ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            Tagging=f'DOCUMENT_PROCESSOR_VERSION={malformed_version}'
        )

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler - should not crash
        lambda_handler(event, {})

        # Verify the file was processed (since version comparison should fail gracefully and default to processing)
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        processed_content = response['Body'].read()
        assert processed_content != input_docx

        # Verify the file has the current version tag
        tag_response = s3_client.get_object_tagging(Bucket=bucket_name, Key=object_key)
        tags = {tag['Key']: tag['Value'] for tag in tag_response['TagSet']}
        assert tags['DOCUMENT_PROCESSOR_VERSION'] == __version__

    def test_version_number_is_uri_safe(self):
        """AWS expects the tag to be URI encoded; ensure that it is URI-safe for our convenience.
        https://boto3.amazonaws.com/v1/documentation/api/1.28.3/reference/services/s3/client/put_object.html"""
        assert __version__ == urllib.parse.quote_plus(__version__)
