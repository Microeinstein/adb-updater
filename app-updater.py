#!/usr/bin/env python3

import sys, os, io, re, sqlite3, zlib, tarfile, asyncio

from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin
from inspect import getmro
from typing import List, Dict, Tuple, Optional, Iterable, Callable, AnyStr, Any

import aiohttp, json_stream, simdjson, tomlkit
import tableprint as tp
import readchar as rc

from adb import adb_commands, sign_cryptography
from adb import usb_exceptions as usb_ex

# NOTE: adb_commands.AdbCommands.BytesStreamingShell requires a byte-format command


SELFDIR = Path(os.path.dirname(os.path.realpath(__file__)))
LISTER_JAR = Path(SELFDIR) / 'dex-lister/build/lister.jar'
LISTER_MAIN = 'net.micro.adb.Lister.Lister'


######## UTILS ########

def middle_ellipsis(txt: str, maxwidth: int):
    l = len(txt)
    if l <= maxwidth:
        return txt
    l1 = (maxwidth - 1) // 2
    l2 = maxwidth // 2
    l1 += maxwidth - (l1 + 1 + l2)
    return f"{txt[:l1]}…{txt[l-l2:]}"

def title(*values, **kw):
    values = (kw.get('sep', ' ')).join(values)
    kw['sep'] = ''
    kw['file'] = sys.stderr
    print('\n\x1b[1m', values, '\x1b[0m', **kw)

def error(*values, **kw):
    values = (kw.get('sep', ' ')).join(values)
    kw['sep'] = ''
    kw['file'] = sys.stderr
    print('\x1b[30m', values, '\x1b[0m', **kw)

def ask_yes_no(prompt, default=False):
    print(prompt, ' ', '[Y/n]' if default else '[y/N]', ': ', sep='', end='')
    try:
        while True:
            k = rc.readkey()
            if k == rc.key.ENTER:
                return default
            if k == 'y':
                return True
            if k in ('n', rc.key.ESC):
                return False
    except KeyboardInterrupt:
        return False


RGX_URL = re.compile(r"^[^:/]+://([^?#]+)([?#].*)?$")

def url2path(url: str) -> Path:
    m = RGX_URL.match(url)
    if not m:
        raise RuntimeError(f"Unknown url: {url!r}")
    return Path(m[1])


def rel_urljoin(base: AnyStr, url: AnyStr, **kw) -> AnyStr:
    return urljoin(base + '/', './' + url, **kw)


async def try_get_url(session, dir, url, new_ts: int = None):
    fpath = dir / url2path(url)
    print('  ', fpath, sep='')
    
    if new_ts and fpath.exists() and fpath.stat().st_mtime <= new_ts:
        return fpath
    
    async with session.get(url) as response:
        if not response.ok:
            return None
        
        # if "content-disposition" in response.headers:
        #     header = response.headers["content-disposition"]
        #     filename = header.split("filename=")[1]
        # else:
        #     filename = res.split("/")[-1]
        
        os.makedirs(fpath.parent, exist_ok=True)
        with open(fpath, mode="wb") as file:
            while True:
                chunk = await response.content.read()
                if not chunk:
                    break
                file.write(chunk)
        return fpath


######## STREAMS ########

@dataclass
class IterStream(ABC):
    iter: Iterable
    leftover: io.IOBase = field(init=False)
    
    def __post_init__(self):
        self.iter = iter(self.iter)
        self.leftover = self.__annotations__['leftover']()
    
    def seekable(self): return False
    def readable(self): return True
    def writable(self): return False
    
    def _seek_to_cut(self, buffer, size):
        ...
    
    def _read_limiter(self, buffer):
        return False
    
    def close(self):
        flush_stream(self)
        super().close()
    
    def read(self, size=-1, /) -> io.IOBase:
        buffer = self.leftover
        cur = buffer.seek(0, io.SEEK_END)
        
        try:
            while (size < 0 or cur < size) and not self._read_limiter(buffer):
                data = next(self.iter)
                cur += buffer.write(data)
        except StopIteration:
            pass
        
        buffer.seek(0)
        self._seek_to_cut(buffer, size)
        cur = buffer.tell()
        
        extra = self.leftover.__class__()
        extra.write(buffer.read())
        self.leftover = extra
        
        buffer.seek(cur)
        buffer.truncate()
        return buffer


