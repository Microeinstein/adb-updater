#!/bin/bash

SELF="$(realpath "${BASH_SOURCE[0]}")"
cd "$(dirname "$SELF")" || exit

export PYTHONPATH="src"
export PYTHONOPTIMIZE=2
MODULE=adb_updater
RUNNER=adb-updater.py
LISTER=dex-lister/build/lister.jar

# reproducible builds
export PYTHONHASHSEED=11893
export SOURCE_DATE_EPOCH="$(git show -s --format=%ct)"  # last commit timestamp


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


with_pyinstaller "$@"
