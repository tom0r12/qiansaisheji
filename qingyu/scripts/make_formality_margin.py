"""Package a fixed-run Formality launcher, without shipping private libraries."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT.parent / 'output/eda/run_formality_margin.sh'
digest = hashlib.sha256((ROOT/'rtl/qingyu_accel.sv').read_bytes()).hexdigest()
shell = r'''#!/bin/sh
set -eu
desktop="$HOME/Desktop"
fm=/eda/synopsys/fm/fm_2020.09-SP5/bin/fm_shell
synthesis="$desktop/qingyu_dc_margin_1793542006_213217"
wrapper="$desktop/qingyu_sram_check_1793542008_213217/qingyu_sram16.sv"
core="$desktop/qingyu_dc_start/rtl/qingyu_accel.sv"
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
out="$desktop/qingyu_formality_margin_$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "$out/inputs" "$out/reports"
cp "$core" "$out/inputs/qingyu_accel.sv"
cp "$wrapper" "$out/inputs/qingyu_sram16.sv"
cp "$synthesis/qingyu_accel_mapped.v" "$out/inputs/qingyu_accel_mapped.v"
cp "$synthesis/qingyu_accel.svf" "$out/inputs/qingyu_accel.svf"
cd "$out"
sha256sum inputs/* > inputs.sha256
printf '%s\n' "$synthesis" > synthesis_source.txt
sha256sum "$desktop/qingyu_stdcell_db/db/sc9mc_logic0040ll_base_rvt_c40_tt_typical_max_1p10v_25c.db" \
    "$desktop/qingyu_sram_db/RAMSP128X16_tt_1p10v_1p10v_25c.db" \
    "$desktop/qingyu_sram_db/RAMSP1024X16_tt_1p10v_1p10v_25c.db" \
    "$desktop/qingyu_sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db" > libraries.sha256
cat > run.tcl <<'QINGYU_FORMALITY_TCL_END'
__TCL__
QINGYU_FORMALITY_TCL_END
echo "QINGYU_FORMALITY_DIRECTORY: $out"
echo "Fixed target: $synthesis"
"$fm" -f run.tcl
'''
shell = shell.replace('__CORE_SHA__', digest).replace('__TCL__', (ROOT/'scripts/formality_margin.tcl').read_text())
DEST.parent.mkdir(parents=True, exist_ok=True)
DEST.write_text(shell, encoding='utf-8', newline='\n')
print(f'{DEST} ({DEST.stat().st_size} bytes); reference SHA256={digest}')
