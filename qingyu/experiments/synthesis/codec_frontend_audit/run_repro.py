"""Minimum plain-Verilog task-inout reproducer, no sv2v involved."""
from pathlib import Path
from datetime import datetime,timezone
import subprocess,hashlib,json
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=HERE/'runs'/('repro_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir(parents=True)
 original=HERE/'task_inout_repro.v';tb=HERE/'tb_task_inout_repro.sv'
 report=dict(diagnostic_complete=False,source_sha256={p.name:sha(p) for p in [original,tb,Path(__file__)]},stages=[])
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 def run(cmd,log):
  with (out/log).open('w') as f:return subprocess.run(cmd,cwd=out,stdout=f,stderr=subprocess.STDOUT,timeout=60).returncode
 save()
 for stage,passes in [('original',None),('proc_only','proc'),('optimized','proc\nopt\nwreduce\nopt\nmemory_collect\nopt_clean')]:
  src=original
  if passes:
   src=out/(stage+'.v');ys=out/(stage+'.ys');ys.write_text(f'read_verilog {original}\nhierarchy -top task_inout_repro\n{passes}\nwrite_verilog -noattr {src}\n')
   assert run(['yosys','-Q','-T','-s',str(ys)],stage+'_synth.log')==0
  binary=out/(stage+'.vvp');rc=run(['iverilog','-g2012','-s','tb_task_inout_repro','-o',str(binary),str(src),str(tb)],stage+'_compile.log');assert rc==0
  rc=run(['vvp',str(binary)],stage+'.log');text=(out/(stage+'.log')).read_text()
  report['stages'].append(dict(stage=stage,passed=rc==0,returncode=rc,log_sha256=sha(out/(stage+'.log')),text=text,netlist_sha256=sha(src)));save();print(stage,text,flush=True)
 report['diagnostic_complete']=True;save();print(out/'result.json')
if __name__=='__main__':main()
