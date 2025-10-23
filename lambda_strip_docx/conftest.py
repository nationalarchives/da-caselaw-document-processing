import os
import pytest
import boto3
from moto import mock_aws
from clean_docx import strip_docx_author_metadata_from_docx
from lambda_function import lambda_handler, __version__

def load_bytes(filename):
    with open(filename, "rb") as f:
        return f.read()

# Fixtures

def test_file(filename):
    return os.path.join(os.path.dirname(__file__), "test_files", filename)

@pytest.fixture
def input_docx():
    """Load sample DOCX file as bytes"""
    return load_bytes(test_file("sample_with_author.docx"))

@pytest.fixture
def input_pdf():
    """Load sample PDF file as bytes"""
    return load_bytes(test_file("sample_pdf_with_author.pdf"))

@pytest.fixture
def input_jpeg():
    """Load sample JPEG file as bytes"""
    """https://commons.wikimedia.org/w/index.php?title=Category:Public_domain&from=S#/media/File:Schetsen_van_vogels.jpeg"""
    return load_bytes(test_file("art.jpeg"))

@pytest.fixture
def input_multipage_pdf():
    """Load sample PDF file as bytes"""
    return load_bytes(test_file("multipage.pdf"))

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
def s3_with_docx_file(s3_setup, input_docx):
    """S3 environment with a DOCX file uploaded"""
    s3_client, bucket_name = s3_setup
    object_key = "sample_with_author.docx"

    # Upload the DOCX file to S3
    s3_client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=input_docx,
        ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )

    return s3_client, bucket_name, object_key

@pytest.fixture
def s3_with_multipage_pdf_file(s3_setup, input_multipage_pdf):
    """S3 environment with a PDF file uploaded"""
    s3_client, bucket_name = s3_setup
    object_key = "multipage.pdf"

    # Upload the DOCX file to S3
    s3_client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=input_multipage_pdf,
        ContentType='application/pdf'
    )

    return s3_client, bucket_name, object_key


@pytest.fixture
def s3_with_pdf_file(s3_setup, input_pdf):
    """S3 environment with a PDF file uploaded"""
    s3_client, bucket_name = s3_setup
    object_key = "sample_pdf_with_author.pdf"

    # Upload the DOCX file to S3
    s3_client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=input_pdf,
        ContentType='application/pdf'
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
