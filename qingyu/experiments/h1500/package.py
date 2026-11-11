"""Freeze tested H1500 sources into an isolated server VCS/DC/Formality flow."""
import base64,gzip,hashlib,io,json,tarfile,time
from pathlib import Path
root=Path(__file__).resolve().parents[2]
exp=Path(__file__).resolve().parent
eda=root.parent/'output/eda'
run=root/'build/h1500_vcs_compatible'
measured=json.loads((run/'result.json').read_text())
assert measured['outputs']==304128 and len(measured['layers'])==12
assert all(hashlib.sha256((root/k).read_bytes()).hexdigest()==v for k,v in measured['sha256'].items())
template=(eda/'run_h16.sh').read_bytes()
prefix,body=template.split(b"<<'PAYLOAD'\n",1)
encoded,suffix=body.split(b'\nPAYLOAD\n',1)
old=base64.b64decode(encoded); oldhash=hashlib.sha256(old).hexdigest().encode()
files={}
with tarfile.open(fileobj=io.BytesIO(old)) as arc:
 for m in arc: files[m.name]=arc.extractfile(m).read()
for name in ['qingyu_fio.sv','qingyu_accel.sv']:
 header=files['rtl/'+name].split(b'// System-bus endpoint',1)[0] if name=='qingyu_fio.sv' else b''
 files['rtl/'+name]=header+(exp/'rtl'/name).read_bytes().replace(b'\r',b'')
for i in range(12):
 name=f'layer{i:02}/firmware64.hex';files[name]=(run/name).read_bytes()
for name in ['tb_qingyu_soc_performance.sv','tb_qingyu_soc_macro_performance.sv']:
 data=files[name].replace(b'weight_commands!=512',b'weight_commands!=16')
 data=data.replace(b"fixture.dut.u_fio.icb_cmd_addr==32'hf0000038",b"(fixture.dut.u_fio.icb_cmd_addr==32'hf0000038 || fixture.dut.u_fio.icb_cmd_addr==32'hf0000084)")
 files[name]=data
files['area.tcl']=files['area.tcl'].replace(b'RAMSP128X16 21 RAMSP1024X16 0 RAMSP4096X16 2',b'RAMSP128X16 33 RAMSP1024X16 8 RAMSP4096X16 0')
for p in (exp/'tests').glob('*.sv'): files[p.name]=p.read_bytes()
for name in ['qingyu_accel.c','soc_perf_main.c']:files['driver/'+name]=(exp/'rtl'/name).read_bytes()
files['local_cycles.tsv']=''.join(f"layer{r['layer']:02} {r['cycles']}\n" for r in measured['layers']).encode()
# A fresh formal run compares the exact new RTL and newly mapped netlist.
f=(eda/'run_formality_h16.sh').read_text()
f=f.replace('base="$desk/qingyu_h16_9tJxup"','base="${1:?pass frozen H1500 run directory}"').replace('qingyu_formality_h16_','qingyu_formality_h1500_')
a=f.index("cat > rtl.sha256 <<'HASH'");b=f.index('sha256sum -c rtl.sha256',a)
f=f[:a]+"cat > rtl.sha256 <<'HASH'\n"+''.join(hashlib.sha256(files['rtl/'+name]).hexdigest()+'  inputs/'+name+'\n' for name in ['qingyu_accel.sv','qingyu_fio.sv'])+'HASH\n'+f[b:]
files['formality.sh']=f.encode()
# Stop after functional, area, five-corner timing and formal checks; do not reuse H power.
suffix=suffix.split(b'echo "QINGYU_REFERENCE_C_TIMING:',1)[0]
suffix=suffix.replace(b'103 SRAM macros',b'121 SRAM macros').replace(b'23 private macros',b'41 private macros')
suffix=suffix.replace(b'for unit in tb_weight_stream tb_load_chain;',b'for unit in tb_weight_stream tb_load_chain tb_stage256 tb_h1500_transfer;')
# All unit binaries need the 1024-word macros used by compact X banks.
suffix=suffix.replace(b'"$models/RAMSP128X16/verilog/RAMSP128X16.v" "$models/RAMSP4096X16/verilog/RAMSP4096X16.v"',b'"$models/RAMSP128X16/verilog/RAMSP128X16.v" "$models/RAMSP1024X16/verilog/RAMSP1024X16.v" "$models/RAMSP4096X16/verilog/RAMSP4096X16.v"')
suffix=suffix.replace(b'RAMSP128X16 21 RAMSP1024X16 0 RAMSP4096X16 2',b'RAMSP128X16 33 RAMSP1024X16 8 RAMSP4096X16 0')
suffix=suffix.replace(b'for variant in H;',b'for variant in H1500;')
suffix+=b'echo "QINGYU_H1500: formal equivalence of this frozen candidate"\nsh formality.sh "$run" > formal_summary.log 2>&1 || { tail -30 formal_summary.log; exit 1; }\ngrep -E "Verification SUCCEEDED|QINGYU_VERIFY_RETURN|QINGYU_REPORT_ERRORS" formal_summary.log\necho "QINGYU_H1500_REPORTS_READY: $run"\necho "Engineering timing only; inspect hold/setup violations and formal audit. New energy measurements remain pending."\n'
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w') as arc:
 for name,data in files.items():
  m=tarfile.TarInfo(name);m.size=len(data);m.mtime=int(time.time());arc.addfile(m,io.BytesIO(data))
packed=gzip.compress(buf.getvalue(),mtime=0)
suffix=suffix.replace(oldhash,hashlib.sha256(packed).hexdigest().encode())
script=prefix+b"<<'PAYLOAD'\n"+base64.encodebytes(packed).rstrip()+b'\nPAYLOAD\n'+suffix
script=script.replace(b'qingyu_h16_XXXXXX',b'qingyu_h1500_XXXXXX').replace(b'QINGYU_H16',b'QINGYU_H1500')
target=eda/'run_h1500_v2.sh';target.write_bytes(script)
print(target,len(script),hashlib.sha256(script).hexdigest())
