
from abc import ABC
from dataclasses import dataclass, field
from typing import List, Dict, Any

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
    def load(cls, fin) -> "TOMLConfig":
        data = tomlkit.load(fin)
        # update() will convert TOMLDocument to dict, unwanted
        for k, v in cls.__dict__.items():
            if not k.startswith('__'):
                data.setdefault(k, v)
        
        ret = TOMLConfig()
        ret.__toml__ = data  # TOMLDocument
        ret.__post_init__()
        return ret
    
    def dump(self, fout):
        old = self.__toml__
        blank = tomlkit.document()
        blank.update(old)
        tomlkit.dump(blank, fout)


class ConfigType(ABC):
    SERIALIZE: List[str]
    
    @classmethod
    def load(cls, data: Dict[str, Any], **extra):
        for k in cls.SERIALIZE:
            if k not in data:
                raise RuntimeError(f"Missing attribute {k!r}.")
        return cls(**data, **extra)
    
    def save(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.SERIALIZE}
