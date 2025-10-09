import logging
import boto3
from urllib.parse import unquote_plus
import clean_docx
import clean_pdf
from exceptions import VisuallyDifferentError

__version__="0.1.0-dev"

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

                # Check if the file has already been processed
                tags_response = s3.get_object_tagging(Bucket=bucket_name, Key=object_key)
                tags = {tag['Key']: tag['Value'] for tag in tags_response.get('TagSet', [])}

                if 'DOCUMENT_PROCESSOR_VERSION' in tags:
                    existing_version = tags['DOCUMENT_PROCESSOR_VERSION']
                    try:
                        current_major_version = document_processor_version.split('.')[0]
                        existing_major_version = existing_version.split('.')[0]

                        if current_major_version == existing_major_version:
                            logger.info(f"File {object_key} has already been processed with compatible version {existing_version} (current: {document_processor_version}). Skipping.")
                            continue
                    except (IndexError, AttributeError):
                        # If version parsing fails, proceed with processing to be safe
                        logger.warning(f"Could not parse version strings for comparison. Existing: {existing_version}, Current: {document_processor_version}. Proceeding with processing.")
                        pass

                # Read the file from S3
                response = s3.get_object(Bucket=bucket_name, Key=object_key)
                file_content = response['Body'].read()

                extension = object_key.split(".")[-1].lower()
                # TODO: work out what sort of file it is from magic numbers
                # extensions are less reliable

                file_type = extension

                if file_type == "docx":
                    clean_module = clean_docx
                    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif file_type == "pdf":
                    clean_module = clean_pdf
                    content_type= "application/pdf"
                else:
                    logger.warning(f"Skipping unrecognised file: {object_key} {file_content[:5]!r}")
                    continue

                output_bytes = clean_module.clean(file_content)
                if clean_module.compare(file_content, output_bytes) == False:
                    raise VisuallyDifferentError(f"S3 key {object_key} was visually different after cleaning.")

                # Write the processed file back to S3
                s3.put_object(
                    Bucket=bucket_name,
                    Key=object_key,
                    Body=output_bytes,
                    ContentType=content_type,
                    Tagging=f'DOCUMENT_PROCESSOR_VERSION={document_processor_version}'
                )

                logger.info(f"Successfully processed and rewrote {file_type}: {object_key}")

            except Exception as e:
                logger.error(f"Failed to process file {object_key}: {e}", exc_info=True)
                continue

            # Log completion using available record information
            logger.info(f"Processing finished on object: {object_key}")

    except Exception as e:
        logger.error(f"Lambda execution failed: {e}", exc_info=True)
        raise
