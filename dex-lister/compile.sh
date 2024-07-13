#!/bin/bash

set -euo pipefail
# set -x

unset _JAVA_OPTIONS  # too much output for nothing
clear


# Project config & paths

JVM_VER=1.8
SRC_VER=1.8
MIN_API=29  # int
SDK_VER=34  # int

DIR_PROJ="$(dirname "$(realpath -ms "${BASH_SOURCE[0]}" )" )"
DIR_LIB="$DIR_PROJ/lib"
DIR_BUILD="$(realpath -ms "${DIR_BUILD:-"${DIR_PROJ}/build"}" )"
DIR_CLASSES="$DIR_BUILD/classes"
DIR_GEN="$DIR_BUILD/gen"
PROJ_BIN=lister.jar
PROJ_PKG=net.micro.adb.Lister
PROJ_MAIN="$PROJ_PKG.Lister"


# SDK paths

SDK="${ANDROID_HOME:-/opt/android-sdk}"
SDK_BUILD="$SDK/build-tools/${SDK_VER}.0.0"
SDK_PLAT="$SDK/platforms/android-${SDK_VER}"
SDK_TOOLS="$SDK/platforms-tools"

LIB_ANDROID="$SDK_PLAT/android.jar"
LIB_LAMBDA="$SDK_BUILD/core-lambda-stubs.jar"
LIB_FRAMEWORK="$DIR_LIB/framework.jar"
LIB_CORE_OJ="$DIR_LIB/core-oj.jar"


cat <<EOF
Build dir   : $DIR_BUILD
Platform    : $SDK_PLAT
Build tools : $SDK_BUILD
EOF


# Basic checks

if [[ ! -d "$SDK_BUILD" || ! -d "$SDK_PLAT" ]]; then
    echo "Android SDK not found."
    exit 1
fi

export PATH="$SDK_BUILD:$SDK_TOOLS:$PATH"


check_bin_deps() {
    local miss=()
    for d in "$@"; do
        if ! command -V "$d" &>/dev/null; then
            miss+=("$d")
        fi
    done
    if [[ -v miss[0] ]]; then
        echo "Some tools are missing: ${miss[*]}"
        exit 1
    fi
}

# cannot check here if a compilation step is disabled
# check_bin_deps  adb  dex2jar  d8  javac


# Build functions

title() {
    printf '\n%b\n' "\e[1m$*\e[0m"
} >&2

run() {
    {
        echo $'\e[96m'"@ $PWD"
        echo -n '> '
        printf '[%s] ' "$@"
        echo $'\e[0m'
    } >&2
    "$@"
}


reset() {
    title 'Resetting...'
    rm -rf "$DIR_CLASSES" "$DIR_GEN" "${DIR_BUILD:?}/$PROJ_BIN"
    mkdir -p "$DIR_LIB" "$DIR_CLASSES" "$DIR_GEN"
}


get_phone_lib() (
    local lib="${1:?Missing library remote path.}"
    local nam
    nam="$(basename "$lib")"
    cd "$DIR_LIB"
    if [[ -f "$nam" ]]; then
        return
    fi
    title "Getting $nam from phone..."
    check_bin_deps  adb dex2jar
    
    adb pull "$lib" .
    dex2jar "$nam"
    mv "$(basename -s .jar "$nam")-dex2jar.jar" "$nam"
)


generate_buildconfig() (
    title "Generating build config..."
    
    local pkg2dir="${PROJ_PKG//.//}"
    mkdir -p "$DIR_GEN/$pkg2dir"
    
    cat <<EOF >"$DIR_GEN/$pkg2dir/BuildConfig.java"
package ${PROJ_PKG};

public final class BuildConfig {
    // public static final boolean DEBUG = \$PROJ_DEBUG;
    // public static final String VERSION_NAME = "\$PROJ_VERSION_NAME";
    public static final int SDK_VER = $SDK_VER;
    public static final int MIN_API = $MIN_API;
}
EOF
)


find_sources() {
    title "Finding sources..."
    
    local common=(
        -type f
        -not -name '.*'
        -and -not  -iname "$(basename "$LIB_FRAMEWORK")"
        -and -not  -iname "$(basename "$LIB_CORE_OJ")"
        -and  -iname
    )
    
    mapfile -t src < <(
        find "$DIR_PROJ/src"  "${common[@]}"  '*.java'
    )
    
    mapfile -t libs < <(
        find "$DIR_LIB"  "${common[@]}"  '*.jar'  
    )
}


