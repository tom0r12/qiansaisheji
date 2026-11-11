"""Package a fixed-run Formality launcher, without shipping private libraries."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT.parent / 'output/eda/run_formality_io_margin.sh'
digest = hashlib.sha256((ROOT/'rtl/qingyu_accel.sv').read_bytes()).hexdigest()
shell = r'''#!/bin/sh
set -eu
desktop="$HOME/Desktop"
fm=/eda/synopsys/fm/fm_2020.09-SP5/bin/fm_shell
synthesis="$desktop/qingyu_io_margin_synth_1793624017_73216"
wrapper="$synthesis/qingyu_sram16.sv"
core="$synthesis/qingyu_accel.sv"
repair1="$desktop/qingyu_io_margin_hold_20261102_205626_74163"
repair2="$desktop/qingyu_io_margin_hold_20261102_205626_74163"
for input in "$repair2/qingyu_accel_mapped.v" "$repair1/repair_ff_125c/hold_fix.svf" "$repair2/repair_ff_m40c/hold_fix.svf"; do
    test -s "$input" || { echo "ERROR: missing repair artifact $input"; exit 1; }
done
test -x "$fm" || { echo "ERROR: Formality executable missing"; exit 1; }
for input in "$core" "$wrapper" "$synthesis/qingyu_accel_mapped.v" "$synthesis/qingyu_accel.svf"; do
    test -s "$input" || { echo "ERROR: missing/empty fixed input: $input"; exit 1; }
done
actual=$(sha256sum "$core" | cut -d ' ' -f 1)
if [ "$actual" != "__CORE_SHA__" ]; then
    echo "ERROR: reference RTL differs from the locally recorded baseline. Do not verify a changed reference."
    echo "Actual reference SHA256: $actual"
    exit 1
fi
out="$desktop/qingyu_formality_io_margin_$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "$out/inputs" "$out/reports"
cp "$core" "$out/inputs/qingyu_accel.sv"
cp "$wrapper" "$out/inputs/qingyu_sram16.sv"
cp "$repair2/qingyu_accel_mapped.v" "$out/inputs/qingyu_accel_mapped.v"
cp "$repair1/repair_ff_125c/hold_fix.svf" "$out/inputs/hold_fix_1.svf"
cp "$repair2/repair_ff_m40c/hold_fix.svf" "$out/inputs/hold_fix_2.svf"
cp "$synthesis/qingyu_accel.svf" "$out/inputs/qingyu_accel.svf"
cd "$out"
sha256sum inputs/* > inputs.sha256
printf '%s\n' "$synthesis" "$repair1" "$repair2" > synthesis_source.txt
sha256sum "$desktop/qingyu_stdcell_db/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_m40c.db" \
    "$desktop/qingyu_sram_corners/RAMSP128X16_ss_0p99v_0p99v_m40c.db" \
    "$desktop/qingyu_sram_corners/RAMSP1024X16_ss_0p99v_0p99v_m40c.db" \
    "$desktop/qingyu_sram_corners/RAMSP4096X16_ss_0p99v_0p99v_m40c.db" > libraries.sha256
cat > run.tcl <<'QINGYU_FORMALITY_TCL_END'
__TCL__
QINGYU_FORMALITY_TCL_END
echo "QINGYU_FORMALITY_DIRECTORY: $out"
echo "Fixed target: $repair2/qingyu_accel_mapped.v"
result=0
"$fm" -f run.tcl > console.log 2>&1 || result=$?
grep '^QINGYU_' console.log || true
if [ -f reports/status.rpt ]; then tail -n 25 reports/status.rpt; fi
if [ "$result" -ne 0 ]; then tail -n 35 console.log; fi
if [ "$result" -eq 0 ]; then
    echo "QINGYU_AUDIT_EXCERPTS (review required)"
    grep -H -E 'No unmatched|No unverified|No aborted|verify points:|User Defined Constants:' reports/unmatched_after_verify.rpt reports/unmatched_black_boxes.rpt reports/unverified.rpt reports/aborted.rpt reports/dont_verify.rpt reports/constants.rpt || true
    grep -H -F '/WORK/qingyu_accel/' reports/black_boxes_reference.rpt reports/black_boxes_implementation.rpt || true
fi
exit "$result"
'''
shell = shell.replace('__CORE_SHA__', digest).replace('__TCL__', (ROOT/'scripts/formality_hold_final.tcl').read_text())
DEST.parent.mkdir(parents=True, exist_ok=True)
DEST.write_text(shell, encoding='utf-8', newline='\n')
print(f'{DEST} ({DEST.stat().st_size} bytes); reference SHA256={digest}')
