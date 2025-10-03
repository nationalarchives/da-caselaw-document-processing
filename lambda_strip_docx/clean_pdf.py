import subprocess
from subprocess import STDOUT, PIPE
import os
from tempfile import NamedTemporaryFile


def clean_pdf(pdf_filename: str, verify_removal: bool = True, compressed=True) -> None:
    # assert that the pdf exists
    if not os.path.exists(pdf_filename):
        raise RuntimeError(f"No pdf found at {pdf_filename}")

    # Add a blank metadata update to the PDF and linearize it to remove it entirely
    # both write back to pdf_filename
    subprocess.run(["exiftool", "-all:all=", pdf_filename], timeout=10, check=True)
    subprocess.run(
        ["qpdf", "--linearize", "--flatten-annotations=all", "--replace-input", pdf_filename], timeout=10, check=True
    )

    if verify_removal:
        # attempting to restore metadata will fail if we've linearized -- good!
        output = subprocess.run(
            ["exiftool", "-pdf-update:all=", pdf_filename],
            stdout=PIPE,
            stderr=STDOUT,
            timeout=10,
        )
        if b"no previous ExifTool update" not in output.stdout:
            raise RuntimeError("ExifTool data reversable")

    # uncompress the PDF if required for checking purposes
    if not compressed:
        subprocess.run(["qpdf", "--qdf", "--object-streams=disable", "--replace-input", pdf_filename], timeout=10, check=True)


def clean(file_content, compressed=True):
    # create temp file from file content
    with NamedTemporaryFile(suffix="_temp.pdf") as tempfile:
        tempfile.file.write(file_content)
        tempfile.file.close()
        clean_pdf(tempfile.name, True, compressed=compressed)
        with open(tempfile.name, "rb") as f:
            output_bytes = f.read()
        return output_bytes
    # return bytesio of temp file
