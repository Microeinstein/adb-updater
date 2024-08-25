# adb-updater

Command line tool to update all your third-party installed apps on your Android phone, using F-Droid repositories.

## Gallery

TODO

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
- [x] cache HTTP ETag for repositories indices
- [x] check app compatibility
    - [x] phone CPU and SDK version
    - [x] app signature and version
- [x] ignore updates for certain apps
- [x] reasonably fast searching for compatible updates
- [x] print apps translated labels
- [x] respect the [XDG Base Directory specification](https://wiki.archlinux.org/title/XDG_Base_Directory) 
- [x] cross platform

## Current limitations

- no command line arguments
- no direct downloads support
- only 1 device at a time
- no network adb, only through USB
- no self auto-update
- untested on macOS
- untested on Android lower than 10

## Download

#### x86-64


| Windows  |   Unix   | macOS / _unlisted_ | Other  |
| :------: | :------: | :----------------: | :----: |
| Portable |  Binary  | _try Unix binary_  | Docker |
|          | AppImage |                    |        |

If you want to distribute this project through other channels _and maintain those packages_, feel free to reach out.

## Configuration

| Distribution       | Location                                |
| ------------------ | --------------------------------------- |
| Unix / macOS       | `$HOME/.config/adb-updater/config.toml` |
| Windows (portable) | `.\config\config.toml`                  |

```toml
# Package name of apps to not update
ignore_pkg = [
    'org.blokada.fem.fdroid',
]

# Max cache days for each downloaded apps
apk_max_days = 1
# TODO: other cache options

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

| Name                           | Usage                                   | Notes                                                        |
| ------------------------------ | --------------------------------------- | ------------------------------------------------------------ |
| **Resources**                  |                                         |                                                              |
| &emsp;[lister helper jar](dex-lister) | get phone information                   |                                                              |
| **Python** 3.10                |                                         |                                                              |
| &emsp;`pyinstaller`            | linux and windows binaries              | dev only                                                     |
| &emsp;`cx-freeze`              |                                         | dev only                                                     |
| &emsp;`python-adb`             | phone interaction                       | git submodule; [a fork](https://github.com/MasonAmerica/python-adb) of this [project](https://github.com/google/python-adb) |
| &emsp;&emsp;`libusb1`          | raw USB management (wrapper)            |                                                              |
| &emsp;`tomlkit`                | configuration                           |                                                              |
| &emsp;`pysimdjson`             | extremely fast json files parsing       |                                                              |
| &emsp;`json-stream`            | json streams parsing                    |                                                              |
| &emsp;`colorama`               | cross-platform support for ANSI escapes |                                                              |
| &emsp;`tableprint`             | terminal tables                         |                                                              |
| &emsp;`readchar`               | raw user input                          |                                                              |
| &emsp;`aiohttp`                | asynchronous HTTP requests              |                                                              |
| &emsp;`certifi`                | static mozilla certificates             | optional                                                     |
| **Native**                     | all imported dependencies |                                                              |
| &emsp;`glibc`                         |                                         | linux only? |
| &emsp;`zlib`                  |                       | linux only? |
| &emsp;`libpthread`                  |                       | linux only? |
| &emsp;`ca-certificates`        | system certificates                     | optional, linux only                                       |
| &emsp;`libusb` 1.0.0           | raw USB management                      |                                                              |

> [!NOTE]
> PyInstaller freezes all python code (even the interpreter) and it bundles most native libraries, some of which are not visible through `ldd`.

> [!NOTE]
> Since ABIs are forward compatible but not backward compatible, it's optimal to compile the project with the oldest `glibc` version possible, like 2.28 present in Debian Buster. The same may apply to other native libraries. See [PyInstaller docs](https://pyinstaller.org/en/stable/usage.html#making-gnu-linux-apps-forward-compatible) for more information.

## Development

See the [contribution guide](CONTRIBUTING.md) for build instructions and more information.

## License

<!-- [GPLv3](COPYING) ([resources](/Resources) excluded) -->
<!-- [MIT](LICENSE) -->
[the fuck around and find out license v0.1](COPYING)
