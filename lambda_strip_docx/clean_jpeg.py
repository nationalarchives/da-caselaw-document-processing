import subprocess
from subprocess import STDOUT, PIPE
from utils import file_wrapper, image_compare
from PIL import Image, ImageChops
import io

def _clean_jpeg(filename: str) -> None:
    output = subprocess.run(
        ["exiftool", "-all:all=", filename],
        stdout=PIPE,
        stderr=STDOUT,
        timeout=10,
    )
    print (output.stdout)

def _info(filename:str) -> bytes:
    return subprocess.run(["exiftool", filename], timeout=10, check=True, stdout=PIPE, stderr=STDOUT).stdout

# The following functions take `bytes` and return bytes from either the file or the log
# using the functions above

def clean(file_content):
    return file_wrapper(file_content=file_content, fn=_clean_jpeg, extension="jpeg")

def compare(file_content_a, file_content_b):
    return image_compare(file_content_a, file_content_b)

def info(file_content):
    return file_wrapper(file_content=file_content, fn=_info, extension="jpeg")