class TextIterStream(IterStream, io.TextIOBase):
    leftover: io.StringIO
    _line: str
    
    def _seek_to_cut(self, buffer, size):
        self._line = buffer.readline(size)
    
    def _read_limiter(self, buffer):
        return buffer.tell() > 0
    
    def readlines(self, hint=-1, /) -> List[str]:
        lines = []
        while hint != 0:
            line = self.readline()
            if not line:
                break
            if hint >= 0:
                hint -= 1
            lines.append(line)
        return lines
    
    def readline(self, size=-1, /) -> str:
        super().read(size)
        return self._line
    
    def read(self, size=-1, /) -> str:
        return super().read(size).getvalue()


class RawIterStream(IterStream, io.RawIOBase):
    leftover: io.BytesIO
    
    def _seek_to_cut(self, buffer, size):
        if size >= 0:
            buffer.seek(size)
    
    def readall(self) -> bytes:
        return self.read()
    
    def read(self, size=-1, /) -> bytes:
        return super().read(size).getvalue()


def ZlibDecompStream(fileobj: io.RawIOBase):
    def chunked():
        dec = zlib.decompressobj(wbits=15)
        while True:
            raw = dec.decompress(fileobj.read(1024 * 4 * 4))
            if not raw:
                break
            yield raw
    return RawIterStream(chunked())


def GzipDecompStream(fileobj: io.RawIOBase):
    def chunked():
        dec = zlib.decompressobj(wbits=47)
        while True:
            raw = dec.decompress(fileobj.read(1024 * 4 * 4))
            if not raw:
                break
            yield raw
    return RawIterStream(chunked())


def chunked_stream(stream: io.RawIOBase, chunksize=1024 * 4 * 4) -> bytes:
    while True:
        c = stream.read(chunksize)
        if not c:
            break
        yield c


def flush_stream(stream: io.IOBase):
    if isinstance(stream, io.RawIOBase):
        stream: io.RawIOBase
        while stream.read(4096):
            pass
    else:
        while stream.readline():
            pass


######## PROGRAM ########

def optional_decor_args(orig):
    def wrapper(func = None, /, *a, **kwargs):
        if func and callable(func) and not a and not kwargs:
            # not effective with only one positional callable
            return orig(func, *a, **kwargs)
        return lambda func: orig(func, *a, **kwargs)
    
    return wrapper


@optional_decor_args
def a_autoexit(func):
    async def wrapper(self, *a, **kw):
        try:
            ret = await func(self, *a, **kw)
        finally:
            for ak, av in self.__dict__.copy().items():  # no descriptors
                if hasattr(av, '__exit__'):
                    av.__exit__(None, None, None)
                    delattr(self, ak)
        return ret
    
    return wrapper
    

@dataclass
class PropMessage:
    msg: str
    default: Any = field(default=None)

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


@dataclass
class ContextProp:
    factory: Callable = field(default=None)

    def __set_name__(self, owner, name):
        self.pub = name
        self.priv = '_' + name

    def __get__(self, obj, objtype=None):
        if not self.factory:
            self.factory = obj.__annotations__[self.pub]
        value = getattr(obj, self.priv, None)
        if not value:
            value = self.factory().__enter__()
            setattr(obj, self.priv, value)
        return value

    def __set__(self, obj, value):
        self.__delete__(obj)
        setattr(obj, self.priv, value)
    
    def __delete__(self, obj):
        old = getattr(obj, self.priv, None)
        if not old:
            return
        old.__exit__(None, None, None)
        delattr(obj, self.priv)


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


