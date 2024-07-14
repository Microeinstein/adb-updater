
import os, io, sqlite3

from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict

import aiohttp, json_stream, simdjson

from .core.network import *
from .core.config import ConfigType
from .apps import *


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
