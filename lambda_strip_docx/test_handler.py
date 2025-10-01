import os
import pytest
import boto3
import logging
from moto import mock_aws
from zipfile import ZipFile
import io
import re
from lambda_function import strip_docx_author_metadata_from_docx, lambda_handler, __version__

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

def assert_docx_metadata_is_stripped(docx_bytes):
    """Helper function to assert that DOCX metadata has been properly stripped"""
    # Define the forbidden attributes and tags that should be redacted
    forbidden_attributes = ["w15:author", "w15:userId", "w:author", "w:initials"]
    forbidden_tags = ["cp:lastModifiedBy", "dc:creator"]

    # Verify author metadata has been stripped from all XML files
    with ZipFile(io.BytesIO(docx_bytes), "r") as archive:
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


class TestStripDocxAuthorMetadata:
    """Tests for the strip_docx_author_metadata function"""
    def test_strip_docx_author_removes_metadata(self, input_bytes):
        """Test that all author metadata is properly stripped from DOCX files while preserving text content"""

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

        # Use the extracted assertion function to verify metadata is stripped
        assert_docx_metadata_is_stripped(output_bytes)

    def test_strip_docx_author_rejects_non_docx(self):
        """Test that non-DOCX files raise appropriate exceptions"""
        with pytest.raises(Exception):
            strip_docx_author_metadata_from_docx(b"not a docx file")

    def test_assertion_function_detects_violations(self, input_bytes):
        """Test that our assertion function correctly detects violations when metadata is NOT stripped"""

        # Test with original (unprocessed) bytes - this should fail the assertions
        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(input_bytes)

        # Verify the assertion error contains meaningful information about what was found
        error_message = str(exc_info.value)
        assert "should not be present" in error_message or "should be empty" in error_message, \
            f"Assertion error should indicate metadata violation, got: {error_message}"


class TestAssertDocxMetadataIsStripped:
    """Comprehensive tests for the assert_docx_metadata_is_stripped function"""

    def create_mock_docx_with_author_in_core(self, author_name="John Doe"):
        """Create a minimal DOCX with author in core metadata"""
        # Create a minimal DOCX structure with author metadata
        docx_buffer = io.BytesIO()
        with ZipFile(docx_buffer, 'w') as zf:
            # Content Types
            zf.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>''')

            # Main document
            zf.writestr("word/document.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p>
            <w:r>
                <w:t>Test document content</w:t>
            </w:r>
        </w:p>
    </w:body>
</w:document>''')

            # Core properties with author
            zf.writestr("docProps/core.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:dcmitype="http://purl.org/dc/dcmitype/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <dc:creator>{author_name}</dc:creator>
    <cp:lastModifiedBy>{author_name}</cp:lastModifiedBy>
</cp:coreProperties>''')

            # Relationships
            zf.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>''')

        docx_buffer.seek(0)
        return docx_buffer.getvalue()

    def create_mock_docx_with_document_author_attributes(self, author="Jane Smith", initials="JS"):
        """Create a minimal DOCX with author attributes in document.xml"""
        docx_buffer = io.BytesIO()
        with ZipFile(docx_buffer, 'w') as zf:
            # Content Types
            zf.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>''')

            # Main document with author attributes
            zf.writestr("word/document.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">
    <w:body>
        <w:p>
            <w:pPr>
                <w:rPr>
                    <w:rChange w:id="1" w:author="{author}" w:date="2024-01-01T10:00:00Z"/>
                </w:rPr>
            </w:pPr>
            <w:r>
                <w:t>Test document content</w:t>
            </w:r>
        </w:p>
        <w:p>
            <w:ins w15:author="{author}" w:id="2" w:date="2024-01-01T10:01:00Z">
                <w:r>
                    <w:t>Inserted text</w:t>
                </w:r>
            </w:ins>
        </w:p>
    </w:body>
</w:document>''')

            # Empty core properties
            zf.writestr("docProps/core.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:creator></dc:creator>
    <cp:lastModifiedBy></cp:lastModifiedBy>
</cp:coreProperties>''')

            # Relationships
            zf.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>''')

        docx_buffer.seek(0)
        return docx_buffer.getvalue()

    def create_mock_docx_with_comments(self, author="Bob Wilson", initials="BW"):
        """Create a minimal DOCX with comments containing author information"""
        docx_buffer = io.BytesIO()
        with ZipFile(docx_buffer, 'w') as zf:
            # Content Types
            zf.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
    <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
