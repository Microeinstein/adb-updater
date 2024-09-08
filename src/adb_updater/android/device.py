
import sys, os.path, io, tarfile
from pathlib import Path
from typing import IO, Callable

import simdjson
from adb import adb_commands, sign_cryptography
from adb import android_pubkey as adbkey
from adb import usb_exceptions as usb_ex

from ..core.io import *
from ..core.ui import restore_cursor_clear, save_cursor, title, ask_yes_no
from ..core.misc import jobj, PropMessage
from ..platform import USERNAME, HOSTNAME, Platform
from .apps import InstalledApp

# NOTE: adb_commands.AdbCommands.BytesStreamingShell requires a byte-format command


class AndroidDevice:
    TMP = '/data/local/tmp'
    
    device: adb_commands.AdbCommands|None = PropMessage("Device is not connected.")
    model: str
    arch: str
    supported_abis: list[str]
    min_sdk: int
    sdk: int
    apps: jobj[InstalledApp]
    
    
    @staticmethod
    def get_adbkey():
        local_key = os.path.expanduser('~/.android/adbkey')
        os.makedirs(os.path.dirname(local_key), exist_ok=True)
        
        if not Path(local_key).exists():
            adbkey.keygen(local_key)
        
        local_pub = local_key + '.pub'
        if not Path(local_pub).exists():  # only private exists
            adbkey.write_public_keyfile(local_key, local_pub)
        
        return sign_cryptography.CryptographySigner(local_key)


    def __enter__(self):
        save_cursor()
        title("Connecting to device...")
        signer = AndroidDevice.get_adbkey()
        
        while True:
            try:
                print('Awaiting authorization... (30s)')
                device = adb_commands.AdbCommands()
                device.ConnectDevice(
                    default_timeout_ms=30 * 1000,
                    auth_timeout_ms=30 * 1000,
                    banner=f"{USERNAME}@{HOSTNAME}",
                    rsa_keys=[signer]
                )
                break
            except usb_ex.DeviceAuthError:
                if not ask_yes_no('Please accept auth key on your device. Retry?', True):
                    sys.exit(0)
        
        restore_cursor_clear()
        self.device = device
        return self


    def __exit__(self, exc_type, exc_val, exc_tb):
        title("Disconnecting from device...")
        if self.device:
            self.device.Close()
            self.device = None
        # suppress error -> return True
    
    
    def is_compatible(self, *,
        min_sdk_ver: int,
        nativecode: list[str],
        **kw
    ) -> bool:
        return (
            min_sdk_ver <= self.sdk
            and (not nativecode or any(map(lambda a: a in self.supported_abis, nativecode)))
        )
    
    
    def get_dumpsys_packages(self) -> io.IOBase:
        assert self.device
        text_iter = self.device.StreamingShell('dumpsys package packages')
        return TextIterStream(text_iter)
    
    
    def load_device_info(self, app_filter: Callable[[InstalledApp], bool]|None = None):
        assert self.device
        lister_fn = os.path.basename(Platform.LISTER_JAR)
        dest = f"{AndroidDevice.TMP}/{lister_fn}"
        
        save_cursor()
        print('Awaiting response from device...')
        self.device.Push(str(Platform.LISTER_JAR), dest, timeout_ms=30000)
        
        raw_iter = self.device.BytesStreamingShell(f"""
            export CLASSPATH={dest!r};
            app_process / {Platform.LISTER_MAIN!r} | gzip;
        """.encode())
        
        # raw = RawIterStream(raw_iter)
        # gz = GzipDecompStream(raw)
        # js = json_stream.load(gz)
        # for japp in js:
        #     yield json_stream.to_standard_types(japp)
        
        # use simdjson, but it requires disk usage
        raw = RawIterStream(raw_iter)
        gz = GzipDecompStream(raw)
        cache = Platform.CACHE_DIR / 'device_apps.json'
        with open(cache, 'wb') as fout:
            for chunk in chunked_stream(gz):
                fout.write(chunk)
        
        print('Parsing response from device...')
        parser = simdjson.Parser()
        js: jobj[...] = parser.load(cache)
        
        apps = dict()
        for k, v in js['apps'].items():
            v = InstalledApp.from_lister(v)
            if not app_filter or app_filter(v):
                apps[k] = v
        
        ph: jobj[...] = js['device']
        bu: jobj[...] = ph['build']
        
        self.__dict__.update(dict(
            arch           = ph['arch'],
            model          = bu['MODEL'],
            supported_abis = list(bu['SUPPORTED_ABIS']),
            min_sdk        = bu['VERSION']['MIN_SUPPORTED_TARGET_SDK_INT'],
            sdk            = bu['VERSION']['SDK_INT'],
            apps           = apps,
        ))
        
        restore_cursor_clear()
    
    
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
