
import sys, atexit

import readchar as rc


def flush_all():
    sys.stderr.flush()
    sys.stdout.flush()

atexit.register(flush_all)


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
    print('\x1b[30m', values, '\x1b[0m', **kw)


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