</Types>''')

            # Main document
            zf.writestr("word/document.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p>
            <w:r>
                <w:t>Test document content with </w:t>
            </w:r>
            <w:commentRangeStart w:id="0"/>
            <w:r>
                <w:t>commented text</w:t>
            </w:r>
            <w:commentRangeEnd w:id="0"/>
            <w:r>
                <w:commentReference w:id="0"/>
            </w:r>
        </w:p>
    </w:body>
</w:document>''')

            # Comments with author information
            zf.writestr("word/comments.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:comment w:id="0" w:author="{author}" w:initials="{initials}" w:date="2024-01-01T10:00:00Z">
        <w:p>
            <w:r>
                <w:t>This is a comment by {author}</w:t>
            </w:r>
        </w:p>
    </w:comment>
</w:comments>''')

            # Empty core properties
            zf.writestr("docProps/core.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:creator></dc:creator>
    <cp:lastModifiedBy></cp:lastModifiedBy>
</cp:coreProperties>''')

            # Relationships
            zf.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
    <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="word/comments.xml"/>
</Relationships>''')

        docx_buffer.seek(0)
        return docx_buffer.getvalue()

    def create_clean_docx(self):
        """Create a properly cleaned DOCX with no author metadata"""
        docx_buffer = io.BytesIO()
        with ZipFile(docx_buffer, 'w') as zf:
            # Content Types
            zf.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>''')

            # Main document with empty author attributes
            zf.writestr("word/document.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">
    <w:body>
        <w:p>
            <w:pPr>
                <w:rPr>
                    <w:rChange w:id="1" w:author="" w:date="2024-01-01T10:00:00Z"/>
                </w:rPr>
            </w:pPr>
            <w:r>
                <w:t>Test document content</w:t>
            </w:r>
        </w:p>
        <w:p>
            <w:ins w15:author="" w:id="2" w:date="2024-01-01T10:01:00Z">
                <w:r>
                    <w:t>Inserted text</w:t>
                </w:r>
            </w:ins>
        </w:p>
    </w:body>
</w:document>''')

            # Properly cleaned core properties
            zf.writestr("docProps/core.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:creator/>
    <cp:lastModifiedBy/>
</cp:coreProperties>''')

            # Relationships
            zf.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>''')

        docx_buffer.seek(0)
        return docx_buffer.getvalue()

    def test_detects_author_in_core_metadata_dc_creator(self):
        """Test that assertion detects author names in dc:creator tag"""
        docx_bytes = self.create_mock_docx_with_author_in_core("Alice Johnson")

        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(docx_bytes)

        error_message = str(exc_info.value)
        assert "Alice Johnson" in error_message
        # The assertion checks that tags are empty, so we expect this error message
        assert "should be empty in core metadata" in error_message

    def test_detects_author_in_core_metadata_cp_lastmodifiedby(self):
        """Test that assertion detects author names in cp:lastModifiedBy tag"""
        docx_bytes = self.create_mock_docx_with_author_in_core("Bob Smith")

        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(docx_bytes)

        error_message = str(exc_info.value)
        assert "Bob Smith" in error_message
        # The assertion checks that tags are empty, so we expect this error message
        assert "should be empty in core metadata" in error_message

    def test_detects_w_author_attribute_in_document(self):
        """Test that assertion detects non-empty w:author attributes in document"""
        docx_bytes = self.create_mock_docx_with_document_author_attributes("Jane Smith")

        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(docx_bytes)

        error_message = str(exc_info.value)
        # Could be either w:author or w15:author that triggers first
        assert ("w:author" in error_message or "w15:author" in error_message)
        assert "should be empty" in error_message
        assert "Jane Smith" in error_message

    def test_detects_w15_author_attribute_in_document(self):
        """Test that assertion detects non-empty w15:author attributes in document"""
        docx_bytes = self.create_mock_docx_with_document_author_attributes("Carol Davis")

        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(docx_bytes)

        error_message = str(exc_info.value)
        assert "w15:author" in error_message or "w:author" in error_message  # Either could trigger first
        assert "should be empty" in error_message

    def test_detects_author_attributes_in_comments(self):
        """Test that assertion detects non-empty author attributes in comments"""
        docx_bytes = self.create_mock_docx_with_comments("Bob Wilson", "BW")

        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(docx_bytes)

        error_message = str(exc_info.value)
        assert ("w:author" in error_message or "w:initials" in error_message)
        assert "should be empty" in error_message

    def test_passes_with_clean_docx(self):
        """Test that assertion passes with properly cleaned DOCX"""
        docx_bytes = self.create_clean_docx()

        # This should not raise an exception
        assert_docx_metadata_is_stripped(docx_bytes)

    def test_requires_meaningful_text_content(self):
        """Test that assertion requires the document to have meaningful text content"""
        # Create DOCX with clean metadata but no meaningful text
        docx_buffer = io.BytesIO()
        with ZipFile(docx_buffer, 'w') as zf:
            zf.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>''')

            # Document with only empty text elements
            zf.writestr("word/document.xml", '''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p><w:r><w:t></w:t></w:r></w:p>
        <w:p><w:r><w:t>   </w:t></w:r></w:p>
    </w:body>
</w:document>''')

            # Clean metadata
            zf.writestr("docProps/core.xml", '''<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:creator/>
    <cp:lastModifiedBy/>
</cp:coreProperties>''')

        docx_bytes = docx_buffer.getvalue()

        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(docx_bytes)

        error_message = str(exc_info.value)
        assert "meaningful text content" in error_message

    def test_validates_core_xml_tags_are_empty_not_missing(self):
        """Test that assertion requires core metadata tags to be empty, not missing"""
        # Create DOCX with missing core metadata tags
        docx_buffer = io.BytesIO()
        with ZipFile(docx_buffer, 'w') as zf:
            zf.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>''')

            zf.writestr("word/document.xml", '''<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p><w:r><w:t>Test content</w:t></w:r></w:p>
    </w:body>
