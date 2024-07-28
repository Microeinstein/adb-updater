
import re
from dataclasses import dataclass
from typing import Sequence, Any

import tableprint as tp

from ..core.misc import get_base_classes
from ..core.ui import middle_ellipsis


@dataclass
class AndroidApp:
    PKG_INSTALLER = 'com.google.android.packageinstaller'
    FDROID_APP    = 'org.fdroid.fdroid'
    FOXYDROID_APP = 'nya.kitsunyan.foxydroid'
    FFUPDATER_APP = 'de.marmaro.krt.ffupdater'
    ISLAND_SBOX   = 'com.oasisfeng.island.fdroid'
    PLAY_STORE    = 'com.android.vending'
    AMAZON_STORE  = 'com.amazon.venezia'
    HUAWEI_STORE  = 'com.huawei.appmarket'
    AURORA_STORE  = 'com.aurora.store'
    
    OPEN_STORES   = [
        PKG_INSTALLER,
        FDROID_APP,
        FOXYDROID_APP,
        FFUPDATER_APP
    ]
    
    package: str
    label: str
    version_code: str
    version_name: str
    
    @classmethod
    def get_installer_name(cls, pkg: str) -> str|None:
        for c in get_base_classes(cls):
            for k, v in c.__dict__.items():
                if v == pkg:
                    return k.replace('_', ' ').title()
        return None


@dataclass
class InstalledApp(AndroidApp):
    RGX_ATTR = re.compile(r"^[ \t]+([a-z]+)=(.*)$", re.I)
    RGX_PKG  = re.compile(r"[^ ]+\{[^ ]+ ([^ ]+)\}.*$", re.I)
    RGX_VER  = re.compile(r"([^ ]+).*$", re.I)
    
    system: bool
    removed: bool
    installer: str|None = None
    
    @classmethod
    def _fetch_foreign_apps(cls, text_iter):
        raise RuntimeError("deprecated")
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
    def from_lister(cls, japp: dict[str, Any]) -> "InstalledApp":
        return InstalledApp(
            package      = japp['pkg'],
            label        = japp['label'],
            version_code = japp['vcode'],
            version_name = japp['vname'],
            system       = japp['system'],
            removed      = japp['removed'],
            installer    = japp['installer'],
        )
        
    @classmethod
    def print_apps_table(cls, apps: Sequence["InstalledApp"]):
        apps = sorted(apps, key=lambda a: (a.installer, a.label))
        rows = []
        for a in apps:
            a: "InstalledApp"
            inst = cls.get_installer_name(a.installer) or a.installer if a.installer else '?'
            rows.append((
                middle_ellipsis(a.label, 18),
                middle_ellipsis(a.version_name or '?', 18),
                middle_ellipsis(inst, 18),
            ))
        tp.table(rows, 'Label Version Installer'.split())