compile_aidl() (
    title "Generating java from aidl..."
    if [[ ! -d "$DIR_PROJ/src/aidl" ]]; then
        echo "(none)"
        return
    fi
    check_bin_deps  aidl
    cd "$DIR_PROJ/src/aidl"
    
    local dest_dir
    while read -r f; do
        dest_dir="$DIR_GEN/$(dirname "$f")"
        mkdir -p "$dest_dir"
        run aidl -o"$dest_dir" "$f"
    done < <(
        find .  -type f  -not -name '.*'  -and  -iname '*.aidl'
    )
)


compile_java() (
    title "Compiling java sources..."
    check_bin_deps  javac
    cd "$DIR_PROJ/src"
    mkdir -p "$DIR_CLASSES"
    
    local IFS=':'
    local classpath=(
        "${libs[@]}"
        "$DIR_GEN"
        "$LIB_LAMBDA"
        "$LIB_CORE_OJ"
        "$LIB_FRAMEWORK"
    )
    
    # shellcheck disable=SC2030
    local a=(
        -Xlint:-options
        -Xlint:-deprecation
        -bootclasspath "$LIB_ANDROID"
        -classpath "${classpath[*]}"
        -source "$SRC_VER"
        -target "$JVM_VER"
        -d "$DIR_CLASSES"
    )
    
    run javac "${a[@]}" "${src[@]}"
)


_compile_dex_dx() (
    check_bin_deps  dx  jar
    local dex='classes.dex'
    
    # shellcheck disable=SC2031
    run dx  --dex  --min-sdk-version "$MIN_API" \
            --output "$DIR_BUILD/$dex"  "${dexable[@]}"

    cd "$DIR_BUILD"
    run jar -cvf "$PROJ_BIN" "$dex"
    rm -f "$dex"
)

_compile_dex_d8() (
    check_bin_deps  d8
    
    # shellcheck disable=SC2031
    run d8  --classpath "$LIB_ANDROID"  --min-api "$MIN_API" \
            --output "$DIR_BUILD/$PROJ_BIN"  "${dexable[@]}"
)

compile_dex() (
    title "Dexing..."
    cd "$DIR_CLASSES"
    
    local dexable=()
    mapfile -t dexable < <(find .  -type f  -not -name '.*'  -and  -iname '*.class')
    dexable+=("${libs[@]}")
    
    if (( SDK_VER < 31 )); then
        _compile_dex_dx
    else
        _compile_dex_d8
    fi
)


add_resources() (
    title "Adding extra resources..."
    check_bin_deps  zip
    cd "$DIR_PROJ/src"
    
    run zip -ru "$DIR_BUILD/$PROJ_BIN"  'AndroidManifest.xml'
)


adb_execute() {
    title 'Executing on phone...'
    check_bin_deps  adb
    
    local tmp='/data/local/tmp'
    
    run adb push "$DIR_BUILD/$PROJ_BIN" "$tmp"

    # will give pre-warmed VM from the Zygote process, but hides errors  
    run adb exec-out "
        export CLASSPATH=${tmp@Q}/${PROJ_BIN@Q}
        app_process / ${PROJ_MAIN@Q}
    " | less

    # can't load native libraries, but shows errors
    # run adb shell "
    #     export LD_LIBRARY_PATH=/apex/com.android.runtime/lib64:/system/lib64
    #     dalvikvm -cp ${tmp@Q}/${PROJ_BIN@Q}  ${PROJ_MAIN@Q}
    # "
}


main() {
    if (($#)); then
        "$@"
        return
    fi
    
    local src=()
    local libs=()
    
    reset
    # BOOTCLASSPATH
    # SYSTEMSERVERCLASSPATH
    get_phone_lib '/system/framework/framework.jar'
    get_phone_lib '/apex/com.android.runtime/javalib/core-oj.jar'
    generate_buildconfig
    find_sources
    compile_aidl
    compile_java
    compile_dex
    add_resources
    
    title "Server generated in $DIR_BUILD/$PROJ_BIN"
    # adb_execute
}

main "$@"
