
import sys, os.path, platform, socket, getpass
from abc import ABC
from pathlib import Path

from . import version
from .core.ui import error


# maybe the most portable ways to get these two variables...
_sck_hostname = socket.gethostname()
if '.' in _sck_hostname:
    HOSTNAME = _sck_hostname
else:
    HOSTNAME = socket.gethostbyaddr(_sck_hostname)[0]

USERNAME = getpass.getuser()


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
        CONFIG_DIR = Path(home_config).absolute() / version.NAME
        CACHE_DIR = Path(home_cache).absolute() / version.NAME


elif SYSNAME == 'Windows':  # portable
    # home_config = os.getenv("APPDATA", './config')
    # home_cache = os.getenv("TEMP", './cache')
    
    workdir = Path('.').absolute()
    class _platform(_common):
        CONFIG_DIR = workdir / 'config'
        CACHE_DIR = workdir / 'cache'

else:
    raise NotImplementedError()


if FROZEN:
    _platform.LISTER_JAR = LOCAL_REPO / 'lister.jar'


Platform = _platform()


# certificates
# https://serverfault.com/a/722646
# https://docs.openssl.org/master/man7/openssl-env/#description
def unix_find_cert():
    cert_dir = os.getenv("SSL_CERT_DIR", "")
    cert_file = os.getenv("SSL_CERT_FILE", "")
    if cert_dir or cert_file:
        return
    
    try:
        import certifi
        embedded = certifi.where()
        os.environ['SSL_CERT_FILE'] = os.environ['REQUESTS_CA_BUNDLE'] = embedded
        return
    except ImportError:
        ...

    known_files = [
        "/etc/ssl/certs/ca-certificates.crt",                 # Debian/Ubuntu/Gentoo etc.
        "/etc/pki/tls/certs/ca-bundle.crt",                   # Fedora/RHEL 6
        "/etc/ssl/ca-bundle.pem",                             # OpenSUSE
        "/etc/pki/tls/cacert.pem",                            # OpenELEC
        "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",  # CentOS/RHEL 7
        "/etc/ssl/cert.pem",                                  # Alpine Linux
    ]
    for f in known_files:
        if os.path.isfile(f):
            os.environ['SSL_CERT_FILE'] = f
            return
    
    known_dirs = [
        "/etc/ssl/certs",                # SLES10/SLES11, https://golang.org/issue/12139
        "/system/etc/security/cacerts",  # Android
        "/usr/local/share/certs",        # FreeBSD
        "/etc/pki/tls/certs",            # Fedora/RHEL
        "/etc/openssl/certs",            # NetBSD
        "/var/ssl/certs",                # AIX
    ]
    for d in known_dirs:
        if os.path.isdir(d):
            os.environ['SSL_CERT_DIR'] = d
            return
    
    raise RuntimeError("No root certificates found!")
    
if SYSNAME != 'Windows':
    unix_find_cert()
