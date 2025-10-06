import clean_pdf

def test_clean_pdf_works(input_pdf):
    # alice in hex-encoded UTF-16, as it appears in qdf format
    alice= b"0041006c006900630065"

    # input pdf must be modified with `qpdf --qdf` so we can see all the data neatly
    assert b"%QDF-1.0" in input_pdf
    assert b"Author" in input_pdf
    assert b"Creator" in input_pdf
    assert b"Producer" in input_pdf
    assert alice in input_pdf

    output_pdf = clean_pdf.clean(input_pdf, compressed=False)
    assert b"%QDF-1.0" in input_pdf
    assert b"Author" not in output_pdf
    assert b"Creator" not in output_pdf
    assert b"Producer" not in output_pdf
    assert alice not in output_pdf
