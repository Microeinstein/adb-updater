
import sqlite3
from pathlib import Path
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

from .misc import optional_decor_args


@optional_decor_args
def a_autoexit(func):
    async def wrapper(self, *a, **kw):
        try:
            ret = await func(self, *a, **kw)
        finally:
            for ak, av in self.__dict__.copy().items():  # no descriptors
                if hasattr(av, '__exit__'):
                    av.__exit__(None, None, None)
                    delattr(self, ak)
        return ret
    
    return wrapper


CM = AbstractContextManager[object]

@dataclass
class ContextProp():
    factory: Callable[[],CM]|None = field(default=None)
    pub: str = field(init=False)
    priv: str = field(init=False)

    def __set_name__(self, owner, name):
        self.pub = name
        self.priv = '_' + name

    def __get__(self, obj: object, objtype=None):
        if not self.factory:
            annot: Callable[[],CM] = obj.__annotations__[self.pub]
            self.factory = annot
        value = getattr(obj, self.priv, None)
        if not value:
            value = self.factory().__enter__()
            setattr(obj, self.priv, value)
        return value

    def __set__(self, obj, value):
        self.__delete__(obj)
        setattr(obj, self.priv, value)
    
    def __delete__(self, obj):
        old: CM = getattr(obj, self.priv, None)
        if not old:
            return
        _ = old.__exit__(None, None, None)
        delattr(obj, self.priv)


# https://stackoverflow.com/a/65644970
class SQLite:
    """
    A minimal sqlite3 context handler that removes pretty much all
    boilerplate code from the application level.
    """
    connection: sqlite3.Connection
    cursor: sqlite3.Cursor

    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        # do not forget this or you will not be able to use methods of the
        # context handler in your with block
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.connection.close()
