
from abc import ABC
from typing import TypeVar

import tomlkit


# @dataclass
# class ConfigProp:
#     def __set_name__(self, owner, name):
#         self.key = name
#
#     def __get__(self, facade, objtype=None):
#         return getattr(getattr(facade, 'config'), self.key)
#
#     def __set__(self, facade, value):
#         setattr(getattr(facade, 'config'), self.key, value)


T = TypeVar('T', bound='TOMLConfig')

class TOMLConfig:
    def __post_init__(self):
        ...
    
    def __getattr__(self, name):
        if not name.startswith('__'):
            return self.__toml__[name]
        return super().__getattribute__(name)
    
    def __setattr__(self, name, value):
        if not name.startswith('__'):
            self.__toml__[name] = value
        super().__setattr__(name, value)
    
    def __delattr__(self, name):
        if not name.startswith('__'):
            del self.__toml__[name]
        super().__delattr__(name)
    
    @classmethod
    def load(cls: type[T], fin) -> T:
        data = tomlkit.load(fin)
        # update() will convert TOMLDocument to dict, unwanted
        for k, v in cls.__dict__.items():
            if not k.startswith('__'):
                data.setdefault(k, v)
        
        ret: T = TOMLConfig()
        ret.__toml__ = data  # TOMLDocument
        ret.__post_init__()
        return ret
    
    def dump(self, fout):
        old = self.__toml__
        blank = tomlkit.document()
        blank.update(old)
        tomlkit.dump(blank, fout)


class ConfigType(ABC):
    SERIALIZE: list[str]
    
    @classmethod
    def load(cls, data: dict[str, object], **extra):
        for k in cls.SERIALIZE:
            if k not in data:
                raise RuntimeError(f"Missing attribute {k!r}.")
        return cls(**data, **extra)
    
    def save(self) -> dict[str, object]:
        return {k: getattr(self, k) for k in self.SERIALIZE}
