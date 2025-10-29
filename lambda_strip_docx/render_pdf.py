import hashlib
from pathlib import Path

import pymupdf

DEBUG_IMG_DIR = "debug-images"


def ppm_list(image_bytes):
    """The PPM format is very simple, just a header and pixel data.
    Two identical images should have the same PPM output, unlike other more complicated formats"""
    doc = pymupdf.Document(stream=image_bytes)
    return [page.get_pixmap().tobytes("ppm") for page in doc]


def save_pngs(image_bytes) -> None:
    """Save PNGs for debugging purposes"""
    doc = pymupdf.Document(stream=image_bytes)
    for i, page in enumerate(doc):
        Path(DEBUG_IMG_DIR).mkdir()
        with Path(f"{DEBUG_IMG_DIR}/{i}.png").open("wb") as f:
            f.write(page.get_pixmap().tobytes("png"))


def hash_pdf_image(image_bytes) -> str:
    """Hash the PPM image of each page together, to provide a hash which should tell us if the image has changed."""
    pages = ppm_list(image_bytes)
    m = hashlib.sha256()
    for page in pages:
        m.update(page)
    return m.hexdigest()


def visually_identical(first_content, second_content) -> bool:
    """Are these two PDFs visually identical?"""
    return hash_pdf_image(first_content) == hash_pdf_image(second_content)
