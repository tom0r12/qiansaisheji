#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python3 prepare_report.py
mkdir -p build
for pass in 1 2 3; do
  xelatex -interaction=nonstopmode -halt-on-error -output-directory=build main.tex >"build/compile-${pass}.stdout" 2>&1
done
if grep -Eq 'Overfull|Missing character|undefined references|undefined citations|Label\(s\) may have changed' build/main.log; then
  echo 'Review build/main.log before publishing.' >&2
  exit 1
fi
cp build/main.pdf qingyu_technical_report.pdf
echo 'Built qingyu_technical_report.pdf; review every page after layout edits.'
