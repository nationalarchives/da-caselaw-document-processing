def pad_name(name):
    split_name_ints = list(name)
    split_name_chars = [chr(x) for x in split_name_ints]
    unicode_name = "\x00" + "\x00".join(split_name_chars)
    return unicode_name.encode('utf-8')

def check_sample_pdf_metadata_is_stripped(pdf_bytes):
    names = [b"Alice Johnson", b"Bob Smith", b"Carol Davis"]
    padded_names = [pad_name(name) for name in names]
    breakpoint()
    for padded_name in padded_names:
        assert padded_name not in pdf_bytes

def test_x():
    check_sample_pdf_metadata_is_stripped(b"")
