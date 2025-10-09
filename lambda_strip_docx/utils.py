from tempfile import NamedTemporaryFile

def file_wrapper(file_content, fn) -> bytes:
    """Since the PDF utilities require filenames and not bytestrings, write the bytestring to a file,
       and call a partial function which expects a filename. Return the return value of the function,
       or the output bytes if the function returns nothing"""

    with NamedTemporaryFile(suffix="_temp.pdf") as tempfile:
        tempfile.file.write(file_content)
        tempfile.file.close()
        retval = fn(filename=tempfile.name)
        if retval is not None:
            return retval
        with open(tempfile.name, "rb") as f:
            output_bytes = f.read()
        return output_bytes
