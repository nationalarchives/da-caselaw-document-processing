import os
import pytest
import boto3
from moto import mock_aws
from handler import strip_docx_author_metadata_from_docx, lambda_handler

def load_docx_bytes(filename):
    with open(filename, "rb") as f:
        return f.read()

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

# Fixtures
@pytest.fixture
def sample_docx_path():
    """Path to the sample DOCX file with author metadata"""
    return os.path.join(os.path.dirname(__file__), "test_files", "sample_with_author.docx")

@pytest.fixture
def input_bytes(sample_docx_path):
    """Load sample DOCX file as bytes"""
    return load_docx_bytes(sample_docx_path)

@pytest.fixture
def s3_bucket_name():
    """S3 bucket name for testing"""
    return "test-bucket"

@pytest.fixture
def s3_setup(s3_bucket_name):
    """Setup mocked S3 environment with bucket"""
    with mock_aws():
        # Create S3 client and bucket
        s3_client = boto3.client('s3', region_name='us-east-1')
        s3_client.create_bucket(Bucket=s3_bucket_name)
        yield s3_client, s3_bucket_name

@pytest.fixture
def s3_with_docx_file(s3_setup, input_bytes):
    """S3 environment with a DOCX file uploaded"""
    s3_client, bucket_name = s3_setup
    object_key = "sample_with_author.docx"

    # Upload the DOCX file to S3
    s3_client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=input_bytes,
        ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )

    return s3_client, bucket_name, object_key

@pytest.fixture
def s3_with_corrupted_file(s3_setup):
    """S3 environment with a corrupted DOCX file"""
    s3_client, bucket_name = s3_setup
    object_key = "corrupted.docx"

    # Upload corrupted content as DOCX
    s3_client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=b"corrupted docx content",
        ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )

    return s3_client, bucket_name, object_key

