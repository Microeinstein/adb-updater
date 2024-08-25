# Contributing to adb-updater

## Preparation

1. clone this repository

```nginx
git clone --recurse-submodules 'https://github.com/Microeinstein/adb-updater.git'
# or
git clone --recurse-submodules 'git@github.com:Microeinstein/adb-updater.git'
```

### Local build preparation

2. create a virtual environment (recommended);<br>
   I suggest using an env which supports native packages other than pip ones, like miniconda

```nginx
conda create -p './venv'
conda activate './venv'
conda install  python=3.10  libpython-static=3.10
pip install -r 'requirements.txt'
pip install pyinstaller
```

3. build the lister helper

## Actions

<table><tbody>
<tr><td valign="top">
<sup><h3>Local build</h3></sup>
</td><td>

```nginx
# make sure to activate your virtual environment
# check the script for other flags
bash build.sh  # --clean --onefile
```

</td></tr>
<tr></tr>
<tr><td valign="top">
<sup><h3>&emsp;&ensp;Running</h3></sup>
</td><td>

```nginx
export PYTHONPATH="./src"
python -m adb_updater  # ...
```

</td></tr>
<tr></tr>
<tr><td valign="top">
<sup><h3>Docker build</h3></sup>
</td><td>

```nginx
# install: docker  docker-buildx
docker --debug  build -t adb-updater  '.'
```

</td></tr>
<tr></tr>
<tr><td valign="top">
<sup><h3>&emsp;&ensp;Running</h3></sup>
</td><td>

```nginx
# connect your phone and check for the usb path
lsusb
docker run -it --device=/dev/bus/usb/BUS/DEV  adb-updater:latest
```

</td></tr>
</tbody></table>