class AndroidPhone:
    TMP = '/data/local/tmp'
    
    device: adb_commands.AdbCommands = PropMessage("Phone is not connected.")  


    def __enter__(self):
        title("Connecting to phone...")
        local_key = os.path.expanduser('~/.android/adbkey')
        
        if Path(local_key).exists():
            signer = sign_cryptography.CryptographySigner(local_key)
        else:
            print("No adb local key (todo)")
            return None
        
        try:
            device = adb_commands.AdbCommands()
            device.ConnectDevice(rsa_keys=[signer])
        except usb_ex.DeviceNotFoundError as ex:
            print(ex.args[0])
            return None
        
        self.device = device
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        title("Disconnecting from phone...")
        self.device.Close()
        self.device = None
        # suppress error -> return True
    
    
    def get_dumpsys_packages(self) -> io.IOBase:
        text_iter = self.device.StreamingShell('dumpsys package packages')
        return TextIterStream(text_iter)
    
    def get_package_list(self):
        lister_fn = os.path.basename(LISTER_JAR)
        dest = f"{AndroidPhone.TMP}/{lister_fn}"
        
        self.device.Push(str(LISTER_JAR), dest, timeout_ms=30000)
        
        raw_iter = self.device.BytesStreamingShell(f"""
            export CLASSPATH={dest!r};
            app_process / {LISTER_MAIN!r} | gzip;
        """.encode())
        
        raw = RawIterStream(raw_iter)
        gz = GzipDecompStream(raw)
        js = json_stream.load(gz)
        for japp in js:
            yield json_stream.to_standard_types(japp)
        
    def get_package_backup(self, package: str) -> io.RawIOBase:
        bytes_iter = self.device.BytesStreamingShell(f"bu backup -keyvalue {package}".encode())
        return RawIterStream(bytes_iter)
    
    @staticmethod
    def get_file_from_backup(bkp: io.RawIOBase, path: str) -> tarfile.ExFileObject:
        # dd if=fdroid.backup bs=24 skip=1 | zlib-flate -uncompress | tar -vxf -
        head = bkp.read(24)
        if not head.startswith(b'ANDROID BACKUP'):
            raise RuntimeError(f"Unknown backup format: {head!r}")
        bkp = ZlibDecompStream(bkp)
        bkp = tarfile.open(fileobj=bkp, mode='r|')
        # NOTE: in streaming mode you must iterate members this way,
        # otherwise tar needs to seek backwards
        for member in bkp:
            if member.path == path:
                return bkp.extractfile(member)


@dataclass
class AndroidApp:
    PKG_INSTALLER = 'com.google.android.packageinstaller'
    FDROID_APP    = 'org.fdroid.fdroid'
    FOXYDROID_APP = 'nya.kitsunyan.foxydroid'
    FFUPDATER_APP = 'de.marmaro.krt.ffupdater'
    ISLAND_SBOX   = 'com.oasisfeng.island.fdroid'
    PLAY_STORE    = 'com.android.vending'
    AMAZON_STORE  = 'com.amazon.venezia'
    HUAWEI_STORE  = 'com.huawei.appmarket'
    AURORA_STORE  = 'com.aurora.store'
    
    OPEN_STORES   = [
        PKG_INSTALLER,
        FDROID_APP,
        FOXYDROID_APP,
        FFUPDATER_APP
    ]
    
    package: str
    label: str
    version_code: str
    version_name: str
    
    @classmethod
    def get_installer_name(cls, pkg: str) -> str:
        for c in getmro(cls):
            for k, v in c.__dict__.items():
                if v == pkg:
                    return k.replace('_', ' ').title()


