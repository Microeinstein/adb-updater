
import itertools

from dataclasses import dataclass, field
from inspect import getmro
from collections.abc import Generator, Iterable
from typing import Callable, Any, TypeVar


T = TypeVar('T')


def get_base_classes(cls):
    return getmro(cls)


def round_robin(it: Iterable[T], key: Callable[[T], Any]) -> Generator[T]:
    srt = sorted(it, key=key)
    if not srt:
        return
    
    cursors = dict()  # key: start_index
    last_key = None
    for i, x in enumerate(srt):
        k = key(x)
        if last_key is None or last_key != k:
            cursors[k] = i
            last_key = k
    
    k2, v2 = next(iter(cursors.items()))
    for (k1, v1), (k2, v2) in itertools.pairwise(cursors.items()):
        cursors[k1] = iter(range(v1, v2))
    cursors[k2] = iter(range(v2, len(srt)))
    
    while cursors:
        exhaust = []
        for k, c in cursors.items():
            i = next(c, None)
            if i is None:
                exhaust.append(k)
                continue
            yield srt[i]
        for k in exhaust:
            del cursors[k]


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
