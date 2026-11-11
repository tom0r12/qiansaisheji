#!/bin/sh
# Run with `sh scripts/server_probe.sh` in the contest VNC terminal.
# Inspect local paths only; do not connect, install, change passwords or run jobs.
set -u

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 1
mkdir -p "$project_root/reports" || exit 1
report="$project_root/reports/server_probe_$(date -u +%Y%m%dT%H%M%SZ)_$$.txt"
umask 077

{
    printf 'Qingyu contest server inspection\n'
    printf 'UTC: '; date -u '+%Y-%m-%d %H:%M:%S'
    printf 'System: '; uname -srm
    printf 'Project: %s\n' "$project_root"
    printf '\nTool paths (presence does not prove a working license):\n'
    for tool in dc_shell pt_shell fm_shell lc_shell vcs verdi iverilog verilator python3; do
        if tool_path=$(command -v "$tool" 2>/dev/null); then
            printf '%s: %s\n' "$tool" "$tool_path"
        else
            printf '%s: NOT FOUND in inherited PATH\n' "$tool"
        fi
    done
    printf '\nEDA installation directory names, at most two levels:\n'
    if [ -d /eda ]; then
        find /eda -maxdepth 2 -type d -print 2>/dev/null | awk 'NR <= 100 { print }'
    else
        printf '/eda is not visible\n'
    fi
    printf '\nLibrary/model candidates, depth <= 6, first 100 per root:\n'
    printf 'Candidates require manual checking of macro ports and library corners.\n'
    if [ "$#" -eq 0 ]; then
        set -- "${HOME:-$project_root}"
    fi
    for scan_root in "$@"; do
        printf '\nRoot: %s\n' "$scan_root"
        if [ -d "$scan_root" ]; then
            find "$scan_root" -maxdepth 6 -type f \( -name '*.db' -o -name '*.lib' -o -name '*.lib.gz' -o -iname '*sram*.v' -o -iname '*sram*.sv' \) -print 2>/dev/null | awk 'NR <= 100 { print }'
        else
            printf 'Not an accessible directory\n'
        fi
    done
    printf '\nNo synthesis, license test or acceptance assessment was performed.\n'
} > "$report"

cat "$report"
printf '\nLocal report saved: %s\n' "$report"
