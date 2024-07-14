
import os, re
from pathlib import Path
from urllib.parse import urljoin
from typing import AnyStr

from aiohttp import ClientSession

__all__ = 'url2path  rel_urljoin  try_get_url'.split()


RGX_URL = re.compile(r"^[^:/]+://([^?#]+)([?#].*)?$")

def url2path(url: str) -> Path:
    m = RGX_URL.match(url)
    if not m:
        raise RuntimeError(f"Unknown url: {url!r}")
    return Path(m[1])


def rel_urljoin(base: AnyStr, url: AnyStr, **kw) -> AnyStr:
    return urljoin(base + '/', './' + url, **kw)


async def try_get_url(session: ClientSession, dir, url, new_ts: int = None):
    fpath = dir / url2path(url)
    print('  ', fpath, sep='')
    
    old_ts = fpath.stat().st_mtime if fpath.exists() else 0
    if new_ts and old_ts >= new_ts:
        return fpath
    
    headers = {
        'If-Modified-Since': old_ts,
        'If-None-Match': ...,
    }
    async with session.get(url, headers=headers) as response:
        if not response.ok:  # < 400
            return None
        
        if response.status == 304:
            return fpath
        
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
