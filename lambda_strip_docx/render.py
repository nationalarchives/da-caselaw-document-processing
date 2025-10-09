import pymupdf
import hashlib
from operator import ne
from itertools import compress, count
import os

TEMP_IMG_DIR = "imgtmp"

def ppm_list(bytes):
    """The PPM format is very simple, just a header and pixel data.
       Two identical images should have the same PPM output, unlike other more complicated formats"""
    doc = pymupdf.Document(stream=bytes)
    return [page.get_pixmap().tobytes("ppm") for page in doc]

def save_pngs(bytes):
    """Save PNGs for debugging purposes"""
    doc = pymupdf.Document(stream=bytes)
    for i, page in enumerate(doc):
        os.mkdir(TEMP_IMG_DIR)
        with open("{TEMP_IMG_DIR}/{i}.png", "wb") as f:
            f.write(page.get_pixmap().tobytes("png"))

def hash_pdf_image(bytes):
    """Hash the PPM image of each page together, to provide a hash which should tell us if the image has changed."""
    pages = ppm_list(bytes)
    m = hashlib.sha256()
    for page in pages:
        m.update(page)
    return (m.hexdigest())

def diff(a,b):
    """Debug helper function which shows the position of the first difference in the file."""
    index = next(compress(count(), map(ne, a, b)))
    print(a[index-50:index+50], b[index-50:index+50])

if __name__ == "__main__":
    with open("lambda_strip_docx/test_files/multipage.pdf", "rb") as f:
        print(hash_pdf_image(f.read()))
