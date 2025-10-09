import pymupdf
import hashlib
from operator import ne
from itertools import compress, count

def ppm_list(bytes):
    doc = pymupdf.Document(stream=bytes)
    return [page.get_pixmap().tobytes("png") for page in doc]

def hash_image(bytes):
    pages = ppm_list(bytes)
    m = hashlib.sha256()
    for page in pages:
        m.update(page)
    return (m.hexdigest())

def diff(a,b):
    index = next(compress(count(), map(ne, a, b)))
    print(a[index-50:index+50], b[index-50:index+50])

if __name__ == "__main__":
    with open("lambda_strip_docx/test_files/multipage.pdf", "rb") as f:
        print(hash_image(f.read()))
