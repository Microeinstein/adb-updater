
import os.path, io, tarfile
from pathlib import Path
from typing import IO

import json_stream
from adb import adb_commands, sign_cryptography
from adb import usb_exceptions as usb_ex

from ..core.io import *
from ..core.ui import title
from ..core.misc import PropMessage
from ..platform import Platform

# NOTE: adb_commands.AdbCommands.BytesStreamingShell requires a byte-format command


class AndroidPhone:
    TMP = '/data/local/tmp'
    
    device: adb_commands.AdbCommands|None = PropMessage("Phone is not connected.")  


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
        if self.device:
            self.device.Close()
            self.device = None
        # suppress error -> return True
    
    
    def get_dumpsys_packages(self) -> io.IOBase:
        assert self.device
        text_iter = self.device.StreamingShell('dumpsys package packages')
        return TextIterStream(text_iter)
    
    def get_package_list(self):
        assert self.device
        lister_fn = os.path.basename(Platform.LISTER_JAR)
        dest = f"{AndroidPhone.TMP}/{lister_fn}"
        
        self.device.Push(str(Platform.LISTER_JAR), dest, timeout_ms=30000)
        
        raw_iter = self.device.BytesStreamingShell(f"""
            export CLASSPATH={dest!r};
            app_process / {Platform.LISTER_MAIN!r} | gzip;
        """.encode())
        
        raw = RawIterStream(raw_iter)
        gz = GzipDecompStream(raw)
        js = json_stream.load(gz)
        for japp in js:
            yield json_stream.to_standard_types(japp)
        
    def get_package_backup(self, package: str) -> io.RawIOBase:
        assert self.device
        bytes_iter = self.device.BytesStreamingShell(f"bu backup -keyvalue {package}".encode())
        return RawIterStream(bytes_iter)
    
    @staticmethod
    def get_file_from_backup(bkp: io.RawIOBase, path: str) -> tarfile.ExFileObject | io.RawIOBase:
        # dd if=fdroid.backup bs=24 skip=1 | zlib-flate -uncompress | tar -vxf -
        head: bytes = bkp.read(24)
        if not head.startswith(b'ANDROID BACKUP'):
            raise RuntimeError(f"Unknown backup format: {head!r}")
        zip: IO[bytes] = ZlibDecompStream(bkp)
        tar = tarfile.open(fileobj=zip, mode='r|')
        # NOTE: in streaming mode you must iterate members this way,
        # otherwise tar needs to seek backwards
        for member in tar:
            if member.path == path:
                f: tarfile.ExFileObject = tar.extractfile(member)
                return f
        raise RuntimeError("Unable to extract file.")
    
    def install_app(self, path: str|Path):
        assert self.device
        # 30MB -> 5 min timeout
        timeout = int(max(30, os.path.getsize(path) / 1024 / 100) * 1000)
        self.device.Install(str(path), timeout_ms=timeout)
