import pytest
from zipfile import ZipFile
import io
import re
from clean_docx import strip_docx_author_metadata_from_docx
from lambda_function import __version__


def create_s3_event(bucket_name="test-bucket", object_key="test.docx"):
    """Create a mock S3 event structure"""
    return {
        "Records": [
            {
                "eventID": "test-event-id",
                "s3": {"bucket": {"name": bucket_name}, "object": {"key": object_key}},
            }
        ]
    }


def assert_docx_metadata_is_stripped(docx_bytes):
    """Helper function to assert that DOCX metadata has been properly stripped"""
    # Define the forbidden attributes and tags that should be redacted
    forbidden_attributes = ["w15:author", "w15:userId", "w:author", "w:initials"]
    forbidden_tags = ["cp:lastModifiedBy", "dc:creator"]

    # Verify author metadata has been stripped from all XML files
    with ZipFile(io.BytesIO(docx_bytes), "r") as archive:
        # Check document properties metadata - should be completely empty
        with archive.open("docProps/core.xml", "r") as f:
            core_xml = f.read().decode("utf-8")

            # All forbidden tags should be empty
            for tag in forbidden_tags:
                tag_prefix, tag_name = tag.split(":")
                # Check for both self-closing and empty tags
                empty_patterns = [
                    f"<{tag}></{tag}>",  # Empty tag
                    f"<{tag}/>",  # Self-closing tag
                    f"<{tag}\\s*/>",  # Self-closing with whitespace
                ]

                tag_found = any(
                    re.search(pattern, core_xml) for pattern in empty_patterns
                )
                assert tag_found, (
                    f"Tag '{tag}' should be empty in core metadata, but found: {re.findall(f'<{re.escape(tag)}[^>]*>.*?</{re.escape(tag)}>', core_xml)}"
                )

        # Check main document - author attributes should be empty but text content preserved
        with archive.open("word/document.xml", "r") as f:
            doc_xml = f.read().decode("utf-8")

            # All forbidden attributes should be empty strings
            for attr in forbidden_attributes:
                # Find all instances of this attribute and verify they're empty
                attr_pattern = f'{re.escape(attr)}="([^"]*)"'
                attr_values = re.findall(attr_pattern, doc_xml)

                # All attribute values should be empty strings
                for value in attr_values:
                    assert value == "", (
                        f"Attribute '{attr}' should be empty but found value: '{value}'"
                    )

                # Also check that we don't have any non-empty attribute values
                non_empty_pattern = f'{re.escape(attr)}="[^"]+[^"]"'
                non_empty_matches = re.findall(non_empty_pattern, doc_xml)
                assert len(non_empty_matches) == 0, (
                    f"Found non-empty {attr} attributes: {non_empty_matches}"
                )

        # Check comments file - author attributes should be empty but comment text preserved
        if "word/comments.xml" in archive.namelist():
            with archive.open("word/comments.xml", "r") as f:
                comments_xml = f.read().decode("utf-8")

                # All forbidden attributes in comments should be empty
                for attr in forbidden_attributes:
                    attr_pattern = f'{re.escape(attr)}="([^"]*)"'
                    attr_values = re.findall(attr_pattern, comments_xml)

                    for value in attr_values:
                        assert value == "", (
                            f"Comment attribute '{attr}' should be empty but found value: '{value}'"
                        )

                # Verify that comment text content is preserved (comments should still have meaningful text)
                assert "<w:t>" in comments_xml, (
                    "Comment text content should be preserved"
                )

        # Verify that the document still contains the actual text content
        # (to ensure we're not over-redacting and removing legitimate content)
        with archive.open("word/document.xml", "r") as f:
            doc_xml = f.read().decode("utf-8")
            # The document should still contain text elements
            assert "<w:t>" in doc_xml, "Document text content should be preserved"
            # Should contain some meaningful text (not just empty tags)
            text_content = re.findall(r"<w:t>([^<]*)</w:t>", doc_xml)
            meaningful_text = [t.strip() for t in text_content if t.strip()]
            assert len(meaningful_text) > 0, (
                "Document should contain meaningful text content"
            )


class TestStripDocxAuthorMetadata:
    """Tests for the strip_docx_author_metadata function"""

    def test_strip_docx_author_removes_metadata(self, input_docx):
        """Test that all author metadata is properly stripped from DOCX files while preserving text content"""

        # Process the input bytes to remove author metadata
        output_bytes = strip_docx_author_metadata_from_docx(input_docx)

        # Basic sanity checks
        assert len(output_bytes) > 0, "Output should not be empty"
        assert output_bytes != input_docx, (
            "Output should be different from input after processing"
        )

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

    def test_assertion_function_detects_violations(self, input_docx):
        """Test that our assertion function correctly detects violations when metadata is NOT stripped"""

        # Test with original (unprocessed) bytes - this should fail the assertions
        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(input_docx)

        # Verify the assertion error contains meaningful information about what was found
        error_message = str(exc_info.value)
        assert (
            "should not be present" in error_message
            or "should be empty" in error_message
        ), f"Assertion error should indicate metadata violation, got: {error_message}"


