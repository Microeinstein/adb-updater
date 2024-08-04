
import sys, os.path, platform
from abc import ABC
from pathlib import Path

from .core.ui import error


LOCAL_REPO = Path(__file__).absolute().parents[1]  # directory containing modules
IS_SITE_PKGS = LOCAL_REPO.parts[-1] == 'site_packages'
IS_VENV = Path(sys.prefix).parts[-1] == 'venv'
SELF = Path(sys.argv[0]).absolute()  # or sys.executable, will ignore symlinks
SELF_DIR = SELF.parent

FROZEN = getattr(sys, "frozen", False)  # set by pyInstaller, cx_Freeze
SYSNAME = platform.system()


class _common(ABC):
    CONFIG_DIR: Path
    CACHE_DIR: Path
    LISTER_JAR: Path
    LISTER_MAIN = 'net.micro.adb.Lister.Lister'
    
    def __init__(self):
        self.CONFIG = self.CONFIG_DIR / 'config.toml'
        self.CACHE_INFO = self.CACHE_DIR / 'cache.toml'
        self.CACHE_INDEX = self.CACHE_DIR / 'index'
        self.CACHE_APPS = self.CACHE_DIR / 'apps'

        # print("[Platform]")
        # for k, v in self.__dict__.items():
        #     print(f"{k:>12s} : {v}")

        # make sure attributes are defined
        for _ in (self.LISTER_JAR,):
            pass
        
        os.makedirs(self.CONFIG_DIR, exist_ok=True)
        os.makedirs(self.CACHE_DIR, exist_ok=True)

        if not self.LISTER_JAR.is_file():
            error(f"Missing lister jar: '{self.LISTER_JAR}'")
            sys.exit(2)


if IS_VENV:  # development
    class _platform(_common):
        PROJDIR = LOCAL_REPO.parent
        CONFIG_DIR = PROJDIR / '.config'
        CACHE_DIR = PROJDIR / '.cache'
        LISTER_JAR = PROJDIR / 'dex-lister/build/lister.jar'

elif IS_SITE_PKGS:
    raise NotImplementedError()

elif SYSNAME == 'Linux':
    home_config = os.getenv("XDG_CONFIG_HOME", os.path.expandvars("${HOME}/.config"))
    home_cache = os.getenv("XDG_CACHE_HOME", os.path.expandvars("${HOME}/.cache"))
    class _platform(_common):
        CONFIG_DIR = Path(home_config) / 'app_updater'
        CACHE_DIR = Path(home_cache) / 'app_updater'

elif SYSNAME == 'Windows':  # portable
    # home_config = os.getenv("APPDATA", './config')
    # home_cache = os.getenv("TEMP", './cache')
    class _platform(_common):
        CONFIG_DIR = Path('.') / 'config'
        CACHE_DIR = Path('.') / 'cache'

else:
    raise NotImplementedError()


if FROZEN:
    _platform.LISTER_JAR = LOCAL_REPO / 'lister.jar'


Platform = _platform()
