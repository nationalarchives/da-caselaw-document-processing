import clean_pdf
from render_pdf import hash_pdf_image

def test_clean_pdf_works(input_pdf):
    # Note: we can't check the image is the same as it contains annotations which get flattened onto the image

    # alice in hex-encoded UTF-16, as it may appear in qdf format
    alice= b"0041006c006900630065"

    # the input PDF contains Author data (via QPDF)
    input_qdf = clean_pdf.qdf(input_pdf)
    assert b"%QDF-1.0" in input_qdf
    assert b"Author" in input_qdf
    assert alice in input_qdf or b"Alice" in input_qdf

    # actually process the file
    output_pdf = clean_pdf.clean(input_pdf)

    # once cleaned, QPDF outputs no metadata in QDF of processed file
    output_qdf = clean_pdf.qdf(output_pdf)
    assert b"%QDF-1.0" in input_qdf
    assert b"Author" not in output_qdf
    assert b"Alice" not in output_qdf and alice not in output_qdf

    # exiftool reports no recoverable metadata
    clean_pdf.verify_removal(output_pdf)

    ## pdfcpu outputs no metadata
    pdf_info = clean_pdf.info(output_pdf)
    assert b"Author: \n" in pdf_info
    assert b"Subject: \n" in pdf_info
    assert b"PDF Producer: pdfcpu" in pdf_info
    assert b"Title: \n" in pdf_info

def test_multi_page_clean_unchanged(input_multipage_pdf):
    pdf = input_multipage_pdf
    input_hash = hash_pdf_image(pdf)
    output_pdf = clean_pdf.clean(pdf)
    output_hash = hash_pdf_image(output_pdf)
    assert input_hash == output_hash
