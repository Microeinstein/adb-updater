#!/bin/bash

SELF="$(realpath -ms "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")" || exit
source './.build_common.sh'


export PYTHONPATH="src"
export PYTHONOPTIMIZE=2
MODULE=adb_updater
RUNNER=adb-updater.py
LISTER=dex-lister/build/lister.jar


config() {
    # reproducible builds
    export PYTHONHASHSEED=11893
    export SOURCE_DATE_EPOCH="$(git show -s --format=%ct)"  # last commit timestamp
}

conda_env() {
    local conda_script="/opt/miniconda/etc/profile.d/conda.sh"
    if [[ -f "$conda_script" ]]; then
        source "$conda_script"
        if [[ -d venv ]]; then
            conda activate ./venv
        else
            conda activate "../../Venv/$(basename "$PWD")"
        fi
    fi
}


with_nuitka() {
    local a=(
        # --standalone
        # --onefile
        # --show-scons
        --include-package="$MODULE"
        --follow-imports
        --clang
        # --enable-plugin=pyside6
        # --include-qt-plugins=qml
        --include-data-files="$LISTER=$(basename "$LISTER")"

        # --mingw64
        # --product-version=1.0.0.0
        # --file-description=blabla
        # --copyright="Microeinstein"
        # --windows-icon-from-ico=...
        # --windows-uac-admin
    )
    python -m nuitka "${a[@]}" "$@" "$RUNNER"
}


with_pyinstaller() {
    local a=(
        # --clean
        --paths src
        --specpath .
        --workpath build
        --distpath dist
        --noconfirm
        --onedir
        # --onefile
        --add-data="$LISTER:."
        --hidden-import "$MODULE"
        --copy-metadata readchar
        # --debug 'all,imports,bootloader,noarchive'
        # --debug all
        --optimize "$PYTHONOPTIMIZE"
        --console
        # --windowed
        # --icon ..

        # --version-file ..
        # --manifest ..
        # --uac-admin
    )

    pyinstaller "${a[@]}" "$@" "$RUNNER"
}


target_local() {
    config
    conda_env
    with_pyinstaller "$@"
}


target_docker() {
    systemctl start docker
    docker buildx du | tail -n4
    local imgname='adb-updater'
    docker --debug build -t "$imgname" .
    local id
    id="$(docker create "$imgname")"
    docker export "$id" \
    | bsdtar -czvf 'dist/adb-updater-ver-linux-x86-64.tgz' --include='dist/*' @-
    docker rm "$id"
}


target_run() {
    conda_env
    python -m "$MODULE" "$@"
}


_command_0=(target_local)
main "$@"
