#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec python3 run_vendor.py --tasks 12 --saif --compile-timeout 1800 --task-timeout 1800 --saif-timeout 1800 "$@"
