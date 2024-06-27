#!/usr/bin/env python3

import sys, os, io, re, sqlite3, zlib, tarfile, asyncio, atexit
import aiohttp, json_stream

from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin
from typing import List, Optional, Iterable, AnyStr

from adb import adb_commands, sign_cryptography
from adb import usb_exceptions as usb_ex


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
    
    def read(self, size=-1, /) -> io.IOBase:
        buffer = self.leftover
        cur = buffer.seek(0, io.SEEK_END)
        
        try:
            while (size < 0 or cur < size) and not self._read_limiter(buffer):
                cur += buffer.write(next(self.iter))
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
        self._line = buffer.readline()
    
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
        raise NotImplementedError()


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
        dec = zlib.decompressobj()
        while True:
            raw = dec.decompress(fileobj.read(1024 * 4 * 4))
            if not raw:
                break
            yield raw
    return RawIterStream(chunked())


# def chunk_read_lines(iter):
#     sio = io.StringIO()
#     for chunk in iter:
#         sio.write(chunk)
#         sio.seek(0)
#         line2 = None
#         for i, line in enumerate(sio):
#             if i > 0:
#                 yield line2
#             line2 = line
#         sio = io.StringIO()
#         sio.write(line2)
#     sio.seek(0)
#     yield from sio


@dataclass
class AndroidPhone:
    device: adb_commands.AdbCommands
    
    @classmethod
    def try_connect(cls):
        local_key = os.path.expanduser('~/.android/adbkey')
        
        if Path(local_key).exists():
            signer = sign_cryptography.CryptographySigner(local_key)
        else:
            print("No adb local key (todo)")
            return None
        
        try:
            device = adb_commands.AdbCommands()
            atexit.register(lambda: device.Close())
            device.ConnectDevice(rsa_keys=[signer])
        except usb_ex.DeviceNotFoundError as ex:
            print(ex.args[0])
            return None
        
        return cls(device)
        
    def get_package_backup(self, package: str):
        return self.device.BytesStreamingShell(f"bu backup -keyvalue {package}")
    
    @staticmethod
    def get_file_from_backup(bytes_iter, path: str) -> bytes:
        # dd if=fdroid.backup bs=24 skip=1 | zlib-flate -uncompress | tar -vxf -
        bkp = RawIterStream(bytes_iter)
        head = bkp.read(24)
        if not head.startswith(b'ANDROID BACKUP'):
            raise RuntimeError(f"Unknown backup format: {head!r}")
        bkp = ZlibDecompStream(bkp)
        bkp = tarfile.open(fileobj=bkp, mode='r|')
        print(bkp.list())
    
    def get_dumpsys_packages(self):
        return chunk_read_lines(self.device.StreamingShell('dumpsys package packages'))


@dataclass
class FDroidRepo:
    CACHE_DIR = './cache'
    JSON_INDEX_V1 = 'index-v1.json'
    JSON_ENTRY = 'entry.json'

    name: str
    address: str
    cache_path: Path = field(init=False)

    @classmethod
    def read_from_backup(cls):
        con = sqlite3.connect("apps/org.fdroid.fdroid/db/fdroid_db")
        cur = con.cursor()
        res = cur.execute("SELECT name, address FROM CoreRepository")
        while True:
            row = res.fetchone()
            if row is None:
                break
            name, addr = row
            name = json_stream.load(StringIO(name))
            name = name['en-US']
            yield cls(name, addr+'/')
        con.close()

    async def update_repo(self):
        async with aiohttp.ClientSession() as session:
            entry_path = await try_get_url(
                session, FDroidRepo.CACHE_DIR,
                urljoin(self.address, FDroidRepo.JSON_ENTRY)
            )
            
            if not entry_path:
                self.cache_path = await try_get_url(
                    session, FDroidRepo.CACHE_DIR,
                    urljoin(self.address, FDroidRepo.JSON_INDEX_V1)
                )
                return
            
            with open(entry_path, 'r') as fentry:
                jentry = json_stream.load(fentry)
                tstamp = int(jentry['timestamp']) / 1000
                i2name = jentry['index']['name']
                self.cache_path = await try_get_url(
                    session, FDroidRepo.CACHE_DIR,
                    urljoin(self.address, i2name), tstamp
                )
                return


@dataclass
class AndroidApp:
    RGX_ATTR = re.compile(r"^[ \t]+([a-z]+)=(.*)$", re.I)
    RGX_PKG  = re.compile(r"[^ ]+\{[^ ]+ ([^ ]+)\}.*$", re.I)
    RGX_VER  = re.compile(r"([^ ]+).*$", re.I)
    
    package: str
    version_code: str
    system: bool
    installer: Optional[str] = None
    
    @classmethod
    def fetch_foreign_apps(cls, text_iter):
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
    def print_apps_table(cls, apps):
        apps = sorted(
            filter(lambda a: not a.system and a.installer, apps),
            key=lambda a: (a.installer, a.package)
        )
        for a in apps:
            print(f"  {a.package:<50} {a.version_code:<12} {a.system:<5} {a.installer}")


async def main(arg0, *args):
    # phone = AndroidPhone.try_connect()
    # if not phone:
    #     print("No phone connected.")
    #     return 1
    
    # phone.get_package_backup('org.fdroid.fdroid')
    with open('fdroid.backup', 'rb') as fin:
        def chunked():
            while True:
                c = fin.read(4096)
                if not c:
                    break
                yield c
        
        AndroidPhone.get_file_from_backup(
            chunked(),
            'apps/org.fdroid.fdroid/db/fdroid_db'
        )
        return
    
    
    # repos = list(FDroidRepo.read_from_backup())
    
    # print("Repositories:")
    # for r in repos:
    #     print(f"  {r.name:<40s} {r.address}")
    
    # print()
    # print("Updating repos...")
    # tasks = [r.update_repo() for r in repos]
    # await asyncio.gather(*tasks)
    
    print()
    print("Getting packages...")
    # phone = get_adb_device()
    # if not phone:
    #     return 1
    # dumpsys = chunk_read_lines(phone.StreamingShell('dumpsys package packages'))
    with open('dumpsys.txt', 'r') as dumpsys:
        dumpsys = TextIterStream(dumpsys)
        apps = list(AndroidApp.fetch_foreign_apps(dumpsys))
        AndroidApp.print_apps_table(apps)


if __name__ == '__main__':
    sys.exit(asyncio.run(main(*sys.argv)) or 0)
