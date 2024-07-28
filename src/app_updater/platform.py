
import sys, os.path
from abc import ABC
from pathlib import Path

from .core.ui import error


FROZEN = getattr(sys, "frozen", False)  # set by cx_Freeze

LOCAL_REPO = Path(__file__).absolute().parents[1]
IS_SITE_PKGS = LOCAL_REPO.parts[-1] == 'site_packages'


class __common__(ABC):
    PROJDIR: Path
    LISTER_JAR: Path
    LISTER_MAIN = 'net.micro.adb.Lister.Lister'
    
    def __init__(self):
        self.CONFIG = self.PROJDIR / 'config.toml'
        self.CACHE = self.PROJDIR / 'cache'
        self.CACHE_INFO = self.CACHE / 'cache.toml'
        # try to access other variables
        for _ in (self.LISTER_JAR,):
            pass


if FROZEN:
    raise NotImplementedError()

elif IS_SITE_PKGS:
    raise NotImplementedError()

else:  # development
    class __platform__(__common__):
        PROJDIR = LOCAL_REPO.parent
        LISTER_JAR = PROJDIR / 'dex-lister/build/lister.jar'


Platform = __platform__()

os.makedirs(Platform.CACHE, exist_ok=True)

if not Platform.LISTER_JAR.is_file():
    error("Missing lister jar.")