@dataclass
class InstalledApp(AndroidApp):
    RGX_ATTR = re.compile(r"^[ \t]+([a-z]+)=(.*)$", re.I)
    RGX_PKG  = re.compile(r"[^ ]+\{[^ ]+ ([^ ]+)\}.*$", re.I)
    RGX_VER  = re.compile(r"([^ ]+).*$", re.I)
    
    system: bool
    removed: bool
    installer: Optional[str] = None
    
    @classmethod
    def _fetch_foreign_apps(cls, text_iter):
        raise RuntimeError("deprecated")
        data = dict()
        ignore = False
        
        for line in text_iter:
            line = line.lower()
            m = cls.RGX_ATTR.match(line)
            if not m:
                continue
            
            key, val = m.groups()
            if key == 'pkg':
                if data:
                    if not ignore:
                        yield cls(**data)
                    data = dict()
                ignore = val == 'null'
                data['package'] = cls.RGX_PKG.match(val)[1] if not ignore else val
            
            elif key == 'versioncode':
                data['version_code'] = cls.RGX_VER.match(val)[1]
            
            elif key == 'flags':
                data['system'] = 'SYSTEM' in val
            
            elif key == 'installerpackagename':
                data['installer'] = val
        
        if data and not ignore:
            yield cls(**data)
    
    @classmethod
    def from_lister(cls, japp: Dict) -> "InstalledApp":
        return InstalledApp(
            package      = japp['pkg'],
            label        = japp['label'],
            version_code = japp['vcode'],
            version_name = japp['vname'],
            system       = japp['system'],
            removed      = japp['removed'],
            installer    = japp['installer'],
        )
        
    @classmethod
    def print_apps_table(cls, apps: List["InstalledApp"]):
        apps = sorted(apps, key=lambda a: (a.installer, a.label))
        rows = []
        for a in apps:
            a: "InstalledApp"
            rows.append((
                middle_ellipsis(a.label, 18),
                middle_ellipsis(a.version_name or '?', 18),
                middle_ellipsis(cls.get_installer_name(a.installer), 18),
            ))
        tp.table(rows, 'Label Version Installer'.split())


@dataclass
class FDroidApp(AndroidApp):
    repo: "FDroidRepo"
    url: str
    
    @classmethod
    def from_index_v2(cls, repo: "FDroidRepo", pkg: str, json_like: Dict) -> Optional["FDroidApp"]:
        package = json_like['packages'].get(pkg)
        if not package:
            return None
        
        meta = package['metadata']
        last_ver = list(package['versions'].items())[0][1]
        
        return FDroidApp(
            package      = pkg,
            label        = meta['name']['en-US'],
            repo         = repo,
            version_code = last_ver['manifest']['versionCode'],
            version_name = last_ver['manifest']['versionName'],
            url          = last_ver['file']['name'],
        )
    
    @classmethod
    def from_index_v1(cls, repo: "FDroidRepo", pkg: str, json_like: Dict) -> Optional["FDroidApp"]:
        package = json_like['packages'].get(pkg)
        if not package:
            return None
        last_ver = package[0]
        
        apps = json_like['apps']
        if not isinstance(apps, dict):
            # convert this shit, only the first time
            apps = json_like['apps'] = {app['packageName']: v for app in apps}
            
        meta = apps[pkg]
        
        return FDroidApp(
            package      = pkg,
            label        = meta['localized']['en-US']['name'],
            repo         = repo,
            version_code = last_ver['versionCode'],
            version_name = last_ver['versionName'],
            url          = '/' + last_ver['apkName'],
        )


