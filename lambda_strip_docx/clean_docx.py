import logging
import io
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED
import lxml.etree

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REDACTION_STRING = ""
NAMESPACES = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}


def _strip_forbidden_attributes(root: lxml.etree._Element) -> None:
    """Remove forbidden attributes from XML elements."""
    forbidden_attributes = ["w15:author", "w15:userId", "w:author", "w:initials"]
    for attribute in forbidden_attributes:
        attribute_namespace, _, attribute_name = attribute.partition(":")
        for node in root.xpath(f"//*[@{attribute}]", namespaces=NAMESPACES):
            node.attrib[f"{{{NAMESPACES[attribute_namespace]}}}{attribute_name}"] = (
                REDACTION_STRING
            )


def _strip_forbidden_tags(root: lxml.etree._Element) -> None:
    """Remove content from forbidden tags."""
    forbidden_tags = ["cp:lastModifiedBy", "dc:creator"]
    for tag in forbidden_tags:
        for node in root.xpath(f"//{tag}", namespaces=NAMESPACES):
            if node.text is not None:
                node.text = REDACTION_STRING


def _strip_docx_author_metadata_from_xml(xml_content: bytes) -> bytes:
    """Process XML content to remove author metadata."""
    try:
        root = lxml.etree.fromstring(xml_content)
        _strip_forbidden_attributes(root)
        _strip_forbidden_tags(root)
        return lxml.etree.tostring(root)
    except lxml.etree.XMLSyntaxError:
        # Return original content if XML parsing fails
        return xml_content


def strip_docx_author_metadata_from_docx(input_docx: bytes) -> bytes:
    """Strip author metadata from a DOCX file in bytes form."""
    input_buffer = io.BytesIO(input_docx)
    output_buffer = io.BytesIO()

    with (
        ZipFile(input_buffer, "r") as archive_input,
        ZipFile(
            output_buffer, "w", compression=ZIP_DEFLATED, compresslevel=6
        ) as archive_output,
    ):
        for archive_filename in archive_input.namelist():
            with archive_input.open(archive_filename, "r") as f:
                xml_content = f.read()
                processed_content = _strip_docx_author_metadata_from_xml(xml_content)
                archive_output.writestr(archive_filename, processed_content)

    return output_buffer.getvalue()


def clean(file_content):
    try:
        return strip_docx_author_metadata_from_docx(file_content)
    except BadZipFile:
        logger.error("File is not a valid DOCX (zip) file.")
        raise
    # TODO: handle exceptions, esp BadZipFile
