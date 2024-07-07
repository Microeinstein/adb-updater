#!/usr/bin/env python3

import sys, os, io, re, sqlite3, zlib, tarfile, asyncio
import aiohttp, json_stream

from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin
from typing import List, Dict, Optional, Iterable, AnyStr, Any

import tomlkit

from adb import adb_commands, sign_cryptography
from adb import usb_exceptions as usb_ex

# NOTE: adb_commands.AdbCommands.BytesStreamingShell requires a byte-format command


SELFDIR = Path(os.path.dirname(os.path.realpath(__file__)))
LISTER_JAR = Path(SELFDIR) / 'dex-lister/build/lister.jar'
LISTER_MAIN = 'net.micro.adb.Lister.Lister'


######## UTILS ########

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


RGX_URL = re.compile(r"^[^:/]+://([^?#]+)([?#].*)?$")

def url2path(url: str) -> Path:
    m = RGX_URL.match(url)
    if not m:
        raise RuntimeError(f"Unknown url: {url!r}")
    return Path(m[1])


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
        tomlkit.dump(self.__toml__, fout)


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
    def print_apps_table(cls, apps):
        apps = sorted(
            filter(lambda a: not a.system and a.installer, apps),
            key=lambda a: (a.installer, a.package)
        )
        for a in apps:
            a: InstalledApp
            print(f"  {a.label:<50} {a.version_name or '--':<12} {a.system:<5} {a.installer}")


@dataclass
class FDroidApp(AndroidApp):
    repo: "FDroidRepo"
    url: str
    
    @classmethod
    def from_index_v2(cls, repo: "FDroidRepo", pkg: str, json_like: Dict) -> "FDroidApp":
        package = json_like['packages'][pkg]
        meta = package['metadata']
        last_ver = list(package['versions'].values())[0]
        
        return FDroidApp(
            package      = pkg,
            label        = meta['name']['en-US'],
            repo         = repo,
            version_code = last_ver['manifest']['versionCode'],
            version_name = last_ver['manifest']['versionName'],
            url          = last_ver['file']['name'],
        )
    
    @classmethod
    def from_index_v1(cls, repo: "FDroidRepo", pkg: str, json_like: Dict) -> "FDroidApp":
        apps = json_like['apps']
        if not isinstance(apps, dict):
            # convert this shit, only the first time
            apps = json_like['apps'] = {app['packageName']: v for app in apps}
            
        app = apps[pkg]
        last_ver = json_like['packages'][pkg][0]
        
        return FDroidApp(
            package      = pkg,
            label        = app['localized']['en-US']['name'],
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
    cache_path: Path = field(init=False)
    apps: Dict[str, AndroidApp] = field(init=False)

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
                urljoin(self.address, self.JSON_ENTRY)
            )
            
            if not entry_path:
                self.cache_path = await try_get_url(
                    session, self.base_dir,
                    urljoin(self.address, self.JSON_INDEX_V1)
                )
                return
            
            with open(entry_path, 'r') as fentry:
                jentry = json_stream.load(fentry)
                tstamp = int(jentry['timestamp']) / 1000
                i2name = jentry['index']['name']
                self.cache_path = await try_get_url(
                    session, self.base_dir,
                    urljoin(self.address, i2name), tstamp
                )
                return
    
    def load_repo_apps(self, pkgs: List[str]):
        if not self.cache_path:
            return
        
        if self.cache_path.match(self.JSON_INDEX_V1):
            with open(self.cache_path, 'r') as fin_apps, \
                 open(self.cache_path, 'r') as fin_pkgs:
                
                json_like = dict(
                    apps     = json_stream.load(fin_apps)['apps'].persistent(),
                    packages = json_stream.load(fin_pkgs)['packages'].persistent(),
                )
                
                for p in pkgs:
                    yield FDroidApp.from_index_v1(self, p, json_like)
        
        else:  # v2
            with open(self.cache_path, 'r') as fin_pkgs:
                
                json_like = dict(
                    packages = json_stream.load(fin_pkgs)['packages'].persistent(),
                )
                
                for p in pkgs:
                    yield FDroidApp.from_index_v2(self, p, json_like)


class UpdaterConfig(TOMLConfig):
    repos: List[FDroidRepo]


class Updater:
    CACHE = Path('cache')
    CONFIG = Path('config.toml')
    FDROID_BKP_DB = f'apps/{AndroidApp.FDROID_APP}/db/fdroid_db'
    FDROID_DB = CACHE / Path(os.path.basename(FDROID_BKP_DB))
    
    phone: AndroidPhone
    repos: List[FDroidRepo]
    apps: Dict[str, InstalledApp]


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
        fconf.seek(0)
        config.dump(fconf)
        fconf.truncate()
        
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
                print(f"{k:<8} : {v}")
        
        InstalledApp.print_apps_table(self.apps.values())
    
    
    async def update_repos(self):
        title("Updating repos...")
        tasks = [r.update_repo() for r in repos]
        await asyncio.gather(*tasks)
    
    
    async def main(self, arg0, *args, _loaded = None):
        if not _loaded:
            os.makedirs(self.CACHE, exist_ok=True)
            
            if not LISTER_JAR.is_file():
                error("Missing lister jar.")
                return 1
            
            title("Connecting to phone...")
            with AndroidPhone() as self.phone:
                return await self.main(arg0, *args, _loaded=True)
        
        self.load_config()
        self.load_apps()
        return
        await self.update_repos()
    
        title("Checking...")
        tasks = [r.update_repo() for r in repos]
        await asyncio.gather(*tasks)


if __name__ == '__main__':
    err = asyncio.run(Updater().main(*sys.argv)) or 0
    sys.exit(err)
