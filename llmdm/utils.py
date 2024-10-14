import os
import sys
from contextlib import contextmanager

SAVE_DIR = "saved"


def sanitize(name):
    for token in " -,_'":
        name = "".join(name.split(token))

    return name.lower()


@contextmanager
def suppress_stdout():
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")
    try:
        yield
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
