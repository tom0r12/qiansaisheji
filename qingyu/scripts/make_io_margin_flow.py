"""Build one uploadable setup-margin + two-corner hold-repair experiment."""
from pathlib import Path
import runpy
import tkinter
ROOT=Path(__file__).resolve().parents[1]
setup=runpy.run_path(str(ROOT/'scripts/make_io_constrained_trial.py'))
hold=runpy.run_path(str(ROOT/'scripts/make_io_hold_trial.py'))
synth=setup['synth']
synth=synth.replace('qingyu_io_synth_[clock seconds]', 'qingyu_io_margin_synth_[clock seconds]')
assert synth.count('set compile_result 0')==1
synth=synth.replace('set compile_result 0', '# Optimization target only: reserve about 267ps beyond the 150MHz period.\ncreate_clock -name core_clk -period 6.4 [get_ports clk]\nset compile_result 0')
marker='if {!$compile_result} {error "compile_ultra failed; inspect compile.log"}'
assert marker in synth
synth=synth.replace(marker,marker+'\n# Restore original evaluation conditions without changing IO assumptions.\ncreate_clock -name core_clk -period 6.666666667 [get_ports clk]')
assert int(tkinter.Tcl().call('info','complete',synth))
stage1=setup['shell'].replace('__SYNTH__',synth).replace('__CHECK__',setup['check'])
stage1=stage1.replace('qingyu_io_synth_run_$(date', 'qingyu_io_margin_run_$(date')
stage2=hold['shell']
source='source_netlist="$HOME/Desktop/qingyu_io_synth_1793623115_63265/qingyu_accel_mapped.v"'
assert source in stage2
stage2=stage2.replace(source,'source_netlist="${QINGYU_HOLD_SOURCE:?Missing new synthesized netlist}"')
stage2=stage2.replace('qingyu_io_hold_trial_$(date','qingyu_io_margin_hold_$(date')
launcher=r'''#!/bin/sh
set -eu
flow="$HOME/Desktop/qingyu_io_margin_flow_$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p "$flow"
cd "$flow"
cat > setup.sh <<'QINGYU_SETUP_STAGE_END'
__SETUP__
QINGYU_SETUP_STAGE_END
cat > hold.sh <<'QINGYU_HOLD_STAGE_END'
__HOLD__
QINGYU_HOLD_STAGE_END
echo "QINGYU_FLOW_DIRECTORY: $flow"
echo "QINGYU: optimize at 6.4ns; evaluate at 6.666666667ns with unchanged engineering assumptions"
if sh setup.sh > setup_stage.log 2>&1; then
    cat setup_stage.log
else
    tail -n 40 setup_stage.log; exit 1
fi
synthesis=$(sed -n 's/^QINGYU_SYNTHESIS_DIRECTORY: //p' setup_stage.log | tail -n 1)
test -s "$synthesis/qingyu_accel_mapped.v" || { echo "ERROR: new netlist missing"; exit 1; }
printf '%s\n' "$synthesis" > synthesis_directory.txt
echo "QINGYU: hold-only repair of the NEW candidate, followed by five-corner rechecks"
if QINGYU_HOLD_SOURCE="$synthesis/qingyu_accel_mapped.v" sh hold.sh > hold_stage.log 2>&1; then
    cat hold_stage.log
else
    tail -n 40 hold_stage.log; exit 1
fi
echo "QINGYU_IO_MARGIN_FLOW_COMPLETE: $flow"
echo "Experiment finished, not a pass declaration. Review final slack, violations and equivalence."
'''
dest=ROOT.parent/'output/eda/run_io_margin_flow.sh'
dest.write_text(launcher.replace('__SETUP__',stage1).replace('__HOLD__',stage2),encoding='utf-8',newline='\n')
print(dest)
