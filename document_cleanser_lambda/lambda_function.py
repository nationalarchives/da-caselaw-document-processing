import json
import logging
import os
from urllib.parse import unquote_plus

import boto3
import rollbar
from dotenv import load_dotenv

import clean_docx
import clean_jpeg
import clean_pdf
import clean_png
import utils
from exceptions import VisuallyDifferentError

load_dotenv()


__version__ = "1.0.0"
rollbar.init(os.getenv("ROLLBAR_TOKEN", ""), environment=os.getenv("ROLLBAR_ENV", "unknown"), code_version=__version__)

DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MODULE_FOR_MIME_TYPE = {
    DOCX_MIME_TYPE: clean_docx,
    "image/png": clean_png,
    "image/jpeg": clean_jpeg,
    "application/pdf": clean_pdf,
}


def handle_one_record(record, s3, logger) -> None:
    # Get the document processor version
    document_processor_version = __version__
    # Extract bucket name and object key from the S3 event
    bucket_name = record["s3"]["bucket"]["name"]
    object_key = unquote_plus(record["s3"]["object"]["key"])

    logger.info(f"Processing file: {object_key} from bucket: {bucket_name}")

    # Check if the file has already been processed
    tags_response = s3.get_object_tagging(Bucket=bucket_name, Key=object_key)
    tags = {tag["Key"]: tag["Value"] for tag in tags_response.get("TagSet", [])}

    if "DOCUMENT_PROCESSOR_VERSION" in tags:
        existing_version = tags["DOCUMENT_PROCESSOR_VERSION"]
        try:
            current_major_version = document_processor_version.split(".")[0]
            existing_major_version = existing_version.split(".")[0]

            if current_major_version == existing_major_version:
                logger.info(
                    f"File {object_key} has already been processed with compatible version {existing_version} (current: {document_processor_version}). Skipping.",
                )
                return
        except (IndexError, AttributeError):
            # If version parsing fails, proceed with processing to be safe
            logger.warning(
                f"Could not parse version strings for comparison. Existing: {existing_version}, Current: {document_processor_version}. Proceeding with processing.",
            )

    # Read the file from S3
    response = s3.get_object(Bucket=bucket_name, Key=object_key)
    file_content = response["Body"].read()

    content_type = utils.mimetype(file_content)

    # If a document is served from S3 with the correct DOCX mime type via a signed URL,
    # by default Edge will attempt and fail to open it in its online service
    # (Office365/Copilot) claiming a network error. We avoid this by explicitly saving
    # the DOCX file with a mimetype declaring "this is just an opaque stream of bytes."

    s3_content_type = "binary/octet-stream" if content_type == DOCX_MIME_TYPE else content_type

    clean_module = MODULE_FOR_MIME_TYPE.get(content_type)
    if not clean_module:
        logger.warning(
            f"Skipping unsupported {content_type or 'unknown'} file: {object_key} {file_content[:5]!r}",
        )
        return

    output_bytes = clean_module.clean(file_content)
    if clean_module.compare(file_content, output_bytes) == False:  # noqa: E712
        msg = f"S3 key {object_key} was visually different after cleaning."
        raise VisuallyDifferentError(msg)

    # Write the processed file back to S3
    s3.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=output_bytes,
        ContentType=s3_content_type,
        Tagging=f"DOCUMENT_PROCESSOR_VERSION={document_processor_version}",
    )

    logger.info(f"Successfully processed and rewrote {content_type}: {object_key}")


def lambda_handler(event, context):
    """
    Lambda handler that processes document cleaning requests from SQS queue.

    Event flow: S3 -> SNS -> SQS -> Lambda
    - S3 sends ObjectCreated events to SNS topic
    - SNS forwards to SQS queue (with retry and DLQ)
    - Lambda polls SQS and processes messages

    This architecture provides resilience against Lambda downtime:
    - Messages are buffered in SQS if Lambda is unavailable
    - Automatic retries with exponential backoff
    - Failed messages go to DLQ after max retries
    - No message loss during ECR image issues or Lambda failures
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Track failed message IDs for partial batch failure reporting
    # This allows successful messages to be deleted while failed ones are retried
    failed_message_ids = []

    try:
        # Initialize S3 client
        s3 = boto3.client("s3")

        # Process each SQS record
        for sqs_record in event.get("Records", []):
            message_id = sqs_record.get("messageId", "unknown")

            try:
                # Extract SNS message from SQS record body
                sns_message = json.loads(sqs_record["body"])

                # Extract S3 event from SNS message (SNS envelope format)
                s3_event = json.loads(sns_message["Message"])

                # Process each S3 record in the event
                for s3_record in s3_event.get("Records", []):
                    object_key = unquote_plus(s3_record["s3"]["object"]["key"])

                    try:
                        handle_one_record(s3_record, s3, logger)
                        logger.info(f"Successfully processed object: {object_key}")
                    except Exception:
                        logger.exception(f"Failed to process file {object_key}")
                        rollbar.report_exc_info(
                            extra_data={"object_key": object_key, "message_id": message_id, "sqs_record": sqs_record},
                        )
                        # Add message ID to failed list for partial batch failure
                        failed_message_ids.append(message_id)
                        # Don't re-raise - we've already logged and reported to rollbar
                        # The message is marked as failed via failed_message_ids list
                        break  # Stop processing remaining S3 records in this SQS message

            except Exception:
                logger.exception(f"Failed to process SQS message {message_id}")
                # Only report to rollbar if not already reported in inner handler
                if message_id not in failed_message_ids:
                    rollbar.report_exc_info(extra_data={"message_id": message_id, "sqs_record": sqs_record})
                    failed_message_ids.append(message_id)

    except Exception:
        logger.exception("Lambda execution failed with unhandled exception")
        raise

    # Return partial batch failure response if any messages failed
    # This tells SQS which messages to retry and which to delete
    if failed_message_ids:
        logger.warning(f"Failed to process {len(failed_message_ids)} message(s): {failed_message_ids}")
        return {"batchItemFailures": [{"itemIdentifier": msg_id} for msg_id in failed_message_ids]}

    logger.info("All messages processed successfully")
    return {"batchItemFailures": []}
