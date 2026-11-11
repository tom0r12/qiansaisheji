"""Build single uploadable launcher for independent fixed-netlist corner checks."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
script = r'''#!/bin/sh
set -eu
dc=/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell
source_netlist="$HOME/Desktop/qingyu_dc_margin_1793542006_213217/qingyu_accel_mapped.v"
test -x "$dc" || { echo "ERROR: DC executable missing"; exit 1; }
test -s "$source_netlist" || { echo "ERROR: fixed netlist missing"; exit 1; }
out="$HOME/Desktop/qingyu_fixed_corner_check_$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "$out"
cp "$source_netlist" "$out/qingyu_accel_mapped.v"
cd "$out"
sha256sum qingyu_accel_mapped.v > netlist.sha256
cat > check.tcl <<'QINGYU_CORNER_TCL_END'
__TCL__
QINGYU_CORNER_TCL_END
echo "QINGYU_RUN_DIRECTORY: $out"
for corner in tt_25c ss_125c ss_m40c ff_125c ff_m40c; do
    echo "QINGYU_RUNNING: $corner (please wait)"
    mkdir -p "$out/$corner"
    if QINGYU_STA_CORNER="$corner" QINGYU_STA_RUN_ROOT="$out" "$dc" -f "$out/check.tcl" > "$out/$corner/run.log" 2>&1; then
        if grep -q "^QINGYU_CORNER_COMPLETE: $corner" "$out/$corner/run.log"; then
            grep '^QINGYU_CORNER_RESULT:' "$out/$corner/run.log"
        else
            echo "QINGYU_CORNER_ERROR: $corner; missing completion marker"
            tail -n 35 "$out/$corner/run.log"
            exit 1
        fi
    else
        echo "QINGYU_CORNER_ERROR: $corner"
        tail -n 35 "$out/$corner/run.log"
        exit 1
    fi
done
echo "QINGYU_FIXED_CORNER_CHECK_COMPLETE: $out"
echo "Internal path coverage only; IO constraints incomplete. Negative slack requires attention."
'''
script = script.replace('__TCL__', (ROOT/'scripts/check_fixed_netlist_corners.tcl').read_text())
out = ROOT.parent/'output/eda/run_fixed_corner_check.sh'
out.write_text(script, encoding='utf-8', newline='\n')
print(out)
