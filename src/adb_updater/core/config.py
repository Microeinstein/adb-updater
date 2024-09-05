
from typing import TypeVar

import tomlkit
from tomlkit.toml_document import TOMLDocument
from .misc import AttrDict

T = TypeVar('T')


class TOMLConfig(AttrDict[TOMLDocument]):
    def __post_init__(self):
        ...
    
    @classmethod
    def load(cls, fin):
        data = tomlkit.load(fin)
        # update() will convert TOMLDocument to dict, unwanted
        
        v = cls.attach_proxy(data)
        v.set_class_defaults()
        v.__proxy__.__post_init__()
        return v
    
    def dump(self, fout):
        return tomlkit.dump(self.__wrapped__, fout)
