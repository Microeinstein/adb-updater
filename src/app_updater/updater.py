#!/usr/bin/env python3

import os, asyncio, time

from pathlib import Path
from typing import Any

import tableprint as tp
from usb1 import USBError
from adb import usb_exceptions

from .core.context import ContextProp, a_autoexit, with_all
from .core.io import chunked_stream
from .core.config import TOMLConfig
from .core.ui import *
from .core.misc import Dummy, round_robin
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
    ignore_pkg: list[str]
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
            self.ignore_pkg = config.ignore_pkg
            
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
        
        # with self.phone.get_dumpsys_packages() as dump:
        #     dumpsys = TextIterStream(dumpsys)
        #     for app in InstalledApp._fetch_foreign_apps(dumpsys):
        #         self.apps[app.package] = app
        
        n = Dummy(
            total = 0,
            system = 0,
            removed = 0,
            foreign = 0,
            ignored = 0,
        )
        
        def app_filter(app: InstalledApp):
            nonlocal n
            valid = False
            
            ign = app.package in self.ignore_pkg
            n.total += 1
            n.system += int(app.system)
            n.removed += int(app.removed)
            n.ignored += int(ign)
            if not app.system and (not app.installer or app.installer in AndroidApp.OPEN_STORES):
                n.foreign += 1
                valid = not ign
                
            return valid
        
        print('\x1b7', end='')
        
        self.phone.load_phone_info(app_filter)
        
        print(f'\x1b8\x1b[0J', end='')
        for k, v in (
            ('total', n.total),
            ('system', n.system),
            ('removed', n.removed),
            ('closed', n.total - n.system - n.foreign),
            ('foreign', n.foreign),
            ('ignored', n.ignored),
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
        
        async def upd(r: FDroidRepo):
            r.load_repo_apps(self.phone)
        await asyncio.gather(*[upd(r) for r in self.repos])
        
        title("Checking updates...")
        self.updates = {}
        self.missing = {}
        
        for pkg, app in self.phone.apps.items():
            app: InstalledApp
            found = False
            
            for r in self.repos:
                r: FDroidRepo
                repo_app = r.apps.get(pkg)
                if not repo_app:
                    continue
                found = True
                # app is found, but must also get latest version across repos
                if repo_app.version_code <= app.version_code:
                    continue
                if pkg in self.updates and repo_app.version_code <= self.updates[pkg][1].version_code:
                    continue

                self.updates[pkg] = (app, repo_app)
            
            if not found:  # in any repo
                self.missing[pkg] = app
        
        self.updates = dict(sorted(
            self.updates.items(),
            key=lambda i: (i[1][0].installer or 'n/a', i[1][1].label)
        ))
        
        if not self.updates:
            if not self.missing:
                print(f"Up to date.")
            else:
                print(f"Up to date, {len(self.missing)} missing.")
            return False
        
        if self.missing:
            print("Missing from repos:")
            miss: list[Any] = self.missing.values()
            InstalledApp.print_apps_table(miss)
        # else:
        #     print('  (none)')
        
        return True
    
    
    def ask_updates(self):
        title(f"{len(self.updates)} updates are available:")
        
        rows = []
        for _pkg, (inst, upd) in self.updates.items():
            rows.append((
                f"{middle_ellipsis(inst.label, 18)} @ {upd.repo.name:>14s}",
                middle_ellipsis(inst.version_name or '?', 18).rjust(18) + ' -> ' +
                middle_ellipsis(upd.version_name or '!?', 18).ljust(18),
            ))
        tp.table(rows, 'Label @ Repo  From -> To'.split('  '))
        
        return ask_yes_no(f"Do you want to update {len(self.updates)} apps?")
    
    
    async def download_updates(self):
        title("Downloading...")
        num_parallel = 4
        queue: asyncio.Queue[FDroidApp|None] = asyncio.Queue(num_parallel)
        
        async def worker():
            while True:
                app = await queue.get()
                if app:
                    print(f"  {app.label} ({app.version_name})...")
                    await app.download()
                queue.task_done()
                if not app:
                    return
        
        for _ in range(num_parallel):
            asyncio.create_task(worker())
        
        # parallelize by repo address; requesting multiple apps
        # from the same repository creates a bottle neck
        async def run():
            for _pkg, (_inst, upd) in round_robin(self.updates.items(), lambda kv: kv[1][1].repo.address):
                await queue.put(upd)
            await queue.join()
        
        await with_all(*self.repos, opener=lambda r: r.connect(), callback=run)
        
        for _ in range(num_parallel):
            await queue.put(None)
        
        print()
        failed: list[FDroidApp] = []
        for _pkg, (_inst, upd) in self.updates.items():
            if upd.local_path is None:
                failed.append(upd)
        
        len_upds = len(self.updates)
        for upd in failed:
            del self.updates[upd.package]
        
        print(f"Downloaded {len_upds - len(failed)} / {len_upds} apps.")
    
    
    def install_updates(self):
        title("Installing...")
        
        failed: list[FDroidApp] = []
        for _pkg, (_inst, upd) in self.updates.items():
            if not upd.local_path:
                continue
            
            print(f"  {upd.label} ({upd.version_name})...  ", end='')
            try:
                start = time.time()
                self.phone.install_app(upd.local_path)
            except RuntimeError as e:
                failed.append(upd)
                print(f'FAIL ({e})')
            else:
                end = time.time()
                print(f'OK ({int(end - start)}s)')
        
        len_upds = len(self.updates)
        print(f"Installed {len_upds - len(failed)} / {len_upds} apps.")

    
    @a_autoexit
    async def main(self, arg0, *args) -> int|None:
        try:
            self.load_config()
            await self.update_repos()
            self.load_apps()
            if not await self.check_updates():
                return
            if not self.ask_updates():
                return
            await self.download_updates()
            self.install_updates()
            
        except (USBError, usb_exceptions.CommonUsbError):
            error("Phone does not respond :(")
