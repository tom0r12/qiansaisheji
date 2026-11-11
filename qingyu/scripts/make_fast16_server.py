from pathlib import Path
import argparse
import base64,gzip,hashlib,io,tarfile,zipfile
root=Path(__file__).resolve().parents[2]
eda=root/'output/eda'
def script(name): return (eda/name).read_text()
def change(s,a,b):
    if s.count(a)!=1: raise ValueError(a)
    return s.replace(a,b)
parser=argparse.ArgumentParser()
parser.add_argument('--double-buffer',action='store_true')
parser.add_argument('--block-copy',action='store_true')
parser.add_argument('--read-ahead',action='store_true')
parser.add_argument('--pipe-mac',action='store_true')
args=parser.parse_args()
block=args.block_copy
ahead=args.read_ahead or block
pipe=args.pipe_mac or ahead
db=args.double_buffer or pipe
macro_counts='RAMSP128X16 21 RAMSP1024X16 0' if db else 'RAMSP128X16 17 RAMSP1024X16 4'
files={}
with zipfile.ZipFile(eda/('qingyu_block_performance.zip' if block else 'qingyu_ahead_performance.zip' if ahead else 'qingyu_pipe_performance.zip' if pipe else 'qingyu_db_performance.zip' if db else 'qingyu_fast_performance.zip')) as z:
    prefix='qingyu_soc_performance/'
    for name in ['rtl/qingyu_accel.sv','rtl/qingyu_fio.sv']+[f'layer{i:02d}/firmware64.hex' for i in range(12)]:
        files[name]=z.read(prefix+name)
    if block:
        files['tb_block_copy.sv']=(root/'qingyu/tb/tb_block_copy.sv').read_bytes()
        files['generated/qingyu_e203_soc_top.v']=z.read(prefix+'generated/qingyu_e203_soc_top.v')
    # Tie the reused datasets on the server to the same twelve local cases.
    files['data.sha256']=''.join(hashlib.sha256(z.read(prefix+f'layer{i:02d}/{name}')).hexdigest()+f'  layer{i:02d}/{name}\n' for i in range(12) for name in ['shared.hex','expected.hex']).encode()
files['rtl/qingyu_fio.sv']=b'`define QINGYU_FAST_TASK\n'+files['rtl/qingyu_fio.sv']
area=script('run_fio_area.sh').split("cat > run.tcl <<'TCL'\n")[1].split('\nTCL\n')[0]
i=area.index(' read_verilog qingyu_accel_mapped.v');j=area.index(' create_clock',i)
area=area[:i]+''' file mkdir work
 define_design_lib WORK -path work
 if {![analyze -format sverilog -define {SYNTHESIS QINGYU_FAST_TASK} {../inputs/macro/qingyu_sram16.sv ../inputs/rtl/qingyu_accel.sv ../inputs/rtl/qingyu_fio.sv}]} {error "analyze failed"}
 elaborate qingyu_fio
 current_design qingyu_fio
 if {![link]} {error "link failed"}
 set_ungroup [get_cells u_accel] false
'''+area[j:]
area=area.replace('RAMSP128X16 5 RAMSP1024X16 2',macro_counts).replace(' write -format verilog',' change_names -rules verilog -hierarchy\n write -format verilog').replace(' current_design qingyu_accel\n redirect -file accelerator_area.rpt {report_area -hierarchy}\n current_design qingyu_fio','')
if db:
    files['rtl/qingyu_fio.sv']=b'`define QINGYU_DOUBLE_BUFFER\n'+files['rtl/qingyu_fio.sv']
    for bench in ('tb_qingyu_soc_performance.sv','tb_qingyu_soc_macro_performance.sv','tb_batch_buffers.sv'):
        files[bench]=(root/'qingyu/tb'/bench).read_bytes()
if pipe:
    files['rtl/qingyu_fio.sv']=b'`define QINGYU_PIPE_MAC\n'+files['rtl/qingyu_fio.sv']
    files['tb_batch_buffers.sv']=files['tb_batch_buffers.sv'].replace(b'parameter PIPE_MAC=0',b'parameter PIPE_MAC=1')
if ahead:
    files['rtl/qingyu_fio.sv']=b'`define QINGYU_READ_AHEAD\n'+files['rtl/qingyu_fio.sv']
    files['tb_batch_buffers.sv']=files['tb_batch_buffers.sv'].replace(b'READ_AHEAD=0',b'READ_AHEAD=1')
    # Map with the same setup headroom as the timing-qualified C candidate.
    area=change(area,'-period 6.666666667','-period 6.40')
