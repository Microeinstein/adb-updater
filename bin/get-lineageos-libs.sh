#!/bin/bash

set -euo pipefail


# print gray to stderr without commands
_dbg() ( set +x;  echo -n $'\e[90m';  "$@";  echo -n $'\e[0m'; ) >&2


# self-knowledge
SELF="${BASH_SOURCE[0]}"
REALSELF="$(realpath -ms "$SELF")"


# script is sourced?
if [[ "$0" != "$SELF" ]]; then
    # debug
    set -x
else
    # change directory (must exists) without following symlinks
    cd "$(dirname "$REALSELF")/../foreign" || exit
    _dbg echo "WorkDir: $PWD"
fi


# base dependencies
all_installed() {
    for p in "$@"; do
        if ! command -v "$p" &>/dev/null; then
            return 1
        fi
    done
}

DEPS=(bash  wget  tar  7z  java)
if ! all_installed "${DEPS[@]}"; then  # no output if successful
    command -V "${DEPS[@]}"            # output if failure
    exit 1
fi


get_tools() {
    mkdir -p usr/bin opt
    export PATH="$PWD/usr/bin:$PWD/usr:$PATH"
    
    if ! all_installed jq; then
        wget -qO usr/bin/jq 'https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-linux-amd64'
    fi
    
    if ! all_installed payload-dumper-go; then
        wget -qO tool.tgz 'https://github.com/ssut/payload-dumper-go/releases/download/1.2.2/payload-dumper-go_1.2.2_linux_amd64.tar.gz'
        tar -xzvf tool.tgz -C usr/bin payload-dumper-go
        rm -v tool.tgz
    fi
    
    if ! all_installed dex2jar; then
        wget -qO tool.zip 'https://github.com/pxb1988/dex2jar/releases/download/v2.4/dex-tools-v2.4.zip'
        7z x tool.zip
        rm -v tool.zip
        local dir="dex-tools*"
        local dest='opt/dex-tools'
        mkdir -p "$dest"
        # cp -vrlaPf --remove-destination dex-tools*/* opt
        mv -v "$dir" "$dest"
        ln -s "$dest/d2j-dex2jar.sh" 'usr/bin/dex2jar'
    fi
    
    chmod -R +x usr opt
}


get_lineageos_ota() {
    if [[ -f 'system.img' ]]; then
        return
    fi

    local url
    source <(
        wget -qO- 'https://download.lineageos.org/api/v2/devices/flame/builds' \
        | jq -r '.[0].files[0] | "url=\(.url | @sh)"'
    )
    # fname="${fname%.*}"
    wget --show-progress -qO ota.zip "$url"
    7z e  ota.zip  payload.bin
    rm -v ota.zip
    
    payload-dumper-go  -output .  -partitions system  payload.bin
    rm -v payload.bin
    # mv -v extracted*/system.img .
    # rm -vr extracted*
}


# _get_libs() {
#     mount -t ext4 -o loop system.img img
#     while read -r l; do
#         local fname="$(basename "$l")"
#         cp -v "$l" lib/
#     done < <(
#         find img -type f  -ipath 'img/system/framework/*.jar'
#         find img -type f  -ipath 'img/apex/com.android*/javalib/*.jar'
#     )
#     chown -R 1000:1000 lib
#     chmod -R 777 lib
#     umount img
# }
# export -f _get_libs


get_libs() {
    if [[ -d lib && "$(ls -1 lib | wc -l)" -ge 40 ]]; then
        return
    fi

    rm -rf lib
    7z e -Olib system.img 'system/framework/*.jar' 'apex/com.android*/javalib/*.jar'
    rm -v system.img
    
    cd lib
    for l in *.jar; do
        local fname="$(basename "$l")"
        dex2jar "$l"
        mv -v "${fname%.*}"{-dex2jar,}".${fname##*.}"
    done
    touch converted-dex2jar
    cd -
}


main() {
    if (($#)); then
        for f in "$@"; do
            if [[ "$(type -t "$f")" != function ]]; then
                echo "'$f' is not a function."
                exit 1
            fi
        done

        for f in "$@"; do
            "$f"
        done

    else
        get_tools
        get_lineageos_ota
        get_libs
    fi
    
    echo 'OKAY'
}


main "$@"