class TestAssertDocxMetadataIsStripped:
    """Comprehensive tests for the assert_docx_metadata_is_stripped function"""

    def create_mock_docx_with_author_in_core(self, author_name="John Doe"):
        """Create a minimal DOCX with author in core metadata"""
        # Create a minimal DOCX structure with author metadata
        docx_buffer = io.BytesIO()
        with ZipFile(docx_buffer, "w") as zf:
            # Content Types
            zf.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>""",
            )

            # Main document
            zf.writestr(
                "word/document.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p>
            <w:r>
                <w:t>Test document content</w:t>
            </w:r>
        </w:p>
    </w:body>
</w:document>""",
            )

            # Core properties with author
            zf.writestr(
                "docProps/core.xml",
                f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:dcmitype="http://purl.org/dc/dcmitype/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <dc:creator>{author_name}</dc:creator>
    <cp:lastModifiedBy>{author_name}</cp:lastModifiedBy>
</cp:coreProperties>""",
            )

            # Relationships
            zf.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>""",
            )

        docx_buffer.seek(0)
        return docx_buffer.getvalue()

    def create_mock_docx_with_document_author_attributes(
        self, author="Jane Smith", initials="JS"
    ):
        """Create a minimal DOCX with author attributes in document.xml"""
        docx_buffer = io.BytesIO()
        with ZipFile(docx_buffer, "w") as zf:
            # Content Types
            zf.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>""",
            )

            # Main document with author attributes
            zf.writestr(
                "word/document.xml",
                f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
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
</w:document>''',
            )

            # Empty core properties
            zf.writestr(
                "docProps/core.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:creator></dc:creator>
    <cp:lastModifiedBy></cp:lastModifiedBy>
</cp:coreProperties>""",
            )

            # Relationships
            zf.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>""",
            )

        docx_buffer.seek(0)
        return docx_buffer.getvalue()

    def create_mock_docx_with_comments(self, author="Bob Wilson", initials="BW"):
        """Create a minimal DOCX with comments containing author information"""
        docx_buffer = io.BytesIO()
        with ZipFile(docx_buffer, "w") as zf:
            # Content Types
            zf.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
    <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
</Types>""",
            )

            # Main document
            zf.writestr(
                "word/document.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
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
</w:document>""",
            )

            # Comments with author information
            zf.writestr(
                "word/comments.xml",
                f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:comment w:id="0" w:author="{author}" w:initials="{initials}" w:date="2024-01-01T10:00:00Z">
        <w:p>
            <w:r>
                <w:t>This is a comment by {author}</w:t>
            </w:r>
        </w:p>
    </w:comment>
</w:comments>''',
            )

            # Empty core properties
            zf.writestr(
                "docProps/core.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:creator></dc:creator>
    <cp:lastModifiedBy></cp:lastModifiedBy>
</cp:coreProperties>""",
            )

            # Relationships
            zf.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
    <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="word/comments.xml"/>
</Relationships>""",
            )

        docx_buffer.seek(0)
        return docx_buffer.getvalue()

    def create_clean_docx(self):
        """Create a properly cleaned DOCX with no author metadata"""
        docx_buffer = io.BytesIO()
        with ZipFile(docx_buffer, "w") as zf:
            # Content Types
            zf.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>""",
            )

            # Main document with empty author attributes
            zf.writestr(
                "word/document.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
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
</w:document>""",
            )

            # Properly cleaned core properties
            zf.writestr(
                "docProps/core.xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:creator/>
    <cp:lastModifiedBy/>
</cp:coreProperties>""",
            )

            # Relationships
            zf.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
    <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>""",
            )

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
        assert "w:author" in error_message or "w15:author" in error_message
        assert "should be empty" in error_message
        assert "Jane Smith" in error_message

    def test_detects_w15_author_attribute_in_document(self):
        """Test that assertion detects non-empty w15:author attributes in document"""
        docx_bytes = self.create_mock_docx_with_document_author_attributes(
            "Carol Davis"
        )

        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(docx_bytes)

        error_message = str(exc_info.value)
        assert (
            "w15:author" in error_message or "w:author" in error_message
        )  # Either could trigger first
        assert "should be empty" in error_message

    def test_detects_author_attributes_in_comments(self):
        """Test that assertion detects non-empty author attributes in comments"""
        docx_bytes = self.create_mock_docx_with_comments("Bob Wilson", "BW")

        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(docx_bytes)

        error_message = str(exc_info.value)
        assert "w:author" in error_message or "w:initials" in error_message
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
        with ZipFile(docx_buffer, "w") as zf:
            zf.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>""",
            )

            # Document with only empty text elements
            zf.writestr(
                "word/document.xml",
                """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p><w:r><w:t></w:t></w:r></w:p>
        <w:p><w:r><w:t>   </w:t></w:r></w:p>
    </w:body>
</w:document>""",
            )

            # Clean metadata
            zf.writestr(
                "docProps/core.xml",
                """<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:creator/>
    <cp:lastModifiedBy/>
</cp:coreProperties>""",
            )

        docx_bytes = docx_buffer.getvalue()

        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(docx_bytes)

        error_message = str(exc_info.value)
        assert "meaningful text content" in error_message

    def test_validates_core_xml_tags_are_empty_not_missing(self):
        """Test that assertion requires core metadata tags to be empty, not missing"""
        # Create DOCX with missing core metadata tags
        docx_buffer = io.BytesIO()
        with ZipFile(docx_buffer, "w") as zf:
            zf.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>""",
            )

            zf.writestr(
                "word/document.xml",
                """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p><w:r><w:t>Test content</w:t></w:r></w:p>
    </w:body>
</w:document>""",
            )

            # Core properties without the required tags
            zf.writestr(
                "docProps/core.xml",
                """<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/">
    <!-- Missing dc:creator and cp:lastModifiedBy tags -->
</cp:coreProperties>""",
            )

        docx_bytes = docx_buffer.getvalue()

        with pytest.raises(AssertionError) as exc_info:
            assert_docx_metadata_is_stripped(docx_bytes)

        error_message = str(exc_info.value)
        assert "should be empty" in error_message
        assert "dc:creator" in error_message or "cp:lastModifiedBy" in error_message
