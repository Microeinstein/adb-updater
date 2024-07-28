
from dataclasses import dataclass, field
from inspect import getmro
from typing import Callable, Any


def get_base_classes(cls):
    return getmro(cls)


AnyFunc = Callable[..., Any]
Deco = AnyFunc | Callable[[AnyFunc], Any]

def optional_decor_args(orig: Deco) -> Deco:
    def wrapper(func: AnyFunc|None = None, /, *a, **kwargs):
        if func and callable(func) and not a and not kwargs:
            # not effective with only one positional callable
            return orig(func, *a, **kwargs)
        return lambda func: orig(func, *a, **kwargs)
    
    return wrapper


@dataclass
class PropMessage:
    msg: str
    default: ... = field(default=None)
    pub: str = field(init=False)
    priv: str = field(init=False)

    def __set_name__(self, owner, name):
        self.pub = name
        self.priv = '_' + name

    def __get__(self, obj, objtype=None):
        value = getattr(obj, self.priv, self.default)
        if not value:
            raise RuntimeError(self.msg)
        return value

    def __set__(self, obj, value):
        setattr(obj, self.priv, value)
