
import os, io

from pathlib import Path
from dataclasses import dataclass, field
from collections.abc import Generator
from contextlib import contextmanager, asynccontextmanager
from typing import ClassVar

import aiohttp, json_stream, simdjson

from ..core.io import open_or_create
from ..core.network import *
from ..core.misc import jobj, jlist
from ..core.context import SQLite
from ..core.config import ConfigType, TOMLConfig
from ..platform import Platform
from .apps import *
from .phone import AndroidPhone


class CacheInfo(TOMLConfig):
    etags: dict[str, str|None] = dict()


@dataclass
class FDroidRepo(ConfigType):
    SERIALIZE = ['name', 'address']
    JSON_INDEX_V1 = 'index-v1.json'
    JSON_ENTRY = 'entry.json'

    name: str
    address: str
    cache_path: Path|None = field(init=False, default=None)
    apps: dict[str, "FDroidApp"] = field(init=False, default_factory=dict)
    cache_info: ClassVar[CacheInfo]
    session: aiohttp.ClientSession|None = field(init=False, default=None)


    def __post_init__(self):
        base = Platform.CACHE_INDEX / url2path(self.address)
        
        fentry = base / self.JSON_ENTRY
        if not fentry.is_file():
            self.cache_path = base / self.JSON_INDEX_V1
            return
        
        for _dirpath, _dirnames, filenames in os.walk(base):
            for f in filenames:
                if f != self.JSON_ENTRY:
                    self.cache_path = base / f
                    return
            return


    @classmethod
    def read_from_backup(cls, path) -> Generator["FDroidRepo"]:
        with SQLite(path) as db:
            db.cursor.execute("SELECT name, address FROM CoreRepository")
            for row in db.cursor:
                name, addr = row
                name = json_stream.load(io.StringIO(name))
                name = name['en-US']
                yield cls(name, addr+'/')
    
    
    @classmethod
    @contextmanager
    def load_cache(cls):
        with open_or_create(Platform.CACHE_INFO, 'rt') as fin:
            cls.cache_info = CacheInfo.load(fin)
        yield
        with open(Platform.CACHE_INFO, 'wt') as fout:
            cls.cache_info.dump(fout)
    
    
    @asynccontextmanager
    async def connect(self):
        async with aiohttp.ClientSession() as session:
            self.session = session
            yield
            self.session = None


    async def update_repo(self):
        etags = self.cache_info.etags
        
        async def get(filename, **kw):
            assert self.session is not None
            src = rel_urljoin(self.address, filename)
            dest = Platform.CACHE_INDEX / url2path(src)
            pathout, etag = await try_get_url(
                self.session, src, dest, etags.get(src), **kw
            )
            if etag:
                etags[src] = etag
            return pathout
        
        async with self.connect():
            entry_path = await get(self.JSON_ENTRY)
            
            if not entry_path:
                self.cache_path = await get(self.JSON_INDEX_V1)
                return
            
            with open(entry_path, 'r') as fentry:
                jentry = json_stream.load(fentry)
                tstamp = int(jentry['timestamp']) // 1000
                i2name = jentry['index']['name']
                self.cache_path = await get(i2name, server_ts=tstamp)
                return


    def load_repo_apps(self, phone: AndroidPhone):
        if not self.cache_path or not self.cache_path.is_file():
            return
        
        parser = simdjson.Parser()
        json_like: jobj[...]
        
        if self.cache_path.match(self.JSON_INDEX_V1):
            # with open(self.cache_path, 'r') as fin:
            #     json_like = json_stream.load(fin, persistent=True)
            json_like = parser.load(self.cache_path)
            json_like = dict(  # unwrap first level to allow edits
                packages = json_like['packages'],
                apps     = json_like['apps'],
            )
            for pkg, iapp in phone.apps.items():
                app = FDroidApp.from_index_v1(self, pkg, json_like, phone, iapp)
                if app:
                    self.apps[pkg] = app
        
        else:  # v2
            # with open(self.cache_path, 'r') as fin:
            #     json_like = json_stream.load(fin, persistent=True)
            json_like = parser.load(self.cache_path)
            for pkg, iapp in phone.apps.items():
                app = FDroidApp.from_index_v2(self, pkg, json_like, phone, iapp)
                if app:
                    self.apps[pkg] = app
        
        print(f"  {self.name}... ok ({len(self.apps)})")
    
    
    async def download_app(self, app: "FDroidApp") -> Path|None:
        assert self.session is not None
        src = rel_urljoin(self.address, app.url)
        dest = Platform.CACHE_APPS / url2path(src)
        # do not redownload if existing, ignoring modified time and etag
        pathout, _etag = await try_get_url(self.session, src, dest, None, 1)
        return pathout


@dataclass
class FDroidApp(AndroidApp):
    repo: FDroidRepo
    url: str
    nativecode: list[str]
    min_sdk_ver: int
    local_path: Path|None = None
    
    
    @classmethod
    def from_index_v2(cls, repo: FDroidRepo, pkg: str, json_like: jobj[...], phone: AndroidPhone, iapp: InstalledApp) -> "FDroidApp|None":
        package: jobj[...] = json_like['packages'].get(pkg)
        if not package:
            return None
        
        last_compat: jobj[jobj[...]]
        for vers in package['versions'].values():
            last_compat = vers
            manifest    = last_compat['manifest']
            verinfo = dict(
                signer       = manifest['signer']['sha256'][0],
                version_code = manifest['versionCode'],
                min_sdk_ver  = manifest.get('usesSdk', {}).get('minSdkVersion', 1),
                nativecode   = list(manifest.get('nativecode', [])),
            )
            
            if iapp.is_compatible(**verinfo) and phone.is_compatible(**verinfo):
                break
        else:
            return None
        
        meta: jobj[jobj[...]] = package['metadata']
        
        return FDroidApp(
            package      = pkg,
            label        = meta['name']['en-US'],
            repo         = repo,
            version_name = manifest['versionName'],
            url          = last_compat['file']['name'],
            **verinfo
        )
    
    
    @classmethod
    def from_index_v1(cls, repo: FDroidRepo, pkg: str, json_like: jobj[...], phone: AndroidPhone, iapp: InstalledApp) -> "FDroidApp|None":
        package: jlist[jobj[...]] = json_like['packages'].get(pkg)
        if not package:
            return None
        
        last_compat: jobj[...]
        for vers in package:
            last_compat = vers
            verinfo = dict(
                version_code = last_compat['versionCode'],
                signer       = last_compat['signer'],
                min_sdk_ver  = last_compat.get('minSdkVersion', 1),
                nativecode   = list(last_compat.get('nativecode', [])),
            )
            
            if iapp.is_compatible(**verinfo) and phone.is_compatible(**verinfo):
                break
        else:
            return None
        
        apps = json_like['apps']
        # convert this shit, only the first time
        if isinstance(apps, list) or isinstance(apps, simdjson.Array):
            apps_list: list[jobj[...]] = apps
            apps: jobj[jobj[...]]
            apps = json_like['apps'] = {app['packageName']: app for app in apps_list}
            
        meta = apps[pkg]
        
        return FDroidApp(
            package      = pkg,
            label        = meta['localized']['en-US']['name'],
            repo         = repo,
            version_name = last_compat['versionName'],
            url          = '/' + last_compat['apkName'],
            **verinfo
        )
    
    
    async def download(self):
        self.local_path = await self.repo.download_app(self)
        return self
