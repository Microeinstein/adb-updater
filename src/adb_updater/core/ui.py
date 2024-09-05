
import os, sys

import colorama
import readchar as rc
from colorama import ansi  # pyright: ignore[reportUnusedImport] (import from here to init library)


colorama.init()


# https://stackoverflow.com/a/10455937
if os.name == "nt":
    import ctypes

    class _CursorInfo(ctypes.Structure):
        _fields_ = [("size", ctypes.c_int), ("visible", ctypes.c_byte)]

    CI = _CursorInfo()
    HANDLE = ctypes.windll.kernel32.GetStdHandle(-11)


def hide_cursor(stream=sys.stdout):
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.GetConsoleCursorInfo(HANDLE, ctypes.byref(CI))
        CI.visible = False
        ctypes.windll.kernel32.SetConsoleCursorInfo(HANDLE, ctypes.byref(CI))
    elif os.name == "posix":
        stream.write("\033[?25l")
        stream.flush()


def show_cursor(stream=sys.stdout):
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.GetConsoleCursorInfo(HANDLE, ctypes.byref(CI))
        CI.visible = True
        ctypes.windll.kernel32.SetConsoleCursorInfo(HANDLE, ctypes.byref(CI))
    elif os.name == "posix":
        stream.write("\033[?25h")
        stream.flush()


def save_cursor():
    """
    Warning: not stackable
    """
    print('\x1b7', end='', flush=True)

def restore_cursor_clear():
    print('\x1b8\x1b[0J', end='', flush=True)


# def flush_all():
#     # pyinstaller bug
#     sys.stderr.write('\n')
#     sys.stdout.write('\n')
#     sys.stderr.flush()
#     sys.stdout.flush()

# atexit.register(flush_all)


def middle_ellipsis(txt: str, maxwidth: int):
    l = len(txt)
    if l <= maxwidth:
        return txt
    l1 = (maxwidth - 1) // 2
    l2 = maxwidth // 2
    l1 += maxwidth - (l1 + 1 + l2)
    return f"{txt[:l1]}…{txt[l-l2:]}"


def title(*values: object, **kw):
    text = (kw.get('sep', ' ')).join(values)
    kw.update(sep='', file=sys.stderr, flush=True)
    print('\n\x1b[1m', text, '\x1b[0m', **kw)


def error(*values: object, **kw):
    values = (kw.get('sep', ' ')).join(values)
    kw.update(sep='', file=sys.stderr, flush=True)
    print('\x1b[91m', values, '\x1b[0m', **kw)


def ask_yes_no(prompt: str, default=False):
    print(prompt, ' ', '[Y/n]' if default else '[y/N]', ': ', sep='', end='', flush=True)
    try:
        while True:
            k = rc.readkey()
            if k == rc.key.ENTER:
                return default
            if k == 'y':
                return True
            if k in ('n', rc.key.ESC):
                return False
    except KeyboardInterrupt:
        return False
    finally:
        print()
