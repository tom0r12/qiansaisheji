"""Build a fixed-netlist sensitivity check with explicit NON-OFFICIAL assumptions."""
from pathlib import Path
import tkinter
ROOT = Path(__file__).resolve().parents[1]
check = (ROOT/'scripts/check_fixed_netlist_corners.tcl').read_text()
assumptions = '''# ENGINEERING SENSITIVITY PROFILE ONLY, NOT ORGANIZER VALUES.
set CLOCK_PERIOD_NS 6.666666667
set INPUT_DELAY_MIN_NS 0.0
set INPUT_DELAY_MAX_NS 1.0
set OUTPUT_DELAY_MIN_NS -0.1
set OUTPUT_DELAY_MAX_NS 1.0
set SETUP_UNCERTAINTY_NS 0.1
set HOLD_UNCERTAINTY_NS 0.02
set INPUT_SLEW_NS 0.1
set CLOCK_SLEW_NS 0.1
set OUTPUT_LOAD_PF 0.02
'''
sdc = (ROOT/'constraints/accelerator_explicit_io.sdc').read_text()
old_clock = 'create_clock -name core_clk -period 6.666666667 [get_ports clk]'
assert check.count(old_clock) == 1
check = check.replace(old_clock, assumptions + '\n' + sdc + '\nwrite_sdc [file join $out engineering_assumptions.sdc]')
check = check.replace('# Internal path engineering check only: IO delays/loads/uncertainty pending.', '# All boundary delays below are explicit engineering assumptions, NOT official values.')
check = check.replace('fixed netlist, Small wire-load estimate, ideal clock, incomplete IO constraints; not signoff', 'fixed netlist, Small wire-load estimate, assumed IO budgets/slew/load/clock uncertainty; not signoff')
assert int(tkinter.Tcl().call('info','complete',check))
shell = r'''#!/bin/sh
set -eu
dc=/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell
source_netlist="$HOME/Desktop/qingyu_hold_refine_20261102_172959_284204/qingyu_accel_mapped.v"
test -x "$dc" || { echo "ERROR: DC missing"; exit 1; }
test -s "$source_netlist" || { echo "ERROR: fixed repaired netlist missing"; exit 1; }
out="$HOME/Desktop/qingyu_io_budget_check_$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "$out"
cd "$out"
cp "$source_netlist" qingyu_accel_mapped.v
sha256sum qingyu_accel_mapped.v > netlist.sha256
cat > assumptions.txt <<'QINGYU_ASSUMPTIONS_END'
ENGINEERING SENSITIVITY CHECK -- NOT OFFICIAL CONTEST CONDITIONS
Netlist: qingyu_hold_refine_20261102_172959_284204/qingyu_accel_mapped.v
Clock period 6.666666667 ns, ideal clock network, Small wire-load model.
Uniform non-clock inputs (including synchronous reset): min 0, max 1 ns.
Outputs: min -0.1, max 1 ns; load 0.02 pF per output bit.
Setup uncertainty 0.1 ns; hold uncertainty 0.02 ns.
Input and clock transition 0.1 ns.
These exploratory budgets are not extracted from the E203 bus or PLL specifications.
No false paths, multicycle paths, compile or netlist changes are applied.
Even positive slack does not establish platform timing compatibility or signoff.
QINGYU_ASSUMPTIONS_END
cat > check.tcl <<'QINGYU_CHECK_END'
__CHECK__
QINGYU_CHECK_END
echo "QINGYU_IO_CHECK_DIRECTORY: $out"
echo "ENGINEERING ASSUMPTIONS ONLY: IO max=1ns; setup/hold uncertainty=0.1/0.02ns; load=0.02pF"
for corner in tt_25c ss_125c ss_m40c ff_125c ff_m40c; do
    echo "QINGYU_RUNNING: $corner"
    mkdir -p "$corner"
    if QINGYU_STA_CORNER="$corner" QINGYU_STA_RUN_ROOT="$out" "$dc" -f check.tcl > "$corner/run.log" 2>&1; then
        if ! grep -q "^QINGYU_CORNER_COMPLETE: $corner" "$corner/run.log"; then
            tail -n 35 "$corner/run.log"; exit 1
        fi
        grep '^QINGYU_CORNER_RESULT:' "$corner/run.log"
    else
        tail -n 35 "$corner/run.log"; exit 1
    fi
done
echo "QINGYU_IO_BUDGET_CHECK_COMPLETE: $out"
echo "Review check_timing and violations reports as well as path slack; this is not official acceptance."
'''
dest=ROOT.parent/'output/eda/run_io_budget_check.sh'
dest.write_text(shell.replace('__CHECK__',check),encoding='utf-8',newline='\n')
print(dest)
