#!/usr/bin/env python3

import os, asyncio

from pathlib import Path
from typing import Any

import tableprint as tp

from .core.context import ContextProp, a_autoexit
from .core.io import chunked_stream
from .core.config import TOMLConfig
from .core.ui import *
from .android.phone import *
from .android.apps import *
from .android.fdroid import *
from .platform import Platform


class UpdaterConfig(TOMLConfig):
    ignore_pkg: list[str] = ['ignore.during.updates']
    repos: list[dict[str, Any]]


class Updater:
    FDROID_BKP_DB = f'apps/{AndroidApp.FDROID_APP}/db/fdroid_db'
    FDROID_DB = Platform.CACHE / Path(os.path.basename(FDROID_BKP_DB))
    
    phone: AndroidPhone = ContextProp()
    repos: list[FDroidRepo]
    apps: dict[str, InstalledApp]  # foreign
    updates: dict[str, tuple[InstalledApp, FDroidApp]]
    missing: dict[str, InstalledApp]


    def repos_from_backup(self):
        if not self.FDROID_DB.is_file():
            print("Getting FDroid database from phone... (requires manual confirm)")
            
            with self.phone.get_package_backup(AndroidApp.FDROID_APP) as bkp, \
                 open(self.FDROID_DB, 'wb') as fout:
                
                db_data: io.RawIOBase = AndroidPhone.get_file_from_backup(bkp, self.FDROID_BKP_DB)
                for chunk in chunked_stream(db_data):
                    fout.write(chunk)
    
        return FDroidRepo.read_from_backup(self.FDROID_DB)


    def load_config(self):
        title("Loading config...")
        
        with open(Platform.CONFIG, 'r+t') as fconf:
            config = UpdaterConfig.load(fconf)
        
            repos = config.repos
            if not repos:
                repos = self.repos_from_backup()
            else:
                repos = (FDroidRepo.load(r) for r in repos)
            self.repos = list(repos)
            
            # prepare for save
            config.repos = list(r.save() for r in self.repos)
            
            # save changes
            fconf.seek(0)
            config.dump(fconf)
        
        title("Repositories:")
        for r in self.repos:
            print(f"  {r.name:<40s} {r.address}")
    
    
    def load_apps(self):
        title("Getting packages...")
        self.apps = {}
        
        # with self.phone.get_dumpsys_packages() as dump:
        #     dumpsys = TextIterStream(dumpsys)
        #     for app in InstalledApp._fetch_foreign_apps(dumpsys):
        #         self.apps[app.package] = app
        
        n_total = 0
        n_system = 0
        n_removed = 0
        n_foreign = 0
        
        print('\x1b7Awaiting response from device...')
        for japp in self.phone.get_package_list():
            app = InstalledApp.from_lister(japp)
            n_total += 1
            n_system += int(app.system)
            n_removed += int(app.removed)
            if not app.system and app.installer in AndroidApp.OPEN_STORES:
                n_foreign += 1
                self.apps[app.package] = app
            
            print(f'\x1b8\x1b[0J', end='')
            for k, v in (
                ('total', n_total),
                ('system', n_system),
                ('removed', n_removed),
                ('closed', n_total - n_system - n_foreign),
                ('foreign', n_foreign),
            ):
                print(f"  {k:<8} : {v}")
        
        # InstalledApp.print_apps_table(self.apps.values())
    
    
    async def update_repos(self):
        title("Updating repos...")
        with FDroidRepo.load_cache():
            tasks = [r.update_repo() for r in self.repos]
            await asyncio.gather(*tasks)
    
    
    async def check_updates(self):
        title("Loading repos apps...")
        
        pkgs = self.apps.keys()
        async def upd(r):
            r.load_repo_apps(pkgs)
        await asyncio.gather(*[upd(r) for r in self.repos])
        
        title("Checking updates...")
        self.updates = {}
        self.missing = {}
        
        for pkg, app in self.apps.items():
            app: InstalledApp
            found = False
            
            for r in self.repos:
                r: FDroidRepo
                latest: FDroidApp = r.apps.get(pkg)
                if latest:
                    found = True
                    if latest.version_code > app.version_code:
                        self.updates[pkg] = (app, latest)
                        break
            
            if not found:  # in any repo
                self.missing[pkg] = app
        
        print("Not found in any repo:")
        miss: list[Any] = self.missing.values()
        InstalledApp.print_apps_table(miss)
    
    
    def ask_updates(self):
        if not self.updates:
            if not self.missing:
                title(f"Up to date.")
            else:
                title(f"Up to date, {len(self.missing)} missing.")
            return False
        
        title(f"{len(self.updates)} updates are available:")
        
        upds = dict(sorted(
            self.updates.items(),
            key=lambda i: (i[1][0].installer, i[1][1].label)
        ))
        rows = []
        for _pkg, (inst, upd) in upds.items():
            rows.append((
                middle_ellipsis(inst.label, 18),
                middle_ellipsis(inst.version_name or '?', 18).rjust(18) + ' -> ' +
                middle_ellipsis(upd.version_name or '!?', 18).ljust(18)
            ))
        tp.table(rows, 'Label  From -> To'.split('  '))
        
        return ask_yes_no("Do you want to update?")

    
    @a_autoexit
    async def main(self, arg0, *args) -> int:
        self.load_config()
        await self.update_repos()
        return 0
        self.load_apps()
        await self.check_updates()
        if not self.ask_updates():
            return
        title("Downloading...")
