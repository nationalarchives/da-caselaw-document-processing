import clean_jpeg

def test_clean_jpeg_removes_author_metadata(input_jpeg):
    original_info = clean_jpeg.info(input_jpeg).decode('utf-8')
    assert "Dennis Hogers" in original_info

    # actually process the file
    output_jpeg = clean_jpeg.clean(input_jpeg)
    output_info = clean_jpeg.info(output_jpeg).decode('utf-8')
    assert "Dennis Hogers" not in output_info

    assert clean_jpeg.compare(input_jpeg, output_jpeg)
