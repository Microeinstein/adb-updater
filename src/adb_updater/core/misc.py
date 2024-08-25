
import itertools, inspect

from dataclasses import dataclass, field
from inspect import getmro, get_annotations
from collections.abc import MutableMapping, Generator, Iterable
from abc import ABC
from typing import Callable, Any, TypeVar, TypeAlias, Generic, cast, get_origin, get_args
from typing_extensions import Self, override


T = TypeVar('T')
R = TypeVar('R')

jvalue: TypeAlias = None | str | int | float | bool
J = TypeVar('J')
jlist: TypeAlias = list[J]
jobj: TypeAlias = dict[str, J]


class Dummy(Generic[T]):
    def __init__(self, **kw: T):
        self.__dict__ = kw
    
    def __getattr__(self, name: str) -> T:
        raise AttributeError(name=name, obj=self)
    
    @override
    def __setattr__(self, name: str, value: Any, /) -> None:
        super().__setattr__(name, value)


class Proxy(ABC, Generic[T]):
    __slots__ = '__wrapped__ __proxy__ __routines__'.split()
    __wrapped__: T
    """Original object"""
    __proxy__: Self
    """Allow raw access to Proxy members"""
    
    @classmethod
    def attach_proxy(cls, obj: T):
        p = cls()
        Proxy.__setattr__(p, '__wrapped__', obj)
        if cls == _Proxy:
            return p
        
        routines = set()
        for k, _v in inspect.getmembers(cls, inspect.isroutine):
            routines.add(k)
            
        Proxy.__setattr__(p, '__routines__', routines)
        Proxy.__setattr__(p, '__proxy__', _Proxy.attach_proxy(p))
        
        class mixed(obj.__class__, Generic[R]):  # dummy class for static type checkers
            __getattribute__ = cls.__getattribute__
            __setattr__ = cls.__setattr__
            __delattr__ = cls.__delattr__
        
        return cast(Self|mixed[T], p)
    
    @override
    def __getattribute__(self, k: str):
        sget = super().__getattribute__
        
        # allow raw access; or normal access to routines
        if k in sget('__slots__') or k in sget('__routines__'):
            return sget(k)
        
        w = sget('__wrapped__')
        d = sget('__dict__')
        if k == '__dict__':
            return w.__dict__ | d
        
        # get self value, no class defaults
        try: return d[k]
        except KeyError: pass
        
        # get from custom getter
        try: return sget('__getattr__')(k)
        except AttributeError: pass
        
        # get from wrapped object
        try: return getattr(w, k)
        except AttributeError: pass
        
        # fallback to class default if any
        return sget(k)


class _Proxy(Proxy[T], Generic[T]):
    @override
    def __getattribute__(self, k: str):
        oget = object.__getattribute__
        return oget(oget(self, '__wrapped__'), k)


class Serializable(ABC):
    SERIALIZE: list[str]
    
    @classmethod
    def load(cls, data: dict[str, object], **extra):
        for k in cls.SERIALIZE:
            if k not in data:
                raise RuntimeError(f"Missing attribute {k!r}.")
        return cls(**data, **extra)
    
    def save(self) -> dict[str, object]:
        return {k: getattr(self, k) for k in self.SERIALIZE}


AttrMap: TypeAlias = MutableMapping[str, Any]
M = TypeVar('M', bound=AttrMap|dict[str, Any])

_sequences = { set, list, tuple }
_known_annot = {
    Serializable: (lambda o, v: o.load(v), lambda o, v: o.save(v))
}

class AttrDict(Proxy[M], Generic[M], AttrMap):
    @override
    def __delitem__(self, k: str):
        return self.__wrapped__.__delitem__(k)
    
    @override
    def __iter__(self):
        return self.__wrapped__.__iter__()
    
    @override
    def __len__(self):
        return self.__wrapped__.__len__()

    @classmethod
    def convert_annot(cls, annot: type[R], v: Any, undo: bool) -> R|Any:
        orig: type|None = get_origin(annot)
        if not orig:
            orig = annot
        
        if orig in _sequences:
            arg0 = get_args(annot)[0]
            return (orig if not undo else list)(
                cls.convert_annot(arg0, e, undo) for e in v
            )
        
        for base in get_base_classes(orig):
            conv = _known_annot.get(base, None)
            if not conv:
                continue
            return (conv[0] if not undo else conv[1])(orig, v)
        
        return v

    @classmethod
    def _convert_annot(cls, k: str, v: Any, undo: bool):
        annot: type
        for base in get_base_classes(cls):
            annot = get_annotations(base).get(k)
            if annot:
                break
        else:
            return v
        
        return cls.convert_annot(annot, v, undo)

    @override
    def __getitem__(self, k: str) -> Any:
        v = self.__wrapped__.__getitem__(k)
        if type(v) != AttrDict and isinstance(v, dict):
            v = AttrDict.attach_proxy(v)
        
        v2 = self.__proxy__.__class__._convert_annot(k, v, False)
        # if v2 is not v:
        #     self[k] = v2
        return v2
    
    @override
    def __setitem__(self, k: str, v: Any):
        v2 = self.__proxy__.__class__._convert_annot(k, v, True)
        return self.__wrapped__.__setitem__(k, v2)
    
    def __getattr__(self, k: str):
        if k.startswith('_'):  # internal whatever not found in original object
            raise AttributeError()
        try:
            return self.__getitem__(k)
        except KeyError:
            raise AttributeError()
    
    @override
    def __setattr__(self, k: str, v: Any):
        if k in self:
            return self.__setitem__(k, v)
        self.__wrapped__.__setattr__(k, v)
    
    @override
    def __delattr__(self, k: str):
        if k in self:
            return self.__delitem__(k)
        self.__wrapped__.__delattr__(k)
    
    def set_class_defaults(self):
        for k, v in self.__proxy__.__class__.__dict__.items():
            if not k.startswith('_'):
                self.setdefault(k, self._convert_annot(k, v, False))


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


size_units = 'KMGTPEZYRQ'

def human_to_bytes(size: str) -> int:
    size = size.upper()
    if size.endswith("B"):
        size = size[:-1]

    prefix = size[-1]
    num = float(size[:-1])
    exp = size_units.find(prefix)
    
    if exp >= 0:
        return int(num * 1024 ** (exp+1))
    else:
        return int(num)


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
