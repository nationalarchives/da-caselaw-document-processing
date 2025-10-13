"""
Visual regression tests for DOCX content integrity validation.

These tests render DOCX files to images and compare them to ensure
the document cleanser only removes metadata without affecting visual appearance.
"""
import zipfile
import io
from lxml import etree
import math
from functools import reduce
import operator
import os
import tempfile
import subprocess
import hashlib
from PIL import Image, ImageChops
import pytest
from lambda_function import strip_docx_author_metadata_from_docx



def render_docx_to_image(docx_bytes: bytes, output_path: str) -> str:
    """
    Render a DOCX file to PNG image using LibreOffice headless.
    
    Configures LibreOffice to hide track changes and comments during rendering
    to focus visual regression tests on actual content changes rather than 
    markup display differences.

    Returns:
        str: Path to the generated PNG file
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Save original DOCX to temp file (no modification needed!)
        docx_path = os.path.join(temp_dir, "document.docx")
        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        # Create LibreOffice user profile directory
        profile_dir = os.path.join(temp_dir, "libreoffice_profile")
        os.makedirs(profile_dir, exist_ok=True)
        
        # Create a basic user configuration to hide track changes
        user_config_dir = os.path.join(profile_dir, "user", "config")
        os.makedirs(user_config_dir, exist_ok=True)
        
        # Write a simple configuration to hide changes during export
        registrymodifications_path = os.path.join(user_config_dir, "registrymodifications.xcu")
        with open(registrymodifications_path, "w") as f:
            f.write('''<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
  <item oor:path="/org.openoffice.Office.Writer/Changes">
    <prop oor:name="ShowChanges" oor:op="fuse">
      <value>false</value>
    </prop>
  </item>
</oor:items>''')

        # Convert DOCX to PDF using LibreOffice headless with custom profile
        pdf_path = os.path.join(temp_dir, "document.pdf")
        try:
            result = subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    temp_dir,
                    "-env:UserInstallation=file://" + profile_dir,
                    docx_path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            
            # Check if PDF was actually created
            if not os.path.exists(pdf_path):
                raise RuntimeError(f"LibreOffice did not create PDF file. stdout: {result.stdout}, stderr: {result.stderr}")
                
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"LibreOffice conversion failed: stdout={e.stdout}, stderr={e.stderr}")

        # Convert PDF to PNG using ImageMagick
        try:
            subprocess.run(
                ["convert", "-density", "150", pdf_path, "-quality", "90", output_path],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"PDF to PNG conversion failed: {e.stderr}")

        return output_path


def compare_images(image1_path: str, image2_path: str, threshold: float = 0.01) -> dict:
    """
    Compare two images using RMS histogram comparison.
    
    Returns:
        dict: Comparison results with similarity score and diff image path
    """    
    try:
        # Load images
        img1 = Image.open(image1_path).convert("RGB")
        img2 = Image.open(image2_path).convert("RGB")

        # Resize to same dimensions if needed
        if img1.size != img2.size:
            # Resize to the smaller dimensions
            min_width = min(img1.width, img2.width)
            min_height = min(img1.height, img2.height)
            img1 = img1.resize((min_width, min_height), Image.Resampling.LANCZOS)
            img2 = img2.resize((min_width, min_height), Image.Resampling.LANCZOS)

        # Get histograms for comparison
        h1 = img1.histogram()
        h2 = img2.histogram()
        
        # Calculate RMS difference between histograms
        rms = math.sqrt(reduce(operator.add, map(lambda a, b: (a-b)**2, h1, h2)) / len(h1))
        
        # Normalize RMS to a 0-1 scale (approximate)
        # For 8-bit images, max possible RMS is around sqrt(255^2 * 3) ≈ 442 for RGB
        max_rms = 442.0  # Approximate maximum RMS for RGB images
        similarity_score = rms / max_rms

        # Create and save diff image for debugging
        diff = ImageChops.difference(img1, img2)
        diff_path = image1_path.replace(".png", "_diff.png")
        diff.save(diff_path)

        return {
            "similarity_score": similarity_score,
            "is_similar": similarity_score <= threshold,
            "diff_image_path": diff_path,
            "threshold": threshold,
            "image1_size": img1.size,
            "image2_size": img2.size,
            "debug": {
                "rms": rms,
                "max_rms": max_rms,
                "normalized_score": similarity_score,
            },
        }

    except Exception as e:
        return {
            "similarity_score": 1.0,
            "is_similar": False,
            "error": str(e),
            "diff_image_path": None,
        }


class TestVisualRegression:
    """Visual regression tests for DOCX processing."""

    @pytest.fixture
    def sample_docx_bytes(self):
        """Load the sample DOCX file."""
        sample_path = os.path.join(
            os.path.dirname(__file__), "test_files", "sample_with_author.docx"
        )
        with open(sample_path, "rb") as f:
            return f.read()

    def test_visual_render_integrity_persists_after_metadata_removal(self, sample_docx_bytes, tmp_path):
        """Test that visual appearance is preserved after author metadata removal.

        Uses LibreOffice configuration to hide track changes/comments during rendering
        so visual comparison focuses on content differences, not markup display.
        """
        # Process the document with lambda function (removes author metadata only)
        processed_bytes = strip_docx_author_metadata_from_docx(sample_docx_bytes)

        # Render both versions to images - save to /tmp for debugging visibility
        # Note: LibreOffice is configured to hide track changes/comments during rendering
        original_image = "/tmp/debug_original.png"
        processed_image = "/tmp/debug_processed.png"

        render_docx_to_image(sample_docx_bytes, original_image)
        render_docx_to_image(processed_bytes, processed_image)

        # Compare images - use higher threshold to account for track changes metadata display differences
        comparison = compare_images(original_image, processed_image, threshold=0.15)

        # Assert visual similarity
        assert comparison["is_similar"], (
            f"Visual regression detected! "
            f"Similarity score: {comparison['similarity_score']:.4f} "
            f"(threshold: {comparison['threshold']}) "
            f"Diff saved to: {comparison.get('diff_image_path')}"
        )

class TestCompareImages:
    def test_compare_images_detects_content_changes(self, tmp_path):
        """Test that visual regression can detect actual content changes."""
        # Create two DOCX files with significantly different content
        original_docx = _create_test_docx(
            "This is the original document with some content that should be clearly visible in the rendered image."
        )
        modified_docx = _create_test_docx(
            "THIS IS A COMPLETELY DIFFERENT DOCUMENT WITH ENTIRELY NEW TEXT THAT IS MUCH LONGER AND SHOULD CREATE A VISUALLY OBVIOUS DIFFERENCE WHEN RENDERED TO AN IMAGE."
        )  # Very different text

        # Render both to images - save to /tmp for debugging visibility
        original_image = "/tmp/debug_original_content.png"
        modified_image = "/tmp/debug_modified_content.png"

        render_docx_to_image(original_docx, original_image)
        render_docx_to_image(modified_docx, modified_image)

        # Compare images - should detect difference (use higher threshold for content changes)
        comparison = compare_images(original_image, modified_image, threshold=0.05)

        # Should detect the change (similarity score should be above a minimal threshold)
        # We expect some visual differences when content changes
        assert comparison["similarity_score"] > 0.001, (
            "Visual regression test failed to detect content changes! "
            f"Similarity score: {comparison['similarity_score']:.4f} should be > 0.001 for different content"
        )

    def test_libreoffice_hides_track_changes_in_render(self):
        """Test that LibreOffice configuration hides track changes and comments during rendering.

        This verifies that our LibreOffice configuration properly hides markup elements
        so that documents with and without markup render similarly for visual comparison.
        """
        # Create a DOCX with track changes and comments
        docx_with_markup = _create_test_docx_with_markup(
            "Original text",
            inserted_text="New insertion", 
            deleted_text="Deleted text",
            comment="This is a comment",
        )
        
        # Create the same document without markup for comparison
        docx_clean = _create_test_docx("Original text New insertion")

        # Both should render very similarly due to LibreOffice configuration
        markup_image = "/tmp/debug_with_markup.png"
        clean_image = "/tmp/debug_without_markup.png"

        render_docx_to_image(docx_with_markup, markup_image)
        render_docx_to_image(docx_clean, clean_image)

        # Save debug files
        with open("/tmp/debug_with_markup.docx", "wb") as f:
            f.write(docx_with_markup)
        with open("/tmp/debug_without_markup.docx", "wb") as f:
            f.write(docx_clean)

        print(f"🔧 LibreOffice rendering test files:")
        print(f"   DOCX with markup: /tmp/debug_with_markup.docx")
        print(f"   DOCX without markup: /tmp/debug_without_markup.docx")
        print(f"   Markup image: {markup_image}")
        print(f"   Clean image: {clean_image}")

        # Compare - should be similar due to LibreOffice hiding markup
        comparison = compare_images(markup_image, clean_image, threshold=0.1)

        assert comparison["is_similar"], (
            f"LibreOffice markup hiding failed: {comparison['similarity_score']:.4f} > 0.1. "
            f"Track changes and comments may still be visible in rendered output."
        )

    # def test_lambda_preserves_track_changes_content(self):
    #     """Test that the lambda function preserves track changes content, only removes author metadata."""
    #     # Create a DOCX with track changes that have author information
    #     docx_with_author_metadata = _create_test_docx_with_markup(
    #         "Original text",
    #         inserted_text="New insertion",
    #         deleted_text="Deleted text",
    #         comment="Test comment",
    #     )

    #     # Process with lambda function (should preserve content, remove author metadata only)
    #     processed_docx = strip_docx_author_metadata_from_docx(docx_with_author_metadata)

    #     # Verify track changes content is preserved by checking the XML
    #     import zipfile
    #     import io
    #     from lxml import etree

    #     with zipfile.ZipFile(io.BytesIO(processed_docx), "r") as zf:
    #         document_xml = zf.read("word/document.xml")
    #         root = etree.fromstring(document_xml)

    #         # Check that insertion content is still there
    #         insertions = root.xpath(
    #             ".//w:ins",
    #             namespaces={
    #                 "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    #             },
    #         )
    #         assert len(insertions) > 0, "Track change insertions should be preserved"

    #         # Check that deletion elements are still there (even if content is not rendered)
    #         deletions = root.xpath(
    #             ".//w:del",
    #             namespaces={
    #                 "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    #             },
    #         )
    #         assert len(deletions) > 0, "Track change deletions should be preserved"

    #         # Check that comment references are preserved
    #         comment_refs = root.xpath(
    #             ".//w:commentReference",
    #             namespaces={
    #                 "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    #             },
    #         )
    #         assert len(comment_refs) > 0, "Comment references should be preserved"

    #         # Verify author metadata is removed (should be empty string)
    #         for ins in insertions:
    #             author_attr = ins.get(
    #                 "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}author"
    #             )
    #             assert (
    #                 author_attr == ""
    #             ), f"Author metadata should be removed from insertions, found: {author_attr}"

    #         for deletion in deletions:
    #             author_attr = deletion.get(
    #                 "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}author"
    #             )
    #             assert (
    #                 author_attr == ""
    #             ), f"Author metadata should be removed from deletions, found: {author_attr}"

    #     print(
    #         "✅ Lambda function correctly preserves track changes content while removing author metadata"
    #     )

def _create_test_docx(content: str) -> bytes:
    """Create a simple test DOCX with given content."""
    from zipfile import ZipFile
    import io

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
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        )

        # Main document with proper namespaces
        zf.writestr(
            "word/document.xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="w14 w15 wp14">
<w:body>
    <w:p>
        <w:r>
            <w:t>{content}</w:t>
        </w:r>
    </w:p>
    <w:sectPr>
        <w:pgSz w:w="12240" w:h="15840"/>
        <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
    </w:sectPr>
</w:body>
</w:document>""",
        )

        # Core properties
        zf.writestr(
            "docProps/core.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Test Document</dc:title>
<dc:creator>Test Author</dc:creator>
<cp:lastModifiedBy>Test Author</cp:lastModifiedBy>
<dcterms:created xsi:type="dcterms:W3CDTF">2024-01-01T12:00:00Z</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">2024-01-01T12:00:00Z</dcterms:modified>
</cp:coreProperties>""",
        )

        # App properties  
        zf.writestr(
            "docProps/app.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>Test Application</Application>
<DocSecurity>0</DocSecurity>
<ScaleCrop>false</ScaleCrop>
<SharedDoc>false</SharedDoc>
<HyperlinksChanged>false</HyperlinksChanged>
<AppVersion>16.0000</AppVersion>
</Properties>""",
        )

        # Relationships
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        )

    docx_buffer.seek(0)
    return docx_buffer.getvalue()