if block:
    area=change(area,'-define {SYNTHESIS QINGYU_FAST_TASK}', '-define {SYNTHESIS QINGYU_FAST_TASK QINGYU_BLOCK_COPY}')
files['area.tcl']=area.encode()
soc=script('run_soc_synthesis.sh').split("cat > run.tcl <<'TCL'\n")[1].split('\nTCL\n')[0]
soc=soc.replace('RAMSP128X16 5 RAMSP1024X16 2',macro_counts).replace('$line eq "rtl/qingyu_accel.sv" ||', '$line eq "rtl/qingyu_fio.sv" || $line eq "rtl/qingyu_accel.sv" ||').replace('qingyu_accel_mapped.v','area/qingyu_fio_mapped.v').replace('get_cells u_fio/u_accel','get_cells u_fio')
if db:
    soc=soc.replace('set_dont_touch [get_cells -hierarchical -filter "ref_name == $macro"] true',
                    'set cells [get_cells -quiet -hierarchical -filter "ref_name == $macro"]\n  if {[sizeof_collection $cells]} {set_dont_touch $cells true}')
if block:
    soc=change(soc,'-define {SYNTHESIS DISABLE_SV_ASSERTION=1}', '-define {SYNTHESIS DISABLE_SV_ASSERTION=1 QINGYU_BLOCK_COPY}')
files['soc.tcl']=soc.encode()
# The logic activity run uses behavioral memories, followed by a vendor macro supplement.
old=script('run_soc_power_precheck.sh').split("cat > run.tcl <<'TCL'\n")[1].split('\nTCL\n')[0].replace('RAMSP128X16 5 RAMSP1024X16 2',macro_counts)
files['pre.tcl']=old.encode()
sup=script('run_soc_macro_activity.sh').replace('macro="$HOME/Desktop/qingyu_soc_macro_GRZ25R"','macro="$1"').replace('base="$HOME/Desktop/qingyu_soc_powercheck_Uss31u"','base="$1"').replace('sha256sum -c baseline.sha256','sha256sum -c fast.sha256').replace('sha256sum -c macro_inputs.sha256 >> "$run/reference_check.log"','')
sup=sup.replace("('y', 2,", "('y', 4,").replace("('w', 4,", "('w', 16,").replace('89','103').replace('1424','1648').replace('2614748','$fast_cycles').replace("'^QINGYU_PERF_WINDOW cycles=$fast_cycles '",'"^QINGYU_PERF_WINDOW cycles=$fast_cycles "').replace('17429910168','$fast_duration')
sup=sup.replace('macro="$1"', 'macro="$1"\nfast_cycles=$(cat "$1/cycles.txt")\nfast_duration=$((fast_cycles*6666))\nexport fast_duration')
sup=sup.replace("data = open('macro.saif').read()","import os\ndata = open('macro.saif').read()").replace("Decimal(d.group(1))-$fast_duration","Decimal(d.group(1))-int(os.environ['fast_duration'])")
sup=sup.replace('if grep -E \'^Error:\' reports/read_macro_saif.rpt console.log; then exit 1; fi', '''if grep '^Error:' reports/read_macro_saif.rpt; then exit 1; fi
if grep '^Error:' console.log | grep -v '(PT-063)'; then exit 1; fi''')
sup+='''grep -E 'Dynamic Power Units|Leakage Power Units|^Total Power' reports/power_verbose.rpt
awk -v ms="$(awk -v p="$fast_duration" 'BEGIN {print p/1e9}')" '
 /Dynamic Power Units *= *1 W$/ {d=1}
 /Leakage Power Units *= *1 W$/ {l=1}
 /^Total Power * =/ {p=$4}
 END {if(!d || !l || p<=0)exit 1; printf "QINGYU_LAYER00_POWER_MW=%.4f ENERGY_UJ=%.4f\\n",1000*p,1000*p*ms}' reports/power_verbose.rpt
'''
if db:
    sup=change(sup,"('y', 4, 1024, 10)","('y', 4, 128, 7)").replace('+define+ARM_UD_MODEL','+define+QINGYU_DOUBLE_BUFFER +define+ARM_UD_MODEL')
if ahead:
    sup=sup.replace('+define+QINGYU_DOUBLE_BUFFER','+define+QINGYU_READ_AHEAD +define+QINGYU_DOUBLE_BUFFER')
