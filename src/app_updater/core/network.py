
import os, re
import datetime as dt
from pathlib import Path
from urllib.parse import urljoin
from email.utils import format_datetime

from aiohttp import ClientSession

from .io import CHUNKSIZE


RGX_URL = re.compile(r"^[^:/]+://([^?#]+)([?#].*)?$")

def url2path(url: str) -> Path:
    m = RGX_URL.match(url)
    if not m:
        raise RuntimeError(f"Unknown url: {url!r}")
    return Path(m[1])


def rel_urljoin(base: str, url: str, **kw) -> str:
    return urljoin(base + '/', './' + url, **kw)


async def try_get_url(
    session: ClientSession,
    url: str,
    dest: Path,
    etag: str|None = None,
    server_ts: int|None = None
) -> tuple[Path|None, str|None]:
    # print('  ', url, sep='')
    
    cur_ts = dest.stat().st_mtime if dest.exists() else 0
    if server_ts and cur_ts >= server_ts:
        return dest, etag
    
    since = dt.datetime.fromtimestamp(cur_ts, dt.timezone.utc)
    since = format_datetime(since, usegmt=True)
    headers = {
        'If-Modified-Since': since,
        'If-None-Match': etag,
    }
    headers = {k: v for k, v in headers.items() if v is not None}  # trim none values
    
    async with session.get(url, headers=headers) as response:
        etag = response.headers.get('etag')
        if not response.ok:  # < 400
            return None, etag
        
        if response.status == 304:
            return dest, etag
        
        # if "content-disposition" in response.headers:
        #     header = response.headers["content-disposition"]
        #     filename = header.split("filename=")[1]
        # else:
        #     filename = res.split("/")[-1]
        
        os.makedirs(dest.parent, exist_ok=True)
        with open(dest, mode="wb") as file:
            while True:
                chunk = await response.content.read(CHUNKSIZE)
                if not chunk:
                    break
                file.write(chunk)
        return dest, etag