</w:document>''')

            # Core properties without the required tags
            zf.writestr("docProps/core.xml", '''<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
    <!-- Missing dc:creator and cp:lastModifiedBy tags -->
</cp:coreProperties>''')

        docx_bytes = docx_buffer.getvalue()

        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(docx_bytes)

        error_message = str(exc_info.value)
        assert "should be empty" in error_message
        assert ("dc:creator" in error_message or "cp:lastModifiedBy" in error_message)

class TestLambdaHandler:
    """Tests for the lambda_handler function"""
    def test_lambda_handler_processes_files_without_version_tag(self, s3_with_docx_file, input_bytes):
        """Test lambda handler processes files without a version tag"""
        s3_client, bucket_name, object_key = s3_with_docx_file

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler
        lambda_handler(event, {})

        # Verify the file was processed in place (same object key)
        # Check that the original file still exists
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        object_keys = [obj['Key'] for obj in response.get('Contents', [])]
        assert object_key in object_keys, f"Processed file {object_key} not found in S3"

        # Get the processed file and verify it's different from original
        processed_response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        processed_content = processed_response['Body'].read()
        assert processed_content != input_bytes, "Processed content should be different from input"
        assert len(processed_content) > 0, "Processed content should not be empty"

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
        assert "Skipping non-DOCX file: test.txt" in caplog.text

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

    def test_lambda_handler_handles_corrupted_docx_files(self, s3_with_corrupted_file, caplog):
        """Test lambda handler handles corrupted DOCX files"""
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
        assert "File corrupted.docx is not a valid DOCX (zip) file." in caplog.text

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
            assert processed_content != input_bytes

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

    def test_lambda_handler_skips_already_processed_files(self, s3_setup, input_bytes):
        """Test lambda handler skips files that have already been processed with the current version"""
        s3_client, bucket_name = s3_setup
        object_key = "already_processed.docx"

        # First, process the file to get the processed content
        processed_bytes = strip_docx_author_metadata_from_docx(input_bytes)

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

    def test_lambda_handler_processes_files_with_different_version(self, s3_setup, input_bytes):
        """Test lambda handler processes files that have a different version tag"""
        s3_client, bucket_name = s3_setup
        object_key = "old_version.docx"
        old_version = "0.0.9-old"  # Different from current version

        # Upload a DOCX file with an old version tag (simulating file processed with older version)
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_key,
            Body=input_bytes,
            ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            Tagging=f'DOCUMENT_PROCESSOR_VERSION={old_version}'
        )

        # Create S3 event
        event = create_s3_event(bucket_name=bucket_name, object_key=object_key)

        # Call lambda handler
        lambda_handler(event, {})

        # Verify the file was re-processed (content should be different from original)
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        processed_content = response['Body'].read()
        assert processed_content != input_bytes

        # Verify the file has the current version tag
        tag_response = s3_client.get_object_tagging(Bucket=bucket_name, Key=object_key)
        tags = {tag['Key']: tag['Value'] for tag in tag_response['TagSet']}
        assert tags['DOCUMENT_PROCESSOR_VERSION'] == __version__

        # Verify we only have 1 file total (the original, processed in place)
        list_response = s3_client.list_objects_v2(Bucket=bucket_name)
        object_keys = [obj['Key'] for obj in list_response.get('Contents', [])]
        assert len(object_keys) == 1
        assert object_key in object_keys