class TestStripDocxAuthorMetadata:
    """Tests for the strip_docx_author_metadata function"""
    def test_strip_docx_author_removes_metadata(self, input_bytes):
        """Test that all author metadata is properly stripped from DOCX files while preserving text content"""
        from zipfile import ZipFile
        import io
        import re

        # List of all author names that should be removed from metadata but may remain in text content
        expected_authors = ["Alice Johnson", "Bob Smith", "Carol Davis"]

        # Define the forbidden attributes and tags that should be redacted
        forbidden_attributes = ["w15:author", "w15:userId", "w:author", "w:initials"]
        forbidden_tags = ["cp:lastModifiedBy", "dc:creator"]

        # Process the input bytes to remove author metadata
        output_bytes = strip_docx_author_metadata_from_docx(input_bytes)

        # Basic sanity checks
        assert len(output_bytes) > 0, "Output should not be empty"
        assert output_bytes != input_bytes, "Output should be different from input after processing"

        # Verify it's still a valid DOCX file structure
        with ZipFile(io.BytesIO(output_bytes), "r") as archive:
            file_list = archive.namelist()
            assert "word/document.xml" in file_list, "Missing core document.xml"
            assert "[Content_Types].xml" in file_list, "Missing Content_Types.xml"
            assert "docProps/core.xml" in file_list, "Missing core.xml metadata file"

        # Verify author metadata has been stripped from all XML files
        with ZipFile(io.BytesIO(output_bytes), "r") as archive:
            # Check document properties metadata - should be completely empty
            with archive.open("docProps/core.xml", "r") as f:
                core_xml = f.read().decode('utf-8')

                # All forbidden tags should be empty
                for tag in forbidden_tags:
                    tag_prefix, tag_name = tag.split(":")
                    # Check for both self-closing and empty tags
                    empty_patterns = [
                        f"<{tag}></{tag}>",  # Empty tag
                        f"<{tag}/>",         # Self-closing tag
                        f"<{tag}\\s*/>"      # Self-closing with whitespace
                    ]

                    tag_found = any(re.search(pattern, core_xml) for pattern in empty_patterns)
                    assert tag_found, f"Tag '{tag}' should be empty in core metadata, but found: {re.findall(f'<{re.escape(tag)}[^>]*>.*?</{re.escape(tag)}>', core_xml)}"

                # No author names should remain in metadata tags
                for author in expected_authors:
                    assert author not in core_xml, f"Author '{author}' should not be present in core metadata"

            # Check main document - author attributes should be empty but text content preserved
            with archive.open("word/document.xml", "r") as f:
                doc_xml = f.read().decode('utf-8')

                # All forbidden attributes should be empty strings
                for attr in forbidden_attributes:
                    # Find all instances of this attribute and verify they're empty
                    attr_pattern = f'{re.escape(attr)}="([^"]*)"'
                    attr_values = re.findall(attr_pattern, doc_xml)

                    # All attribute values should be empty strings
                    for value in attr_values:
                        assert value == "", f"Attribute '{attr}' should be empty but found value: '{value}'"

                    # Also check that we don't have any non-empty attribute values
                    non_empty_pattern = f'{re.escape(attr)}="[^"]+[^"]"'
                    non_empty_matches = re.findall(non_empty_pattern, doc_xml)
                    assert len(non_empty_matches) == 0, f"Found non-empty {attr} attributes: {non_empty_matches}"

            # Check comments file - author attributes should be empty but comment text preserved
            if "word/comments.xml" in archive.namelist():
                with archive.open("word/comments.xml", "r") as f:
                    comments_xml = f.read().decode('utf-8')

                    # All forbidden attributes in comments should be empty
                    for attr in forbidden_attributes:
                        attr_pattern = f'{re.escape(attr)}="([^"]*)"'
                        attr_values = re.findall(attr_pattern, comments_xml)

                        for value in attr_values:
                            assert value == "", f"Comment attribute '{attr}' should be empty but found value: '{value}'"

                    # Verify that comment text content is preserved (comments should still have meaningful text)
                    assert "<w:t>" in comments_xml, "Comment text content should be preserved"

            # Verify that the document still contains the actual text content
            # (to ensure we're not over-redacting and removing legitimate content)
            with archive.open("word/document.xml", "r") as f:
                doc_xml = f.read().decode('utf-8')
                # The document should still contain text elements
                assert "<w:t>" in doc_xml, "Document text content should be preserved"
                # Should contain some meaningful text (not just empty tags)
                text_content = re.findall(r'<w:t>([^<]*)</w:t>', doc_xml)
                meaningful_text = [t.strip() for t in text_content if t.strip()]
                assert len(meaningful_text) > 0, "Document should contain meaningful text content"

    def test_strip_docx_author_rejects_non_docx(self):
        """Test that non-DOCX files raise appropriate exceptions"""
        with pytest.raises(Exception):
            strip_docx_author_metadata_from_docx(b"not a docx file")

    def test_comprehensive_coverage_detects_violations(self, input_bytes):
        """Test that our comprehensive test would catch violations if redaction failed"""
        from zipfile import ZipFile
        import io

        # Test with original (unprocessed) bytes to ensure our test would catch violations
        with ZipFile(io.BytesIO(input_bytes), "r") as archive:
            # Verify that the original file DOES contain forbidden content
            # This proves our comprehensive test above is actually checking the right things

            # Check that original file has author names in metadata
            with archive.open("docProps/core.xml", "r") as f:
                core_xml = f.read().decode('utf-8')
                assert any(author in core_xml for author in ["Alice Johnson", "Bob Smith", "Carol Davis"]), \
                    "Original file should contain author names in metadata (test file verification)"

            # Check that original file has non-empty author attributes
            with archive.open("word/document.xml", "r") as f:
                doc_xml = f.read().decode('utf-8')
                # Original should have non-empty author attributes
                import re
                w_author_values = re.findall(r'w:author="([^"]*)"', doc_xml)
                w15_author_values = re.findall(r'w15:author="([^"]*)"', doc_xml)

                # At least some should be non-empty in the original
                non_empty_authors = [v for v in w_author_values + w15_author_values if v.strip()]
                assert len(non_empty_authors) > 0, \
                    "Original file should have non-empty author attributes (test file verification)"

            # Check comments file for initials
            if "word/comments.xml" in archive.namelist():
                with archive.open("word/comments.xml", "r") as f:
                    comments_xml = f.read().decode('utf-8')
                initials_values = re.findall(r'w:initials="([^"]*)"', comments_xml)
                non_empty_initials = [v for v in initials_values if v.strip()]
                assert len(non_empty_initials) > 0, \
                    "Original file should have non-empty initials (test file verification)"