@dataclass
class FDroidRepo(ConfigType):
    SERIALIZE = ['name', 'address']
    JSON_INDEX_V1 = 'index-v1.json'
    JSON_ENTRY = 'entry.json'

    base_dir: Path
    name: str
    address: str
    cache_path: Path = field(init=False, default=None)
    apps: Dict[str, AndroidApp] = field(init=False, default_factory=dict)
    
    def __post_init__(self):
        base = self.base_dir / url2path(self.address)
        
        fentry = base / self.JSON_ENTRY
        if not fentry.is_file():
            self.cache_path = base / self.JSON_INDEX_V1
            return
        
        for dirpath, dirnames, filenames in os.walk(base):
            for f in filenames:
                if f != self.JSON_ENTRY:
                    self.cache_path = base / f
                    return
            return

    @classmethod
    def read_from_backup(cls, path, base_dir) -> "FDroidRepo":
        con = sqlite3.connect(path)
        cur = con.cursor()
        res = cur.execute("SELECT name, address FROM CoreRepository")
        while True:
            row = res.fetchone()
            if row is None:
                break
            name, addr = row
            name = json_stream.load(io.StringIO(name))
            name = name['en-US']
            yield cls(base_dir, name, addr+'/')
        con.close()

    async def update_repo(self):
        async with aiohttp.ClientSession() as session:
            entry_path = await try_get_url(
                session, self.base_dir,
                rel_urljoin(self.address, self.JSON_ENTRY)
            )
            
            if not entry_path:
                self.cache_path = await try_get_url(
                    session, self.base_dir,
                    rel_urljoin(self.address, self.JSON_INDEX_V1)
                )
                return
            
            with open(entry_path, 'r') as fentry:
                jentry = json_stream.load(fentry)
                tstamp = int(jentry['timestamp']) / 1000
                i2name = jentry['index']['name']
                self.cache_path = await try_get_url(
                    session, self.base_dir,
                    rel_urljoin(self.address, i2name), tstamp
                )
                return
    
    def load_repo_apps(self, pkgs: List[str]):
        if not self.cache_path or not self.cache_path.is_file():
            return
        
        parser = simdjson.Parser()
        
        if self.cache_path.match(self.JSON_INDEX_V1):
            # with open(self.cache_path, 'r') as fin:
            #     json_like = json_stream.load(fin, persistent=True)
            json_like = parser.load(self.cache_path)
            for p in pkgs:
                app = FDroidApp.from_index_v1(self, p, json_like)
                if app:
                    self.apps[p] = app
        
        else:  # v2
            # with open(self.cache_path, 'r') as fin:
            #     json_like = json_stream.load(fin, persistent=True)
            json_like = parser.load(self.cache_path)
            for p in pkgs:
                app = FDroidApp.from_index_v2(self, p, json_like)
                if app:
                    self.apps[p] = app
        
        print(f"  {self.name}... ok ({len(self.apps)})")


class UpdaterConfig(TOMLConfig):
    hmm: str = "seriously"
    repos: List[FDroidRepo]


