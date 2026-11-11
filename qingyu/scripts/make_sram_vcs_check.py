"""Generate an uploadable shell script; vendor models remain on the server."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT.parent / 'output/eda/run_sram_vcs.sh'
parts = [r'''#!/bin/sh
set -eu
vcs=/eda/synopsys/vcs/vcs_2020.03-SP2-6/bin/vcs
root=/storage1/admin_public_dir/SRAM_Lib_2025
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out="$base/qingyu_sram_vcs_$(date +%Y%m%d_%H%M%S)_$$"
test -x "$vcs" || { echo "ERROR: VCS executable missing"; exit 1; }
for macro in RAMSP128X16 RAMSP1024X16 RAMSP4096X16; do
    test -r "$root/$macro/verilog/$macro.v" || { echo "ERROR: missing model $macro"; exit 1; }
done
mkdir -p "$out"
cd "$out"
echo "QINGYU_RUN_DIRECTORY: $out"
''']
for source, name in [('rtl/asic/qingyu_sram16.sv','qingyu_sram16.sv'),
                     ('rtl/qingyu_accel.sv','qingyu_accel.sv'),
                     ('tb/tb_qingyu_accel.sv','tb_qingyu_accel.sv')]:
    data = (ROOT / source).read_text(encoding='utf-8')
    marker = 'QINGYU_EOF_' + hashlib.sha256(data.encode()).hexdigest()[:16]
    parts.append(f"cat > '{name}' <<'{marker}'\n{data.rstrip()}\n{marker}\n")
parts.append(r'''
# Vendor functional mode. The testbench clock is 10ns (100MHz).
# This run is NOT a 150MHz timing check, SDF simulation or power measurement.
echo "QINGYU: compiling with vendor SRAM models (ARM_UD_MODEL functional mode)"
"$vcs" -full64 -sverilog -timescale=1ns/1ps +define+ARM_UD_MODEL \
    -top tb_qingyu_accel \
    "$root/RAMSP128X16/verilog/RAMSP128X16.v" \
    "$root/RAMSP1024X16/verilog/RAMSP1024X16.v" \
    "$root/RAMSP4096X16/verilog/RAMSP4096X16.v" \
    qingyu_sram16.sv qingyu_accel.sv tb_qingyu_accel.sv \
    -o simv -l compile.log
echo "QINGYU: running directed accelerator tests"
./simv -l simulation.log
if grep -q '^PASS qingyu_accel directed tests: 58176 bus checks, 1980 output checks' simulation.log; then
    echo "QINGYU_VENDOR_SRAM_FUNCTIONAL_PASS"
    echo "LOG_DIRECTORY: $out"
else
    echo "QINGYU_VENDOR_SRAM_FUNCTIONAL_NOT_PASSED: inspect $out/simulation.log"
    exit 1
fi
''')
DEST.parent.mkdir(parents=True, exist_ok=True)
DEST.write_text(''.join(parts), encoding='utf-8', newline='\n')
print(f'{DEST} ({DEST.stat().st_size} bytes)')