class TestLambdaHandler:
    """Tests for the lambda_handler function"""
    def test_lambda_handler_successful_processing(self, s3_with_docx_file, input_bytes):
        """Test lambda handler successfully processes DOCX files from S3"""
        s3_client, bucket_name, object_key = s3_with_docx_file

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler
        lambda_handler(event, {})

        # Verify the processed file was uploaded
        processed_key = "sample_with_author_processed.docx"

        # Check that processed file exists
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        object_keys = [obj['Key'] for obj in response.get('Contents', [])]
        assert processed_key in object_keys, f"Processed file {processed_key} not found in S3"

        # Get the processed file and verify it's different from original
        processed_response = s3_client.get_object(Bucket=bucket_name, Key=processed_key)
        processed_content = processed_response['Body'].read()

        assert processed_content != input_bytes, "Processed content should be different from input"
        assert len(processed_content) > 0, "Processed content should not be empty"

    def test_lambda_handler_skips_non_docx_files(self, s3_setup):
        """Test lambda handler skips non-DOCX files"""
        s3_client, bucket_name = s3_setup

        # Upload a non-DOCX file
        non_docx_key = "test.txt"
        s3_client.put_object(Bucket=bucket_name, Key=non_docx_key, Body=b"text file content")

        # Create S3 event for the non-DOCX file
        event = create_s3_event(bucket_name=bucket_name, object_key=non_docx_key)

        # Call lambda handler
        lambda_handler(event, {})

        # Verify no processed file was created
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        object_keys = [obj['Key'] for obj in response.get('Contents', [])]
        processed_keys = [key for key in object_keys if "_processed" in key]
        assert len(processed_keys) == 0, "No processed files should be created for non-DOCX files"

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

    def test_lambda_handler_handles_corrupted_docx_files(self, s3_with_corrupted_file):
        """Test lambda handler handles corrupted DOCX files"""
        s3_client, bucket_name, object_key = s3_with_corrupted_file

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler - should not raise exception
        lambda_handler(event, {})

        # Verify no processed file was created due to corruption
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        object_keys = [obj['Key'] for obj in response.get('Contents', [])]
        processed_keys = [key for key in object_keys if "_processed" in key]
        assert len(processed_keys) == 0, "No processed files should be created for corrupted DOCX files"

    def test_lambda_handler_processes_multiple_records(self, s3_setup, input_bytes):
        """Test lambda handler processes multiple S3 records"""
        s3_client, bucket_name = s3_setup

        # Upload multiple DOCX files
        files = ["file1.docx", "file2.docx"]
        for file_key in files:
            s3_client.put_object(
                Bucket=bucket_name,
                Key=file_key,
                Body=input_bytes,
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

        # Verify both processed files were created
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        object_keys = [obj['Key'] for obj in response.get('Contents', [])]

        expected_processed_files = ["file1_processed.docx", "file2_processed.docx"]
        assert set(expected_processed_files).issubset(set(object_keys)), "Not all processed files found in S3"


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
        assert len(contents) == 0, "No files should be created when there are no records"

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
        assert len(contents) == 0, "No files should be created when Records key is missing"
