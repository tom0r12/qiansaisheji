"""Separate original, sv2v and optimized Yosys simulation with an independent miter."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def rename(src,name):
 text=src.read_text();text,n=re.subn(r'\bmodule\s+rice32_encoder\b','module '+name,text,count=1);assert n==1;return text

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',choices=['encoder','bounded_encoder'],default='encoder');a=p.parse_args()
 inventory=ROOT/'build/int8_structure/20261111T180353162824Z'/a.case
 original=ROOT/('experiments/codec/rice32_bounded' if a.case.startswith('bounded') else 'experiments/codec/rice32')/'rice32_encoder.sv'
 out=HERE/'runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
 report=dict(schema='qingyu-codec-frontend-audit-v1',case=a.case,passed=False,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in [original,inventory/'converted.v',inventory/'structure.json',HERE/'tb_encoder_miter.sv',Path(__file__)]},stages=[],limits=['Behavior/equivalence diagnostic, not physical PPA or official synthesis signoff'])
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 def run(cmd,log):
  with (out/log).open('w') as f:q=subprocess.run(cmd,cwd=out,stdout=f,stderr=subprocess.STDOUT,timeout=180)
  return q.returncode
 # Yosys0.33 write_json emits malformed non-ASCII source-location escapes and
 # its own read_json rejects those. Re-run the exact recorded passes and export
 # a new netlist; never edit/rewrite the original inventory artifacts.
 ys=out/'export.ys'
 recorded=(inventory/'inventory.ys').read_text()
 lines=[line for line in recorded.splitlines() if not line.startswith('write_json ')]
 ys.write_text('\n'.join(lines)+f'\nwrite_verilog -noattr {out/"optimized.v"}\n')
 report['export_method']='Exact recorded original converted.v and passes, replacing only write_json with write_verilog -noattr; original artifacts untouched'
 save()
 export_code=run(['yosys','-Q','-T','-s',str(ys)],'export.log')
 report['export_returncode']=export_code;save();assert export_code==0
 (out/'reference.v').write_text(rename(original,'reference_encoder'))
 for stage,source in [('original_sv',original),('sv2v',inventory/'converted.v'),('yosys_optimized',out/'optimized.v')]:
  candidate=out/f'{stage}.v';candidate.write_text(rename(source,'candidate_encoder'))
  binary=out/(stage+'.vvp')
  compile_code=run(['iverilog','-g2012','-Wall','-s','tb_encoder_miter','-o',str(binary),str(out/'reference.v'),str(candidate),str(HERE/'tb_encoder_miter.sv')],stage+'_compile.log')
  simulation_code=run(['vvp',str(binary)],stage+'.log') if compile_code==0 else None
  log=(out/(stage+'.log')).read_text() if simulation_code is not None else ''
  good=simulation_code==0 and 'PASS encoder frontend miter' in log
  report['stages'].append(dict(stage=stage,source_sha256=sha(source),compile_returncode=compile_code,simulation_returncode=simulation_code,passed=good,log_sha256=sha(out/(stage+'.log')) if simulation_code is not None else None,tail=log[-2000:]));save()
  print(stage,'PASS' if good else 'FAIL',log[-400:],flush=True)
 assert all(sha(ROOT/name)==h for name,h in report['source_sha256'].items())
 report['passed']=all(s['passed'] for s in report['stages']);report['diagnostic_complete']=True
 save();print(out/'result.json',flush=True)

if __name__=='__main__':main()