class Updater:
    CACHE = Path('cache')
    CONFIG = Path('config.toml')
    FDROID_BKP_DB = f'apps/{AndroidApp.FDROID_APP}/db/fdroid_db'
    FDROID_DB = CACHE / Path(os.path.basename(FDROID_BKP_DB))
    
    phone: AndroidPhone = ContextProp()
    repos: List[FDroidRepo]
    apps: Dict[str, InstalledApp]  # foreign
    updates: Dict[str, Tuple[InstalledApp, FDroidApp]]
    missing: Dict[str, InstalledApp]


    def repos_from_backup(self):
        if not self.FDROID_DB.is_file():
            print("Getting FDroid database from phone... (requires manual confirm)")
            
            with self.phone.get_package_backup(AndroidApp.FDROID_APP) as bkp, \
                 open(self.FDROID_DB, 'wb') as fout:
                
                db_data = AndroidPhone.get_file_from_backup(bkp, self.FDROID_BKP_DB)
                for chunk in chunked_stream(db_data):
                    fout.write(chunk)
    
        return FDroidRepo.read_from_backup(self.FDROID_DB, self.CACHE)


    def load_config(self, fconf: io.IOBase = None):
        if not fconf:
            with open(self.CONFIG, 'a+t') as fconf:
                fconf.seek(0)
                return self.load_config(fconf)
        
        title("Loading config...")
        
        config = UpdaterConfig.load(fconf)
        
        repos = config.repos
        if not repos:
            repos = self.repos_from_backup()
        else:
            repos = (FDroidRepo.load(r, base_dir=self.CACHE) for r in repos)
        self.repos = list(repos)
        
        # prepare for save
        config.repos = list(r.save() for r in self.repos)
        
        # save changes
        # fconf.seek(0)
        # config.dump(fconf)
        # fconf.truncate()
        
        title("Repositories:")
        for r in self.repos:
            print(f"  {r.name:<40s} {r.address}")
    
    
    def load_apps(self):
        title("Getting packages...")
        self.apps = {}
        
        # with self.phone.get_dumpsys_packages() as dump:
        #     dumpsys = TextIterStream(dumpsys)
        #     for app in InstalledApp._fetch_foreign_apps(dumpsys):
        #         self.apps[app.package] = app
        
        n_total = 0
        n_system = 0
        n_removed = 0
        n_foreign = 0
        
        print('\x1b7Awaiting response from device...')
        for japp in self.phone.get_package_list():
            app = InstalledApp.from_lister(japp)
            n_total += 1
            n_system += int(app.system)
            n_removed += int(app.removed)
            if not app.system and app.installer in AndroidApp.OPEN_STORES:
                n_foreign += 1
                self.apps[app.package] = app
            
            print(f'\x1b8\x1b[0J', end='')
            for k, v in (
                ('total', n_total),
                ('system', n_system),
                ('removed', n_removed),
                ('closed', n_total - n_system - n_foreign),
                ('foreign', n_foreign),
            ):
                print(f"  {k:<8} : {v}")
        
        # InstalledApp.print_apps_table(self.apps.values())
    
    
    async def update_repos(self):
        title("Updating repos...")
        tasks = [r.update_repo() for r in self.repos]
        await asyncio.gather(*tasks)
    
    
    async def check_updates(self):
        title("Loading repos apps...")
        
        pkgs = self.apps.keys()
        async def upd(r):
            r.load_repo_apps(pkgs)
        await asyncio.gather(*[upd(r) for r in self.repos])
        
        title("Checking updates...")
        self.updates = {}
        self.missing = {}
        
        for pkg, app in self.apps.items():
            app: InstalledApp
            found = False
            
            for r in self.repos:
                r: FDroidRepo
                latest: FDroidApp = r.apps.get(pkg)
                if latest:
                    found = True
                    if latest.version_code > app.version_code:
                        self.updates[pkg] = (app, latest)
                        break
            
            if not found:  # in any repo
                self.missing[pkg] = app
        
        print("Not found in any repo:")
        InstalledApp.print_apps_table(self.missing.values())
    
    
    def ask_updates(self):
        if not self.updates:
            if not self.missing:
                title(f"Up to date.")
            else:
                title(f"Up to date, {len(self.missing)} missing.")
            return False
        
        title(f"{len(self.updates)} updates are available:")
        
        upds = dict(sorted(
            self.updates.items(),
            key=lambda i: (i[1][0].installer, i[1][1].label)
        ))
        rows = []
        for pkg, (inst, upd) in upds.items():
            rows.append((
                middle_ellipsis(inst.label, 18),
                middle_ellipsis(inst.version_name or '?', 18),
                '->',
                middle_ellipsis(upd.version_name or '!?', 18)
            ))
        tp.table(rows, 'Label From -> To'.split())
        
        return ask_yes_no("Do you want to update?")

    
    @a_autoexit
    async def main(self, arg0, *args) -> int:
        os.makedirs(self.CACHE, exist_ok=True)
        
        if not LISTER_JAR.is_file():
            error("Missing lister jar.")
            return 1
        
        self.load_config()
        await self.update_repos()
        self.load_apps()
        await self.check_updates()
        if not self.ask_updates():
            return
        title("Downloading...")


if __name__ == '__main__':
    err = asyncio.run(Updater().main(*sys.argv)) or 0
    sys.exit(err)
