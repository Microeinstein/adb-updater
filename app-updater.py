#!/usr/bin/env python3

import sys
import os
import re
import sqlite3
import asyncio

import aiohttp
import json_stream

from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from urllib.parse import urljoin
from typing import Optional

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


def get_adb_device():
    local_key = os.path.expanduser('~/.android/adbkey')
    
    if Path(local_key).exists():
        signer = sign_cryptography.CryptographySigner(local_key)
    else:
        print("No adb local key (todo)")
        return
    
    try:
        device = adb_commands.AdbCommands()
        device.ConnectDevice(rsa_keys=[signer])
    except usb_ex.DeviceNotFoundError as ex:
        print(ex.args[0])
        return
    
    return device


def chunk_read_lines(iter):
    sio = StringIO()
    for chunk in iter:
        sio.write(chunk)
        sio.seek(0)
        line2 = None
        for i, line in enumerate(sio):
            if i > 0:
                yield line2
            line2 = line
        sio = StringIO()
        sio.write(line2)
    sio.seek(0)
    yield from sio


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


async def main(arg0, *args):
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
        apps = list(AndroidApp.fetch_foreign_apps(dumpsys))
        apps = sorted(
            filter(lambda a: not a.system and a.installer, apps),
            key=lambda a: (a.installer, a.package)
        )
        for a in apps:
            print(f"  {a.package:<50} {a.version_code:<12} {a.system:<5} {a.installer}")


if __name__ == '__main__':
    sys.exit(asyncio.run(main(*sys.argv)) or 0)
