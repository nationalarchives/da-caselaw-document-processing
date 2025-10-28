import subprocess
from subprocess import STDOUT, PIPE
from utils import file_wrapper, image_compare
from exceptions import CleansingError
import io


def _clean_png(filename: str) -> None:
    # Preserve the ICC profile as that can change image colours
    output = subprocess.run(
        ["exiftool", "-all:all=", filename],
        stdout=PIPE,
        stderr=STDOUT,
        timeout=10,
        check=True,
    )

    output_string = output.stdout.decode("utf-8")
    if "Warning:" in output_string:
        raise CleansingError(f"Unexpected exiftool warning {output_string}")


def _info(filename: str) -> bytes:
    return subprocess.run(
        ["exiftool", filename], timeout=10, check=True, stdout=PIPE, stderr=STDOUT
    ).stdout


# The following functions take `bytes` and return bytes from either the file or the log
# using the functions above


def clean(file_content):
    return file_wrapper(file_content=file_content, fn=_clean_png, extension="png")


def compare(file_content_a, file_content_b):
    return image_compare(file_content_a, file_content_b)


def info(file_content):
    return file_wrapper(file_content=file_content, fn=_info, extension="png")
