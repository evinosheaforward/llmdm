import os
import queue
import sys
import threading
import time
from contextlib import contextmanager

SAVE_DIR = "saved"
KILL_SEQUENCE = "Kill sequence: 123987"

text_queue = queue.Queue()


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


def slow_print(text, delay=0.01):
    """Function to print text slowly character by character."""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()


def render_text(text):
    """Function to add text to the queue for display."""
    # have to fix issue where suppress_stdout is overriding this
    # text_queue.put(text)
    slow_print(text)


def prompt_user_input(text):
    text_queue.join()
    return input(text)


def display_thread():
    """Function that runs on a separate thread, displaying text from the queue."""
    while True:
        text = text_queue.get()
        if text is None:
            time.sleep(1)
            continue
        elif text == KILL_SEQUENCE:
            return
        slow_print(text)
        text_queue.task_done()


thread = threading.Thread(target=display_thread)


def start_display_thread():
    thread.start()


def stop_display_thread():
    text_queue.put(KILL_SEQUENCE)
    thread.join()
