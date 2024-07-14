
from dataclasses import dataclass, field
from typing import Callable

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


@dataclass
class ContextProp:
    factory: Callable = field(default=None)

    def __set_name__(self, owner, name):
        self.pub = name
        self.priv = '_' + name

    def __get__(self, obj, objtype=None):
        if not self.factory:
            self.factory = obj.__annotations__[self.pub]
        value = getattr(obj, self.priv, None)
        if not value:
            value = self.factory().__enter__()
            setattr(obj, self.priv, value)
        return value

    def __set__(self, obj, value):
        self.__delete__(obj)
        setattr(obj, self.priv, value)
    
    def __delete__(self, obj):
        old = getattr(obj, self.priv, None)
        if not old:
            return
        old.__exit__(None, None, None)
        delattr(obj, self.priv)
