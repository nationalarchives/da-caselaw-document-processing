from tempfile import NamedTemporaryFile
from PIL import Image, ImageChops
import io
import filetype


def file_wrapper(file_content, fn, extension) -> bytes:
    """Since command line utilities require filenames and not bytestrings, write the bytestring to a file,
    and call a partial function which expects a filename. Return the return value of the function,
    or the output bytes if the function returns nothing"""

    with NamedTemporaryFile(suffix=f"_temp.{extension}") as tempfile:
        tempfile.file.write(file_content)
        tempfile.file.close()
        retval = fn(filename=tempfile.name)
        if retval is not None:
            return retval
        with open(tempfile.name, "rb") as f:
            output_bytes = f.read()
        return output_bytes


def image_compare(file_content_a, file_content_b):
    """Do two files look exactly the same?"""
    image_a = Image.open(io.BytesIO(file_content_a)).convert("RGB")
    image_b = Image.open(io.BytesIO(file_content_b)).convert("RGB")
    diff = ImageChops.difference(image_a, image_b)
    return not diff.getbbox()


def mimetype(document_bytes) -> str:
    """Return a mimetype based on the content of the document"""
    kind = filetype.guess(document_bytes)
    if not kind or not kind.mime:
        return ""
    return kind.mime
