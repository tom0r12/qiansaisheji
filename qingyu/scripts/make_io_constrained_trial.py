"""Use exactly the sensitivity profile during synthesis and all corner checks."""
from pathlib import Path
import ast
import tkinter
ROOT=Path(__file__).resolve().parents[1]
# Reuse the explicit profile, rather than silently changing the budgets.
tree=ast.parse((ROOT/'scripts/make_io_budget_check.py').read_text())
assumptions=next(ast.literal_eval(n.value) for n in tree.body
                 if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='assumptions' for t in n.targets))
constraints=assumptions+'\n'+(ROOT/'constraints/accelerator_explicit_io.sdc').read_text()
clock='create_clock -name core_clk -period 6.666666667 [get_ports clk]'
synth=(ROOT/'scripts/synth_ss_trial.tcl').read_text()
assert synth.count(clock)==1
synth=synth.replace(clock,constraints)
synth=synth.replace('qingyu_ss_trial_[clock seconds]','qingyu_io_synth_[clock seconds]')
synth=synth.replace('QINGYU_SS_', 'QINGYU_IO_')
synth=synth.replace('IO constraints incomplete','explicit engineering IO assumptions, NOT official contest values')
synth=synth.replace('QINGYU_IO_TRIAL_COMPLETE:', 'QINGYU_IO_SYNTH_COMPLETE:')
# Leave the requested budgets unchanged when reporting; do not relax constraints.
synth+='\nexit\n'
check=(ROOT/'scripts/check_fixed_netlist_corners.tcl').read_text().replace(clock,constraints)
check=check.replace('incomplete IO constraints; not signoff','explicit engineering IO assumptions; not signoff')
for script in [synth,check]:
    assert int(tkinter.Tcl().call('info','complete',script))
shell=r'''#!/bin/sh
set -eu
dc=/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell
out="$HOME/Desktop/qingyu_io_synth_run_$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "$out"
cd "$out"
cat > synth.tcl <<'QINGYU_SYNTH_END'
__SYNTH__
QINGYU_SYNTH_END
cat > check.tcl <<'QINGYU_CHECK_END'
__CHECK__
QINGYU_CHECK_END
echo "QINGYU_RUN_DIRECTORY: $out"
echo "QINGYU: synthesis under unchanged engineering IO assumptions, SS -40C (please wait)"
if "$dc" -f synth.tcl > synthesis_console.log 2>&1; then
    if ! grep -q '^QINGYU_IO_SYNTH_COMPLETE:' synthesis_console.log; then
        tail -n 35 synthesis_console.log; exit 1
    fi
else
    tail -n 35 synthesis_console.log; exit 1
fi
synthesis=$(sed -n 's/^QINGYU_IO_SYNTH_COMPLETE: //p' synthesis_console.log | tail -n 1)
echo "QINGYU_SYNTHESIS_DIRECTORY: $synthesis"
printf '%s\n' "$synthesis" > synthesis_directory.txt
grep '^Total cell area:' "$synthesis/area.rpt"
cp "$synthesis/qingyu_accel_mapped.v" qingyu_accel_mapped.v
sha256sum qingyu_accel_mapped.v > netlist.sha256
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
echo "QINGYU_IO_CONSTRAINED_TRIAL_COMPLETE: $out"
echo "Engineering experiment only. Inspect violations/coverage; new netlist needs equivalence verification."
'''
dest=ROOT.parent/'output/eda/run_io_constrained_trial.sh'
dest.write_text(shell.replace('__SYNTH__',synth).replace('__CHECK__',check),encoding='utf-8',newline='\n')
print(dest)
