# Contributing to adb-updater

## Workflow

1. clone this repository

   ```nginx
   git clone --recurse-submodules 'https://github.com/Microeinstein/adb-updater.git'
   # or
   git clone --recurse-submodules 'git@github.com:Microeinstein/adb-updater.git'
   ```

### Local machine (posix)

2. [build the lister helper](../dex-lister)

3. create a virtual environment (recommended);<br>
   I suggest using an env which supports native packages other than pip ones, like miniconda

   ```nginx
   conda create -p './venv'
   conda activate './venv'
   conda install  python=3.10  libpython-static=3.10
   pip install -r 'requirements.txt'
   pip install pyinstaller
   ```

4. do your hacking on your favorite IDE/editor;<br>
   I personally use VSCodium <sub><i>with ms extensions</i></sub> for the whole project

4. build the project

   ```nginx
   # check the script for other flags
   bash build.sh;  # --clean --onefile
   ```

5. run the project

   ```nginx
   bash build.sh  run
   # or
   export PYTHONPATH="./src"
   python -m adb_updater;  # ...
   ```

### Local machine (Windows)

It is suggested to use bash from [Git for Windows](https://github.com/git-for-windows/git/releases), which is taken from MSYS2;<br>
last (un)official working versions for Windows 7:

- Git for Windows — [v2.46.0.windows.1](https://github.com/git-for-windows/git/releases/tag/v2.46.0.windows.1)
- Python 3.10 — [custom fork](https://github.com/adang1345/PythonWin7)
   - `cryptography==41.0.0`

---

2. [build the lister helper](../dex-lister)

### Docker

The current [Dockerfile](Dockerfile) makes use of<br>
- `archlinux` image + AUR for Android SDK and lister building,
- `python:3.10.12-slim-buster` image for project building,
- `debian:buster-slim` for project running.

A new adbkey will be generated at the last layer.

2. build all

   ```nginx
   # install: docker  docker-buildx
   docker --debug  build -t adb-updater  '.'
   ```

3. run the project

   ```nginx
   # connect your phone and check for the usb path
   lsusb
   docker run -it --device=/dev/bus/usb/BUS/DEV  adb-updater:latest
   ```
