"""Package an isolated hold-only ECO experiment plus five-corner rechecks."""
from pathlib import Path
import tkinter
import ast
ROOT = Path(__file__).resolve().parents[1]
check = (ROOT/'scripts/check_fixed_netlist_corners.tcl').read_text()
tree = ast.parse((ROOT/'scripts/make_io_budget_check.py').read_text())
assumptions = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='assumptions' for t in n.targets))
constraints = assumptions + '\n' + (ROOT/'constraints/accelerator_explicit_io.sdc').read_text()
check = check.replace('create_clock -name core_clk -period 6.666666667 [get_ports clk]', constraints)
check = check.replace('incomplete IO constraints; not signoff', 'engineering assumed IO constraints; not signoff')

fix = check.split('redirect -file [file join $out design.rpt]')[0]
fix = fix.replace('set out [file join $env(QINGYU_STA_RUN_ROOT) $corner]', 'set out [file join $env(QINGYU_STA_RUN_ROOT) repair_$corner]')
fix += r'''
set_svf [file join $out hold_fix.svf]
foreach macro {RAMSP128X16 RAMSP1024X16 RAMSP4096X16} {
    set_dont_touch [get_cells -hierarchical -filter "ref_name == $macro"] true
}
redirect -file [file join $out hold_before.rpt] {report_timing -delay_type min -max_paths 100 -significant_digits 6}
# Optimization-only guard band: 50ps total vs 20ps in evaluation.
set_clock_uncertainty -hold 0.05 [get_clocks core_clk]
set_fix_hold [get_clocks core_clk]
set fix_result 0
redirect -file [file join $out compile.log] {set fix_result [compile -incremental_mapping -only_hold_time]}
if {!$fix_result} {error "Hold-only compile failed"}
# Restore the unchanged evaluation profile before reporting.
set_clock_uncertainty -hold 0.02 [get_clocks core_clk]
redirect -file [file join $out hold_after.rpt] {report_timing -delay_type min -max_paths 100 -significant_digits 6}
redirect -file [file join $out area.rpt] {report_area -hierarchy}
redirect -file [file join $out check_design.rpt] {check_design}
change_names -rules verilog -hierarchy
write -format verilog -hierarchy -output [file join $out hold_fixed.v]
write -format ddc -hierarchy -output [file join $out hold_fixed.ddc]
set_svf -off
puts "QINGYU_HOLD_REPAIR_WRITTEN: $out"
exit
'''
for script in (check,fix):
    assert int(tkinter.Tcl().call('info','complete',script))
shell = r'''#!/bin/sh
set -eu
dc=/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell
source_netlist="$HOME/Desktop/qingyu_io_synth_1793623115_63265/qingyu_accel_mapped.v"
out="$HOME/Desktop/qingyu_io_hold_trial_$(date +%Y%m%d_%H%M%S)_$$"
test -s "$source_netlist" || { echo "Missing fixed SS netlist"; exit 1; }
mkdir -p "$out"
cd "$out"
cp "$source_netlist" original_io_netlist.v
cp original_io_netlist.v qingyu_accel_mapped.v
sha256sum original_io_netlist.v > original.sha256
cat > fix.tcl <<'QINGYU_FIX_END'
__FIX__
QINGYU_FIX_END
cat > check.tcl <<'QINGYU_CHECK_END'
__CHECK__
QINGYU_CHECK_END
echo "QINGYU_HOLD_TRIAL_DIRECTORY: $out"
echo "QINGYU: FF hold repair at 125C then -40C; 50ps optimization / 20ps evaluation uncertainty"
for repair_corner in ff_125c ff_m40c; do
    echo "QINGYU_REPAIRING: $repair_corner"
    if QINGYU_STA_CORNER="$repair_corner" QINGYU_STA_RUN_ROOT="$out" "$dc" -f fix.tcl > "$repair_corner.repair.log" 2>&1; then
        if ! grep -q '^QINGYU_HOLD_REPAIR_WRITTEN:' "$repair_corner.repair.log"; then
            tail -n 35 "$repair_corner.repair.log"; exit 1
        fi
    else
        tail -n 35 "$repair_corner.repair.log"; exit 1
    fi
    cp "repair_$repair_corner/hold_fixed.v" qingyu_accel_mapped.v
done
sha256sum qingyu_accel_mapped.v > repaired.sha256
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
grep 'Total cell area:' repair_ff_m40c/area.rpt || true
echo "QINGYU_HOLD_TRIAL_COMPLETE: $out"
echo "Candidate only: inspect all slack values; equivalence and official/platform-derived timing conditions remain required."
'''
shell = shell.replace('__FIX__',fix).replace('__CHECK__',check)
dest=ROOT.parent/'output/eda/run_io_hold_trial.sh'
dest.write_text(shell,encoding='utf-8',newline='\n')
print(dest)
