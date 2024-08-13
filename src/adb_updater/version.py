import sys

_name = sys.modules[__name__].__package__
if not _name:
    raise RuntimeError("Not a module.")
NAME = _name.replace('_', '-')

VERSION = '1.0'
