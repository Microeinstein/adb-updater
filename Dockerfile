# syntax=docker/dockerfile:1.7-labs

FROM archlinux:latest  AS base_env

RUN --mount=type=cache,target=/var/cache/pacman/pkg <<EOF
set -euo pipefail

echo "Installing repo packages..."
pacman-key --init
pacman -Sy --noconfirm --noprogressbar \
    sudo  fakeroot  binutils  unzip  wget  jq  p7zip  jdk-openjdk

echo "Configuring..."
# allow all users to all commands without password
cat <<CFG >/etc/sudoers
ALL ALL=(ALL:ALL) NOPASSWD: ALL
CFG

# no debug symbols, no compression
sed -iE '
    /^OPTIONS=/ s/!*debug/!debug/g
    /^(PKG|SRC)EXT=/ s/\.(zst|gz)//g
' /etc/makepkg.conf

useradd -ms /bin/bash devuser
EOF


#######################################
FROM base_env  AS android_env

USER devuser
WORKDIR /home/devuser

RUN <<EOF
set -euo pipefail
wget() { command wget --no-verbose --show-progress --progress=dot:giga "$@"; }
export -f wget

echo "Installing AUR packages..."

# use specific known good commits, never the latest version
declare -A pkgs=(
    [android-sdk]='https://aur.archlinux.org/cgit/aur.git/snapshot/aur-81fe6b333003848e1a9d9c1d382fbe8fc8ffc625.tar.gz'

    [android-platform]='https://aur.archlinux.org/cgit/aur.git/snapshot/aur-3bf7523a73d536561329749cde01162a36905ea3.tar.gz'
    
    [android-sdk-platform-tools]='https://aur.archlinux.org/cgit/aur.git/snapshot/aur-486dff3428bca912bda70e51ad5d2ab7095fa6b1.tar.gz'

    [android-sdk-build-tools]='https://aur.archlinux.org/cgit/aur.git/snapshot/aur-ce7b51fed9ef7e0db9ee681883204adde1ef3808.tar.gz'
    
    [payload-dumper-go]='https://aur.archlinux.org/cgit/aur.git/snapshot/aur-140208028f9427ce244a6d7a0d56236b9cfc7b24.tar.gz'

    [dex2jar]='https://aur.archlinux.org/cgit/aur.git/snapshot/aur-505e75dcc7c117127ed5f7ac2ab66835afad0e35.tar.gz'
)

for name in "${!pkgs[@]}"; do
    echo "> $name"
    declare -n url="pkgs[${name@Q}]"
    wget -O "$name.tgz" "$url"
    tar -xzf "$name.tgz"
    mv aur* "$name"
    cd "$name"
    makepkg -si --noconfirm --noprogressbar >/dev/null
    rm -rf "$name.tgz" "$name"
    cd -
done
EOF


#######################################
FROM android_env  AS android_proj

USER root
WORKDIR /project
COPY --parents  bin  foreign  dex-lister  ./

RUN <<EOF
set -euo pipefail
wget() { command wget --no-verbose --show-progress --progress=dot:giga "$@"; }
export -f wget

to='dex-lister/lib/'
mkdir -p "$to"

echo "Getting LineageOS system libraries..."
bash bin/get-lineageos-libs.sh

# cp -vrlaPf 'foreign/lib/'*.jar "$to"
# only expose required libraries
for n in framework.jar; do
    cp -vrlaPf "foreign/lib/$n" "$to"
done

echo "Getting project libraries..."
wget -P "$to" https://repo.mavenlibs.com/maven/com/google/code/gson/gson/2.10.1/gson-2.10.1.jar
EOF


#######################################
FROM android_proj  AS build_lister

WORKDIR /project
ENV TERM=linux

RUN <<EOF
set -euo pipefail
wget() { command wget --no-verbose --show-progress --progress=dot:giga "$@"; }
export -f wget

echo "Building dex-lister"
bash dex-lister/build.sh
EOF


#######################################
FROM python:3.10.12-slim-buster  AS py_env

WORKDIR /project
COPY requirements.txt .

ENV PIP_ROOT_USER_ACTION=ignore
ENV PIP_CACHE_DIR=/var/cache/pip

RUN --mount=type=cache,target=/var/cache/apt  \
    --mount=type=cache,target=/var/cache/pip  \
    <<EOF
set -eu
apt update
apt -y install binutils
pip install --cache-dir "$PIP_CACHE_DIR" -r requirements.txt
pip install --cache-dir "$PIP_CACHE_DIR" pyinstaller
# do not embed these libraries
apt -y remove openssl
EOF


#######################################
FROM py_env  AS build_proj

WORKDIR /project
COPY . .

COPY --link --parents --from=build_lister  \
    /project/dex-lister/build/lister.jar   /

RUN bash build.sh  --clean --onefile


#######################################
FROM debian:buster-slim  AS release

COPY --link --from=build_proj  \
    /project/dist/adb-updater  /bin/

RUN --mount=type=cache,target=/var/cache/apt <<EOF
set -eu
apt update
apt -y install openssl ca-certificates libusb-1.0.0
EOF

RUN <<EOF
set -eu
adb-updater || :  # generate adbkey
stat /root/.android/adbkey
EOF

CMD ["adb-updater"]
