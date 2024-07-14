
import sys, os.path
from pathlib import Path

from .core.ui import error


FROZEN = getattr(sys, "frozen", False)  # set by cx_Freeze

LOCAL_REPO = Path(__file__).absolute().parents[1]
IS_SITE_PKGS = LOCAL_REPO.parts[-1] == 'site_packages'


class __common__:
    LISTER_MAIN = 'net.micro.adb.Lister.Lister'


if FROZEN:
    raise NotImplementedError()

elif IS_SITE_PKGS:
    raise NotImplementedError()

else:  # development
    class Platform(__common__):
        PROJDIR = LOCAL_REPO.parent
        LISTER_JAR = PROJDIR / 'dex-lister/build/lister.jar'
        CONFIG = PROJDIR / 'config.toml'
        CACHE = PROJDIR / 'cache'


os.makedirs(Platform.CACHE, exist_ok=True)

if not Platform.LISTER_JAR.is_file():
    error("Missing lister jar.")
