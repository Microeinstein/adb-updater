
import io, zlib
from abc import ABC
from dataclasses import dataclass, field
from collections.abc import Iterator, Generator
from typing import IO, TypeVar, Generic, Any
from typing_extensions import override


CHUNKSIZE = 1024 * 4 * 4


def open_or_create(file, mode: str, *a, **kw) -> io.FileIO | IO[Any]:
    try:
        return open(file, mode, *a, **kw)
    except OSError:
        mode = 'a+' + mode.translate(str.maketrans('', '', 'awr+'))
        return open(file, mode, *a, **kw)


def chunked_stream(stream: io.RawIOBase | IO[bytes], chunksize=CHUNKSIZE) -> Generator[bytes]:
    while True:
        c = stream.read(chunksize)
        if not c:
            break
        yield c


def flush_stream(stream: io.IOBase | IO[Any]):
    if isinstance(stream, io.RawIOBase):
        while stream.read(CHUNKSIZE):
            pass
    else:
        while stream.readline():
            pass


Tbuff = TypeVar('Tbuff', io.StringIO, io.BytesIO)
Tstr = TypeVar('Tstr', str, bytes)

@dataclass
class IterStream(ABC, Generic[Tbuff, Tstr], io.IOBase):
    iter: Iterator[Tstr]
    leftover: Tbuff = field(init=False)
    
    def __post_init__(self):
        self.iter = iter(self.iter)
        self.leftover = self.__annotations__['leftover']()
    
    @override
    def seekable(self): return False
    
    @override
    def readable(self): return True
    
    @override
    def writable(self): return False
    
    def _seek_to_cut(self, buffer, size):
        ...
    
    def _read_limiter(self, buffer):
        return False
    
    @override
    def close(self):
        flush_stream(self)
        super().close()
    
    def _read(self, size: int|None = -1, /) -> Tbuff:
        size = -1 if size is None else size
        buffer: ... = self.leftover
        if size == 0:
            return buffer
        
        cur = buffer.seek(0, io.SEEK_END)
        
        try:
            while (size < 0 or cur < size) and not self._read_limiter(buffer):
                data: Tstr = next(self.iter)
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


class TextIterStream(IterStream[io.StringIO, str], io.TextIOBase):
    leftover: io.StringIO
    _line: str
    
    @override
    def _seek_to_cut(self, buffer, size):
        self._line = buffer.readline(size)
    
    @override
    def _read_limiter(self, buffer):
        return buffer.tell() > 0
    
    def readlines(self, hint=-1, /) -> list[str]:  # pyright: ignore[reportIncompatibleMethodOverride, reportImplicitOverride]
        lines = []
        while hint != 0:
            line = self.readline()
            if not line:
                break
            if hint >= 0:
                hint -= 1
            lines.append(line)
        return lines
    
    def readline(self, size=-1, /) -> str:  # pyright: ignore[reportIncompatibleMethodOverride, reportImplicitOverride]
        super().read(size)
        return self._line
    
    @override
    def read(self, size=-1, /) -> str:
        return super()._read(size).getvalue()


class RawIterStream(IterStream[io.BytesIO, bytes], io.RawIOBase):
    leftover: io.BytesIO
    
    @override
    def _seek_to_cut(self, buffer, size):
        if size >= 0:
            buffer.seek(size)
    
    @override
    def readall(self) -> bytes:
        return self.read()
    
    @override
    def read(self, size=-1, /) -> bytes:
        return super()._read(size).getvalue()


def ZlibDecompStream(fileobj: io.RawIOBase | IO[bytes]):
    def chunked():
        dec = zlib.decompressobj(wbits=15)
        while True:
            raw: bytes = fileobj.read(CHUNKSIZE)
            raw = dec.decompress(raw)
            if not raw:
                break
            yield raw
    return RawIterStream(chunked())


def GzipDecompStream(fileobj: io.RawIOBase | IO[bytes]):
    def chunked():
        dec = zlib.decompressobj(wbits=47)
        while True:
            raw: bytes = fileobj.read(CHUNKSIZE)
            raw = dec.decompress(raw)
            if not raw:
                break
            yield raw
    return RawIterStream(chunked())
