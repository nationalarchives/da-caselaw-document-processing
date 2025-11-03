from pathlib import Path

import docx_visual_comparison


def test_visually_identical_same_docx(tmp_path):
    """Ensure two identical DOCX bytes are considered visually identical"""
    fixtures_dir = Path(__file__).resolve().parents[1] / "test_files"
    docx_path = fixtures_dir / "sample_with_author.docx"
    assert docx_path.exists(), f"Fixture missing: {docx_path}"

    docx_bytes = docx_path.read_bytes()

    # Compare the file to itself; this should always be True
    assert docx_visual_comparison.visually_identical(docx_bytes, docx_bytes) is True


def test_visually_identical_different_docx(tmp_path):
    """Ensure two different DOCX bytes are considered visually different"""
    fixtures_dir = Path(__file__).resolve().parents[1] / "test_files"
    docx_path1 = fixtures_dir / "sample_with_author.docx"
    docx_path2 = fixtures_dir / "sample_with_author_with_comments.docx"
    assert docx_path1.exists(), f"Fixture missing: {docx_path1}"
    assert docx_path2.exists(), f"Fixture missing: {docx_path2}"

    docx_bytes1 = docx_path1.read_bytes()
    docx_bytes2 = docx_path2.read_bytes()

    # Compare two different files; this should be False
    assert docx_visual_comparison.visually_identical(docx_bytes1, docx_bytes2) is False


def test_visually_identical_docx_with_diffrent_core_properties(tmp_path):
    """Ensure two DOCX bytes with different core properties are visually identical"""
    fixtures_dir = Path(__file__).resolve().parents[1] / "test_files"
    docx_path1 = fixtures_dir / "sample_with_author.docx"
    docx_path2 = fixtures_dir / "sample_with_author_cleansed.docx"
    assert docx_path1.exists(), f"Fixture missing: {docx_path1}"
    assert docx_path2.exists(), f"Fixture missing: {docx_path2}"

    docx_bytes1 = docx_path1.read_bytes()
    docx_bytes2 = docx_path2.read_bytes()

    # Compare two files that differ only in core properties; this should be True
    assert docx_visual_comparison.visually_identical(docx_bytes1, docx_bytes2) is True
