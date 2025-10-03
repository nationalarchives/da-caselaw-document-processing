import clean_pdf


def pad_name(name):
    split_name_ints = list(name)
    split_name_chars = [chr(x) for x in split_name_ints]
    unicode_name = "\x00" + "\x00".join(split_name_chars)
    return unicode_name.encode("utf-8")


def check_sample_pdf_metadata_is_stripped(pdf_bytes):
    names = [b"Alice Johnson", b"Bob Smith", b"Carol Davis"]
    padded_names = [pad_name(name) for name in names]
    for padded_name in padded_names:
        assert padded_name not in pdf_bytes


def test_cleaning():
    check_sample_pdf_metadata_is_stripped(b"")


def test_cleaning_pdf_works_at_all(input_pdf):
    # alice in hex-encoded UTF-16, as it appears in qdf format
    alice = b"0041006c006900630065"

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
