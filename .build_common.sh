#!/bin/bash

set -euo pipefail


help() {
    cat <<EOF
Usage: $(basename "$SELF")  [OPTIONS]  [ARG.. | TARGET [ARG..] [TARGET [ARG..]]..]

Options:
    --help         Show this help and exit.
    --debug        Print what whould be executed and exit.

Targets:
EOF
    compgen -A function target_ | sed 's|^target_|  |g'
    exit "${1:-0}"
}


parse_args() {
    local i=-1
    local -n cmd='_command_0'

    while (($#)); do
        local arg="$1"; shift
        if [[ "$i" -lt 0 ]]; then
            [[ "$arg" != '--help' ]] || help 0
            [[ "$arg" != '--debug' ]] || { debug=1; continue; }
        fi
        [[ "$arg" != '--'* ]] || { cmd+=( "$arg" ); continue; }

        local t="target_$arg"
        if [[ "$(type -t "$t")" != function ]]; then
            if [[ "$i" -lt 0 ]]; then
                echo "Unknown target: ${arg@Q}"
                help 1
            fi
            cmd+=( "$arg" )
            continue
        fi

        # shellcheck disable=SC2178
        local -n cmd="_command_$((++i))"
        cmd=( "$t" )
    done
}


main() {
    local debug=0
    parse_args "$@"

    if ((debug)); then
        echo "Schedule:"
        for cmd in "${!_command_@}"; do
            local -n cmd_arr="$cmd"
            echo -n '- '
            printf '[%s] ' "${cmd_arr[@]}"
            echo
        done
        exit
    fi

    for cmd in "${!_command_@}"; do
        local -n cmd_arr="$cmd"
        "${cmd_arr[@]}"
    done
}


_no_default() {
    echo 'Default target has not been set.'
    help 2
}

_command_0=(_no_default)  # default target

