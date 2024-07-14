
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from .core.misc import get_base_classes

__all__ = 'AndroidApp  InstalledApp  FDroidApp'.split()


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
    def get_installer_name(cls, pkg: str) -> str:
        for c in get_base_classes(cls):
            for k, v in c.__dict__.items():
                if v == pkg:
                    return k.replace('_', ' ').title()


@dataclass
class InstalledApp(AndroidApp):
    RGX_ATTR = re.compile(r"^[ \t]+([a-z]+)=(.*)$", re.I)
    RGX_PKG  = re.compile(r"[^ ]+\{[^ ]+ ([^ ]+)\}.*$", re.I)
    RGX_VER  = re.compile(r"([^ ]+).*$", re.I)
    
    system: bool
    removed: bool
    installer: Optional[str] = None
    
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
    def from_lister(cls, japp: Dict) -> "InstalledApp":
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
    def print_apps_table(cls, apps: List["InstalledApp"]):
        apps = sorted(apps, key=lambda a: (a.installer, a.label))
        rows = []
        for a in apps:
            a: "InstalledApp"
            rows.append((
                middle_ellipsis(a.label, 18),
                middle_ellipsis(a.version_name or '?', 18),
                middle_ellipsis(cls.get_installer_name(a.installer), 18),
            ))
        tp.table(rows, 'Label Version Installer'.split())


@dataclass
class FDroidApp(AndroidApp):
    repo: "FDroidRepo"
    url: str
    
    @classmethod
    def from_index_v2(cls, repo: "FDroidRepo", pkg: str, json_like: Dict) -> Optional["FDroidApp"]:
        package = json_like['packages'].get(pkg)
        if not package:
            return None
        
        meta = package['metadata']
        last_ver = list(package['versions'].items())[0][1]
        
        return FDroidApp(
            package      = pkg,
            label        = meta['name']['en-US'],
            repo         = repo,
            version_code = last_ver['manifest']['versionCode'],
            version_name = last_ver['manifest']['versionName'],
            url          = last_ver['file']['name'],
        )
    
    @classmethod
    def from_index_v1(cls, repo: "FDroidRepo", pkg: str, json_like: Dict) -> Optional["FDroidApp"]:
        package = json_like['packages'].get(pkg)
        if not package:
            return None
        last_ver = package[0]
        
        apps = json_like['apps']
        if not isinstance(apps, dict):
            # convert this shit, only the first time
            apps = json_like['apps'] = {app['packageName']: v for app in apps}
            
        meta = apps[pkg]
        
        return FDroidApp(
            package      = pkg,
            label        = meta['localized']['en-US']['name'],
            repo         = repo,
            version_code = last_ver['versionCode'],
            version_name = last_ver['versionName'],
            url          = '/' + last_ver['apkName'],
        )