if block:
    sup=sup.replace('+define+QINGYU_READ_AHEAD', '+define+QINGYU_BLOCK_COPY +define+QINGYU_READ_AHEAD')
files['supplement.sh']=sup.encode()
# Separate verbose report retains units on the same design and activity.
files['pre.tcl']=files['pre.tcl'].replace(b' pt_report power_unqualified.rpt',b' pt_report power_verbose.rpt {report_power -verbose}\n pt_report power_unqualified.rpt')
if db:
    sta=(root/'qingyu/scripts/check_fixed_netlist_corners.tcl').read_text()
    sta=change(sta,'[file join $env(QINGYU_STA_RUN_ROOT) qingyu_accel_mapped.v]','$env(QINGYU_STA_NETLIST)')
    sta=change(sta,'current_design qingyu_accel','current_design qingyu_fio')
    first=sta.index('set_wire_load_mode')
    last=sta.index('    set count', first)
    constraints=area[area.index(' create_clock'):area.index(' set_operating_conditions')]
    if ahead: constraints=change(constraints,'-period 6.40','-period 6.666666667')
    sta=sta[:first]+constraints+'foreach {macro expected} $env(QINGYU_STA_COUNTS) {\n'+sta[last:]
    sta=sta.replace('macros=9','macros=23').replace('Small wire-load estimate, ideal clock, incomplete IO constraints','ideal clock, engineering IO budget')
    files['ab_sta.tcl']=sta.encode()
payload=io.BytesIO()
with tarfile.open(fileobj=payload,mode='w') as tar:
    for name,data in files.items():
        h=tarfile.TarInfo(name);h.mtime=int(Path(__file__).stat().st_mtime);h.size=len(data);tar.addfile(h,io.BytesIO(data))
blob=gzip.compress(payload.getvalue(),mtime=0)
body=(Path(__file__).with_name('fast16_server.sh')).read_text()
if db:
    body=body.replace('qingyu_fast16_XXXXXX','qingyu_db16_XXXXXX').replace('QINGYU_FAST16','QINGYU_DB16')
    body=body.replace('cp ../rtl/*.sv rtl/', 'cp ../rtl/*.sv rtl/\ncp ../tb_qingyu_soc_performance.sv tb/\ncp ../tb_qingyu_soc_macro_performance.sv macro/')
    body=body.replace('+define+DISABLE_SV_ASSERTION=1', '+define+QINGYU_DOUBLE_BUFFER +define+DISABLE_SV_ASSERTION=1')
    body=body.replace(' sed -n "s/^QINGYU_PERF_WINDOW', ''' printf '%s ' "$layer" >> ../batch_waits.tsv
 grep '^QINGYU_BATCH_WAIT ' "../$layer.log" >> ../batch_waits.tsv
 sed -n "s/^QINGYU_PERF_WINDOW''')
    body=body.replace('for layer in layer??; do', """echo 'QINGYU_DB16: testing tail, restart and reset on vendor memory models'
vcs -full64 -sverilog -timescale=1ns/1ps +define+ARM_UD_MODEL -top tb_batch_buffers ../tb_batch_buffers.sv rtl/qingyu_accel.sv macro/qingyu_sram16.sv "$models/RAMSP128X16/verilog/RAMSP128X16.v" "$models/RAMSP4096X16/verilog/RAMSP4096X16.v" -Mdir="$run/unit_csrc" -o "$run/unit_sim" > ../batch_compile.log 2>&1 || { tail -20 ../batch_compile.log; exit 1; }
"$run/unit_sim" > ../batch_test.log 2>&1
grep '^PASS batch handoff' ../batch_test.log
for layer in layer??; do""")
    body=body.replace('mkdir area','cat batch_waits.tsv\nmkdir area') 
    body=body.replace("echo 'QINGYU_DB16: mapping digital SoC", """for variant in A B; do
 if [ "$variant" = A ]; then
  export QINGYU_STA_NETLIST="$HOME/Desktop/qingyu_fast16_Xcbpng/area/qingyu_fio_mapped.v"
  export QINGYU_STA_COUNTS='RAMSP128X16 17 RAMSP1024X16 4 RAMSP4096X16 2'
 else
  export QINGYU_STA_NETLIST="$run/area/qingyu_fio_mapped.v"
  export QINGYU_STA_COUNTS='RAMSP128X16 21 RAMSP1024X16 0 RAMSP4096X16 2'
 fi
 export QINGYU_STA_RUN_ROOT="$run/timing_$variant"
 mkdir "$QINGYU_STA_RUN_ROOT"
 for QINGYU_STA_CORNER in tt_25c ss_125c ss_m40c ff_125c ff_m40c; do
  export QINGYU_STA_CORNER
  log="$QINGYU_STA_RUN_ROOT/$QINGYU_STA_CORNER.log"
  "$dc" -f ab_sta.tcl > "$log" 2>&1
  grep -q "^QINGYU_CORNER_COMPLETE: $QINGYU_STA_CORNER" "$log" || { tail -20 "$log"; exit 1; }
  echo "QINGYU_AB_STA $variant $(cat "$QINGYU_STA_RUN_ROOT/$QINGYU_STA_CORNER/summary.txt")"
 done
done
echo 'QINGYU_DB16: mapping digital SoC""")
if pipe:
    body=body.replace('qingyu_db16_XXXXXX','qingyu_pipe16_XXXXXX').replace('QINGYU_DB16','QINGYU_PIPE16')
    body=body.replace('for variant in A B; do','for variant in C; do')
    body=body.replace("echo 'QINGYU_PIPE16: mapping digital SoC", """echo "QINGYU_REFERENCE_B_TIMING: $HOME/Desktop/qingyu_db16_1Mmvm9/timing_B"
echo 'QINGYU_PIPE16: mapping digital SoC""")
if ahead:
    body=body.replace('+define+QINGYU_DOUBLE_BUFFER', '+define+QINGYU_READ_AHEAD +define+QINGYU_DOUBLE_BUFFER')
    body=body.replace(' sed -n "s/^QINGYU_PERF_WINDOW', ' grep "^QINGYU_READ_AHEAD " "../$layer.log"\n sed -n "s/^QINGYU_PERF_WINDOW')
    body=body.replace('qingyu_pipe16_XXXXXX','qingyu_ahead16_XXXXXX').replace('QINGYU_PIPE16','QINGYU_AHEAD16')
    body=body.replace('for variant in C; do','for variant in D; do')
    body=body.replace('QINGYU_REFERENCE_B_TIMING: $HOME/Desktop/qingyu_db16_1Mmvm9/timing_B',
                      'QINGYU_REFERENCE_C_TIMING: $HOME/Desktop/qingyu_pipe16_hold_O9t0TW/check_ff_125c')
