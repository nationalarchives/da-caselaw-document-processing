import os
import logging
import io
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED
import lxml.etree
import boto3
from urllib.parse import unquote_plus

__version__="0.1.0-dev"

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
            node.attrib[f"{{{NAMESPACES[attribute_namespace]}}}{attribute_name}"] = REDACTION_STRING


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


def strip_docx_author_metadata_from_docx(input_bytes: bytes) -> bytes:
    """Strip author metadata from a DOCX file in bytes form."""
    input_buffer = io.BytesIO(input_bytes)
    output_buffer = io.BytesIO()

    with ZipFile(input_buffer, "r") as archive_input, ZipFile(output_buffer, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive_output:
        for archive_filename in archive_input.namelist():
            with archive_input.open(archive_filename, "r") as f:
                xml_content = f.read()
                processed_content = _strip_docx_author_metadata_from_xml(xml_content)
                archive_output.writestr(archive_filename, processed_content)

    return output_buffer.getvalue()

def lambda_handler(event, context):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Get the document processor version
    document_processor_version = __version__
    try:
        # Initialize S3 client
        s3 = boto3.client('s3')

        # Process each record in the S3 event
        for record in event.get('Records', []):
            try:
                # Extract bucket name and object key from the S3 event
                bucket_name = record['s3']['bucket']['name']
                object_key = unquote_plus(record['s3']['object']['key'])

                logger.info(f"Processing file: {object_key} from bucket: {bucket_name}")

                # Check if it's a DOCX file
                if not object_key.lower().endswith('.docx'):
                    logger.warning(f"Skipping non-DOCX file: {object_key}")
                    continue

                # Check if the file has already been processed
                tags_response = s3.get_object_tagging(Bucket=bucket_name, Key=object_key)
                tags = {tag['Key']: tag['Value'] for tag in tags_response.get('TagSet', [])}
                if 'DOCUMENT_PROCESSOR_VERSION' in tags and tags['DOCUMENT_PROCESSOR_VERSION'] == document_processor_version:
                    logger.info(f"File {object_key} has already been processed. Skipping.")
                    continue

                # Read the file from S3
                response = s3.get_object(Bucket=bucket_name, Key=object_key)
                file_content = response['Body'].read()

                # Process the DOCX file
                try:
                    output_bytes = strip_docx_author_metadata_from_docx(file_content)
                except BadZipFile:
                    logger.error(f"File {object_key} is not a valid DOCX (zip) file.")
                    continue

                # Create output key (you can modify this logic as needed)
                base_name, extension = os.path.splitext(object_key)
                output_key = f"{base_name}_processed{extension}"

                # Write the processed file back to S3
                s3.put_object(
                    Bucket=bucket_name,
                    Key=output_key,
                    Body=output_bytes,
                    ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    Tagging=f'DOCUMENT_PROCESSOR_VERSION={document_processor_version}'
                )

                logger.info(f"Successfully processed and saved: {output_key}")

            except Exception as e:
                logger.error(f"Failed to process file {object_key}: {e}", exc_info=True)
                continue

            logger.info(f"Processing finished for event: {record['eventID']}")

    except Exception as e:
        logger.error(f"Lambda execution failed: {e}", exc_info=True)
        raise
