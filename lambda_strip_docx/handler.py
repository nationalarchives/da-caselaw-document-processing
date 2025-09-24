import os
import logging
import tempfile
from zipfile import ZipFile, BadZipFile
import lxml.etree

default_logger = logging.getLogger()
default_logger.setLevel(logging.INFO)

REDACTION_STRING = ""
namespaces = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}
forbidden_attributes = ["w15:author", "w15:userId", "w:author"]
forbidden_tags = ["cp:lastModifiedBy", "dc:creator"]

def strip_docx_author_metadata(input_bytes, logger=default_logger):
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.docx")
        output_path = os.path.join(tmpdir, "output.docx")
        with open(input_path, "wb") as f:
            f.write(input_bytes)
        try:
            with ZipFile(input_path, "r") as archive_input, ZipFile(output_path, "w") as archive_output:
                for archive_filename in archive_input.namelist():
                    with archive_input.open(archive_filename, "r") as f:
                        xml = f.read()
                        try:
                            root = lxml.etree.fromstring(xml)
                            for attribute in forbidden_attributes:
                                attribute_namespace, _, attribute_name = attribute.partition(":")
                                for node in root.xpath(f"//*[@{attribute}]", namespaces=namespaces):
                                    node.attrib[f"{{{namespaces[attribute_namespace]}}}{attribute_name}"] = REDACTION_STRING
                            for tag in forbidden_tags:
                                for node in root.xpath(f"//{tag}", namespaces=namespaces):
                                    if node.text is not None:
                                        node.text = REDACTION_STRING
                            output_xml = lxml.etree.tostring(root)
                            archive_output.writestr(archive_filename, output_xml)
                        except lxml.etree.XMLSyntaxError:
                            archive_output.writestr(archive_filename, xml)
            with open(output_path, "rb") as f:
                return f.read()
        except BadZipFile:
            logger.error("Input file is not a valid DOCX (zip) file.")
            raise

def lambda_handler(event, context):
    import base64
    logger = default_logger
    try:
        file_content = base64.b64decode(event["body"])
        filename = event.get("headers", {}).get("filename", "document.docx")
        if not filename.lower().endswith(".docx"):
            logger.warning(f"Unsupported file type: {filename}")
            return {
                "statusCode": 400,
                "body": "Unsupported file type. Only DOCX is supported."
            }
        output_bytes = strip_docx_author_metadata(file_content, logger=logger)
        logger.info(f"Successfully processed {filename}")
        return {
            "statusCode": 200,
            "isBase64Encoded": True,
            "headers": {
                "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
            "body": base64.b64encode(output_bytes).decode("utf-8")
        }
    except Exception as e:
        logger.error(f"Failed to process file: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": f"Failed to process file: {str(e)}"
        }
