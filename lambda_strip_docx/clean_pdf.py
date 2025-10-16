import subprocess
from subprocess import STDOUT, PIPE
from utils import file_wrapper
from render_pdf import visually_identical

def _qdf(filename: str) -> None:
    """Convert a PDF file into QDF format (which is still a valid PDF) since QDF files are
    readable and uncompressed."""
    subprocess.run(["qpdf", "--qdf", "--object-streams=disable", "--replace-input", filename], timeout=10, check=True)

def _remove_annotations(filename: str) -> None:
    output = subprocess.run(["pdfcpu", "annot", "remove", filename], timeout=10, stdout=PIPE, stderr=STDOUT)

def _remove_properties(filename: str) -> None:
    # Removing all the properties [nothing specified] does not appear to remove the predefined ones, like Author.
    subprocess.run(["pdfcpu", "prop", "remove", filename], timeout=10, check=True)
    subprocess.run(["pdfcpu", "prop", "add", filename, "Author=", "Subject=", "Title="], timeout=10, check=True)
    subprocess.run(["pdfcpu", "prop", "remove", filename, "Author", "Subject", "Title"], timeout=10, check=True)

def _info(filename:str) -> bytes:
    return subprocess.run(["pdfcpu", "info", filename], timeout=10, check=True, stdout=PIPE, stderr=STDOUT).stdout

def _verify_removal(filename: str) -> bool:
    """Verify that exiftool cannot restore an author name"""
    output = subprocess.run(
        ["exiftool", "-pdf-update:all=", filename],
        stdout=PIPE,
        stderr=STDOUT,
        timeout=10,
    )
    if b"no previous ExifTool update" not in output.stdout:
        raise RuntimeError("ExifTool data reversable")

    # Return something to avoid wrapper returning the file contents
    return True

def _clean_pdf(filename: str) -> None:
    """Add a blank metadata update to the PDF and linearize it to remove it entirely.
       Both processes write back to the file at filename."""

    _remove_annotations(filename)
    _remove_properties(filename)

# The following functions take `bytes` and return bytes from either the file or the log
# using the functions above

def clean(file_content):
    return file_wrapper(file_content=file_content, fn=_clean_pdf)

def compare(file_content_a, file_content_b):
    return visually_identical(file_content_a, file_content_b)

def qdf(file_content):
    return file_wrapper(file_content=file_content, fn=_qdf)

def verify_removal(file_content):
    return file_wrapper(file_content=file_content, fn=_verify_removal)

def info(file_content):
    return file_wrapper(file_content=file_content, fn=_info)
