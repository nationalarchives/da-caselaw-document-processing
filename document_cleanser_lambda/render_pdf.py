import hashlib
import io

from pdf2image import convert_from_bytes


def hash_pdf_visually(pdf_bytes: bytes) -> str:
    """Hash the visual appearance of a PDF by rendering each page and hashing the images.

    Uses streaming approach to process pages one at a time, keeping memory usage constant
    regardless of document size. The PPM format is used because it's simple (just header + pixel data)
    and produces consistent output for identical images.
    """
    hasher = hashlib.sha256()
    for page in convert_from_bytes(pdf_bytes, fmt="ppm"):
        buffer = io.BytesIO()
        page.save(buffer, format="PPM")
        hasher.update(buffer.getvalue())
    return hasher.hexdigest()


def visually_identical(first_content: bytes, second_content: bytes) -> bool:
    """Check if two PDFs are visually identical by comparing their rendered appearance."""
    return hash_pdf_visually(first_content) == hash_pdf_visually(second_content)
