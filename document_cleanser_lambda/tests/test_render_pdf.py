from clean_pdf import compare


def test_visually_identical(input_multipage_pdf):
    pdf = input_multipage_pdf
    pdf_plus_crud = pdf + b"trailing junk"
    assert compare(pdf, pdf_plus_crud)
