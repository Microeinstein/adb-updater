
import os.path, io, tarfile

import json_stream
from adb import adb_commands, sign_cryptography
from adb import usb_exceptions as usb_ex

from .core.streams import *
from .core.misc import PropMessage
from .platform import Platform

# NOTE: adb_commands.AdbCommands.BytesStreamingShell requires a byte-format command


class AndroidPhone:
    TMP = '/data/local/tmp'
    
    device: adb_commands.AdbCommands = PropMessage("Phone is not connected.")  


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
        self.device.Close()
        self.device = None
        # suppress error -> return True
    
    
    def get_dumpsys_packages(self) -> io.IOBase:
        text_iter = self.device.StreamingShell('dumpsys package packages')
        return TextIterStream(text_iter)
    
    def get_package_list(self):
        lister_fn = os.path.basename(Platform.LISTER_JAR)
        dest = f"{AndroidPhone.TMP}/{lister_fn}"
        
        self.device.Push(str(LISTER_JAR), dest, timeout_ms=30000)
        
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