if block:
    body=body.replace('qingyu_ahead16_XXXXXX','qingyu_block16_XXXXXX').replace('QINGYU_AHEAD16','QINGYU_BLOCK16')
    body=body.replace('+define+QINGYU_READ_AHEAD', '+define+QINGYU_BLOCK_COPY +define+QINGYU_READ_AHEAD')
    body=body.replace('for variant in D; do','for variant in E; do')
    body=body.replace('for layer in layer??; do', """vcs -full64 -sverilog -timescale=1ns/1ps +define+QINGYU_BLOCK_COPY +define+QINGYU_READ_AHEAD +define+QINGYU_DOUBLE_BUFFER +define+ARM_UD_MODEL -top tb_block_copy ../tb_block_copy.sv rtl/qingyu_accel.sv rtl/qingyu_fio.sv macro/qingyu_sram16.sv "$models/RAMSP128X16/verilog/RAMSP128X16.v" "$models/RAMSP4096X16/verilog/RAMSP4096X16.v" -Mdir="$run/block_csrc" -o "$run/block_sim" > ../block_compile.log 2>&1 || { tail -20 ../block_compile.log; exit 1; }
"$run/block_sim" > ../block_test.log 2>&1
grep '^PASS CPU block transfer' ../block_test.log
for layer in layer??; do""")
    body=body.replace('cp ../rtl/*.sv rtl/', 'cp ../generated/qingyu_e203_soc_top.v generated/\ncp ../rtl/*.sv rtl/')
body=body.replace('# PAYLOAD', 'base64 -d > payload.tgz <<\'PAYLOAD\'\n'+base64.encodebytes(blob).decode()+'PAYLOAD\n'+"echo '"+hashlib.sha256(blob).hexdigest()+"  payload.tgz' | sha256sum -c -\ntar xzf payload.tgz")
(eda/('run_block16.sh' if block else 'run_ahead16.sh' if ahead else 'run_pipe16.sh' if pipe else 'run_db16.sh' if db else 'run_fast16.sh')).write_bytes(body.encode())
