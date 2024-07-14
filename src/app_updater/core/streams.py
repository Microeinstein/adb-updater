
import io, zlib
from abc import ABC
from dataclasses import dataclass, field
from typing import List, Iterable

__all__ = 'CHUNKSIZE  IterStream  RawIterStream  TextIterStream  ZlibDecompStream  GzipDecompStream  chunked_stream  flush_stream'.split()

CHUNKSIZE = 1024 * 4 * 4



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
            raw = dec.decompress(fileobj.read(CHUNKSIZE))
            if not raw:
                break
            yield raw
    return RawIterStream(chunked())


def GzipDecompStream(fileobj: io.RawIOBase):
    def chunked():
        dec = zlib.decompressobj(wbits=47)
        while True:
            raw = dec.decompress(fileobj.read(CHUNKSIZE))
            if not raw:
                break
            yield raw
    return RawIterStream(chunked())


def chunked_stream(stream: io.RawIOBase, chunksize=CHUNKSIZE) -> bytes:
    while True:
        c = stream.read(chunksize)
        if not c:
            break
        yield c


def flush_stream(stream: io.IOBase):
    if isinstance(stream, io.RawIOBase):
        stream: io.RawIOBase
        while stream.read(CHUNKSIZE):
            pass
    else:
        while stream.readline():
            pass
