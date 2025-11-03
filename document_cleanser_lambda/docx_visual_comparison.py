import subprocess
import tempfile
from pathlib import Path

import render_pdf


def visually_identical(first_content, second_content) -> bool:
    """Are these two docx files visually identical?"""
    first_pdf = convert_docx_to_pdf(first_content)
    second_pdf = convert_docx_to_pdf(second_content)

    return render_pdf.visually_identical(first_pdf, second_pdf)


def convert_docx_to_pdf(docx_bytes) -> bytes:
    """Convert DOCX bytes to PDF bytes using LibreOffice (soffice) in headless mode.

    It requires `soffice` to be available in PATH (install LibreOffice in the Dockerfile).

    Raises RuntimeError with a helpful message if conversion fails or `soffice` is missing.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        docx_path = tmpdir_path / "input.docx"
        with Path.open(docx_path, "wb") as f:
            f.write(docx_bytes)

        try:
            subprocess.run(  # noqa: S603
                [
                    "/usr/bin/soffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    str(docx_path),
                    "--outdir",
                    str(tmpdir_path),
                ],
                check=False,
                shell=False,
            )
        except subprocess.CalledProcessError as exc:
            error_message = f"LibreOffice failed to convert DOCX to PDF: {exc.stderr.decode(errors='ignore')}"
            raise RuntimeError(error_message) from exc
        pdf_path = tmpdir_path / "input.pdf"

        with Path.open(pdf_path, "rb") as f:
            return f.read()