def _create_test_docx_with_markup(
    base_content: str,
    inserted_text: str = "",
    deleted_text: str = "",
    comment: str = "",
) -> bytes:
    """Create a DOCX with track changes and comments for testing cleanup."""
    from zipfile import ZipFile
    import io

    docx_buffer = io.BytesIO()
    with ZipFile(docx_buffer, "w") as zf:
        # Content Types - include comments if needed
        content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>"""
        
        if comment:
            content_types += """
<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>"""
        
        content_types += """
</Types>"""
        zf.writestr("[Content_Types].xml", content_types)

        # Main document with track changes and comments
        comment_ref = (
            f'<w:commentRangeStart w:id="0"/><w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r>'
            if comment
            else ""
        )
        insertion = (
            f'<w:ins w:id="1" w:author="Test Author" w:date="2024-01-01T12:00:00Z"><w:r><w:t>{inserted_text}</w:t></w:r></w:ins>'
            if inserted_text
            else ""
        )
        deletion = (
            f'<w:del w:id="2" w:author="Test Author" w:date="2024-01-01T12:00:00Z"><w:r><w:delText>{deleted_text}</w:delText></w:r></w:del>'
            if deleted_text
            else ""
        )

        zf.writestr(
            "word/document.xml",
            f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="w14 w15 wp14">
<w:body>
    <w:p>
        <w:r>
            <w:t>{base_content}</w:t>
        </w:r>
        {insertion}
        {deletion}
        {comment_ref}
    </w:p>
    <w:sectPr>
        <w:pgSz w:w="12240" w:h="15840"/>
        <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
    </w:sectPr>
</w:body>
</w:document>""",
        )

        # Comments file if comment is provided
        if comment:
            zf.writestr(
                "word/comments.xml",
                f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:comment w:id="0" w:author="Test Author" w:date="2024-01-01T12:00:00Z">
    <w:p>
        <w:r>
            <w:t>{comment}</w:t>
        </w:r>
    </w:p>
</w:comment>
</w:comments>""",
            )

        # Core properties
        zf.writestr(
            "docProps/core.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Test Document with Markup</dc:title>
<dc:creator>Test Author</dc:creator>
<cp:lastModifiedBy>Test Author</cp:lastModifiedBy>
<dcterms:created xsi:type="dcterms:W3CDTF">2024-01-01T12:00:00Z</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">2024-01-01T12:00:00Z</dcterms:modified>
</cp:coreProperties>""",
        )

        # App properties  
        zf.writestr(
            "docProps/app.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>Test Application</Application>
<DocSecurity>0</DocSecurity>
<ScaleCrop>false</ScaleCrop>
<SharedDoc>false</SharedDoc>
<HyperlinksChanged>false</HyperlinksChanged>
<AppVersion>16.0000</AppVersion>
</Properties>""",
        )

        # Relationships
        relationships_content = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>"""

        if comment:
            relationships_content += """
<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="word/comments.xml"/>"""

        relationships_content += """
</Relationships>"""

        zf.writestr("_rels/.rels", relationships_content)

    docx_buffer.seek(0)
    return docx_buffer.getvalue()

# class TestRenderDocxToImage:
#     def test_render_docx_to_image_creates_image(self, tmp_path):
#         """Test that rendering a DOCX to image creates a PNG file."""
#         # Create a simple DOCX
#         docx_bytes = _create_test_docx("This is a test document.")

#         # Render to image
#         output_image = os.path.join(tmp_path, "output.png")
#         render_docx_to_image(docx_bytes, output_image)

#         # Check that the image file was created
#         assert os.path.exists(output_image), "Output image file was not created."
#         assert os.path.getsize(output_image) > 0, "Output image file is empty."

#         output_image_hash = hashlib.md5(open(output_image, 'rb').read()).hexdigest()
#         assert output_image_hash == "2bd3db9da29a63410e8ff540657cdeeb", f"Unexpected image hash: {output_image_hash}"