import clean_png

def test_clean_png_removes_author_metadata(input_png):
    original_info = clean_png.info(input_png).decode('utf-8')
    assert "Some Name" in original_info

    # actually process the file
    output_png = clean_png.clean(input_png)
    output_info = clean_png.info(output_png).decode('utf-8')
    assert "Some Name" not in output_info

    assert clean_png.compare(input_png, output_png)
