# adb-updater

Command line tool to update all your third-party installed apps on your Android phone, using F-Droid repositories.

## Gallery

<img src="/.repo/linux_1.png" alt="Updating repositories" width="50.5%"> <img src="/.repo/linux_2.png" alt="Showing updates" width="48.2%"><br>
<img src="/.repo/win7_1.png" alt="Showing updates" width="49.5%"> <img src="/.repo/win7_2.png" alt="Updating apps after confirmation" width="49.5%"><br>

## Background

Stock Android ROMs never allowed any non-system app (like F-Droid or any other store) to install updates, without prompting the user for confirmation _for every single app_ — imagine having 40 updates, you have to **wait** for a popup to appear, press Yes, hope your ROM does not complain about something, then repeat for all other apps (not including the eventual <kbd>Download</kbd> press and the <kbd>Install</kbd> press, **that's 200 user interactions!**).

Of course one could root their phone, but that's not always possible, at least without breaking some apps and not making them show warnings (DRMs, home banking, etc...).

One way is possible though: installing apps through ADB — this method does not require any user interaction (excluding manual compatibility checks and download of course), so I decided to exploit that.

A similar way is to gain shell permissions through ADB and launch a local service to allow apps exploiting them (with the only caveat that this service must be manually restarted after each reboot). [Someone implemented this idea as Shizuku](https://github.com/RikkaApps/Shizuku), but stores must support it in order to be any useful and [despite being open source, it is not free](https://github.com/RikkaApps/Shizuku?tab=readme-ov-file#license).

## Features

- [x] using a python ADB reimplementation, no need for google's adb binary
- [x] support F-Droid repositories — both index v1 and v2
- [x] ask to backup F-Droid when no repositories are configured
- [x] generate adbkey when missing
- [x] asynchronous download when possible
- [x] caching
    - [x] repositories indices, using HTTP ETag
    - [x] apps to update multiple phones in a row (tunable)
- [x] check app compatibility
    - [x] phone CPU and SDK version
    - [x] app signature and version
- [x] ignore updates for certain apps
- [x] reasonably fast searching for compatible updates
- [x] print apps translated labels
- [x] respect the [XDG Base Directory specification](https://wiki.archlinux.org/title/XDG_Base_Directory) 
- [x] cross platform

## Backlog

- [ ] command line arguments
- [ ] improve UX
- [ ] add default repositories
- [ ] make f-droid backup optional
- [ ] direct downloads support
- [ ] more than 1 device simultaneously
- [ ] network adb
- [ ] handle small-width terminals
- [ ] support other type of sources like [Obtanium](https://github.com/ImranR98/Obtainium)?
- [ ] CI/CD
    - [ ] build on Windows 10 using [PythonWin7](https://github.com/adang1345/PythonWin7), test on Windows 7
- [ ] test on macOS
- [ ] test on Android lower than 10

## Unplanned

- [ ] self auto-update

## Download

See [releases](https://github.com/Microeinstein/adb-updater/releases).

<!--
<details open><summary><b>x86-64</b></summary>

| Windows  |  Unix  | macOS / _unlisted_ |
| :------: | :----: | :----------------: |
| Portable | Binary | _try Unix binary_  |

[Portable](https://github.com/Microeinstein/adb-updater/releases/download/v0.1/adb-updater-0.1-windows-x86-64.zip)

</details>
-->

If you want to distribute _and maintain_ other packages of this project for other channels, feel free to reach out.

## Usage

1. open a terminal
1. `./adb-updater` <sub>(in the program directory, if not added to PATH)</sub>
1. if no repositories are configured, a backup of F-Droid from your phone must be made
1. _wait for repositories syncing_
1. _wait for phone apps scanning_
1. results will be printed, press <kbd>Y</kbd> if you want to proceed
1. _wait for apps downloading_
1. _wait for apps installation_
1. profit

## Configuration

| Distribution       | Location                                |
| ------------------ | --------------------------------------- |
| Posix              | `$HOME/.config/adb-updater/config.toml` |
| Windows (portable) | `.\config\config.toml`                  |

```toml
# Package name of apps to not update
ignore_pkg = [
    'org.blokada.fem.fdroid',
]

# Max cache days for each downloaded apps
[cache.apps]
max_days = 30
max_size = "1G"

# Configured repositories, descending order of priority
[[repos]]
name = "F-Droid Archive"
address = "https://f-droid.org/archive/"

[[repos]]
name = "F-Droid"
address = "https://f-droid.org/repo/"

# ...
```

## Dependencies

<details><summary><b>Resources</b></summary>

| Name                            | Usage                 | Notes |
| ------------------------------- | --------------------- | ----- |
| [lister helper jar](dex-lister) | get phone information |       |

</details>

<details><summary><b>Python</b> 3.10</summary>

| Name            | Usage                                   | Notes                                                                                                                       |
| --------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `pyinstaller`   | linux and windows binaries              | dev only                                                                                                                    |
| `python-adb`    | phone interaction                       | git submodule; [a fork](https://github.com/MasonAmerica/python-adb) of this [project](https://github.com/google/python-adb) |
| &emsp;`libusb1` | raw USB management (wrapper)            |                                                                                                                             |
| `tomlkit`       | configuration                           |                                                                                                                             |
| `pysimdjson`    | extremely fast json files parsing       |                                                                                                                             |
| `json-stream`   | json streams parsing                    |                                                                                                                             |
| `colorama`      | cross-platform support for ANSI escapes |                                                                                                                             |
| `tableprint`    | terminal tables                         |                                                                                                                             |
| `readchar`      | raw user input                          |                                                                                                                             |
| `aiohttp`       | asynchronous HTTP requests              |                                                                                                                             |
| `certifi`       | static mozilla certificates             | optional                                                                                                                    |

</details>

<details><summary><b>Native</b> (all OS)</summary>

| Name           | Notes |
| -------------- | ----- |
| `libusb` 1.0.0 |       |

</details>

<details><summary><b>Native</b> (posix)</summary>

| Name              | Notes     |
| ----------------- | --------- |
| `glibc`           | see below |
| `zlib`            |           |
| `libpthread`      |           |
| `ca-certificates` | optional  |

</details>

### Platform notes

- PyInstaller freezes all python code (even the interpreter) and it bundles most native libraries, some of which are not visible through `ldd`.

- Since ABIs are forward compatible but not backward compatible, it's optimal to compile the project with the oldest `glibc` version possible, like 2.28 present in Debian Buster. The same may apply to other native libraries. See [PyInstaller docs](https://pyinstaller.org/en/stable/usage.html#making-gnu-linux-apps-forward-compatible) for more information.

- On Windows 7 you may (must?) need to install update KB2533623 or KB3063858,<br>
  as per [this fork of Python 3.10](https://github.com/adang1345/PythonWin7).

## Development

See the [contribution guide](CONTRIBUTING.md) for build instructions and more information.

## License

<!-- [GPLv3](COPYING) ([resources](/Resources) excluded) -->
<!-- [MIT](LICENSE) -->
[the fuck around and find out license v0.1](COPYING)
