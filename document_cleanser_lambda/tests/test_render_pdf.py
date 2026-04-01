import re

from clean_pdf import compare
from render_pdf import hash_pdf_visually


def test_visually_identical(input_multipage_pdf):
    pdf = input_multipage_pdf
    pdf_plus_crud = pdf + b"trailing junk"
    assert compare(pdf, pdf_plus_crud)


def test_hash_pdf_visually_returns_valid_sha256_hash(input_multipage_pdf):
    """Test that hash_pdf_visually returns a valid SHA256 hash string"""
    result = hash_pdf_visually(input_multipage_pdf)
    # SHA256 produces 64 character hex string
    assert isinstance(result, str)
    assert len(result) == 64
    assert re.match(r"^[a-f0-9]{64}$", result)


def test_hash_pdf_visually_is_deterministic(input_multipage_pdf):
    """Test that the same PDF always produces the same hash"""
    hash1 = hash_pdf_visually(input_multipage_pdf)
    hash2 = hash_pdf_visually(input_multipage_pdf)
    assert hash1 == hash2


def test_hash_pdf_visually_differs_for_different_pdfs(input_multipage_pdf, input_pdf):
    """Test that different PDFs produce different hashes"""
    hash1 = hash_pdf_visually(input_multipage_pdf)
    hash2 = hash_pdf_visually(input_pdf)
    assert hash1 != hash2


def test_hash_pdf_visually_ignores_trailing_data(input_multipage_pdf):
    """Test that trailing non-PDF data doesn't affect the visual hash"""
    original_hash = hash_pdf_visually(input_multipage_pdf)
    pdf_with_junk = input_multipage_pdf + b"trailing junk data"
    modified_hash = hash_pdf_visually(pdf_with_junk)
    assert original_hash == modified_hash


def test_hash_pdf_visually_handles_single_page_pdf(input_pdf):
    """Test that hash_pdf_visually works with single-page PDFs"""
    result = hash_pdf_visually(input_pdf)
    assert isinstance(result, str)
    assert len(result) == 64
