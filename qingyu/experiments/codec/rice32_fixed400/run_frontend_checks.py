"""Local frontend equivalence regression; never physical area evidence."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--vectors',type=Path,required=True);p.add_argument('--reuse-export',type=Path);a=p.parse_args()
 vectors=a.vectors.resolve();evidence=json.loads((vectors/'result.json').read_text());assert evidence['passed']
 out=HERE/'runs'/('frontend_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir(parents=True)
 tracked=[HERE/'rice32_encoder.sv',HERE/'rice32_decoder.sv',HERE/'tb_rice32_fixed400.sv',Path(__file__)]
 report=dict(schema='qingyu-fixed-codec-frontend-check-v1',passed=False,source_sha256={x.name:sha(x) for x in tracked},vectors_result_sha256=sha(vectors/'result.json'),stages=[],limits=['Finite sequential simulation equivalence, not exhaustive LEC or physical synthesis/PPA'])
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 def run(cmd,log,cwd=out):
  with (out/log).open('w') as f:q=subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=900)
  return q.returncode
 shadow=out/'reference_rice32_encoder.sv'
 shadow_original=ROOT/'experiments/codec/rice32_bounded/rice32_encoder.sv'
 shadow.write_text(shadow_original.read_text().replace('module rice32_encoder #(', 'module reference_rice32_encoder #('))
 report['shadow_reference_sha256']=sha(shadow_original)
 save()
 try:
  converted=[];optimized=[]
  if a.reuse_export:
   old=json.loads((a.reuse_export/'result.json').read_text())
   assert all(sha(x)==old['source_sha256'][x.name] for x in tracked[:3])
   report['reused_export_result_sha256']=sha(a.reuse_export/'result.json')
  for unit in ['encoder','decoder']:
   source=HERE/f'rice32_{unit}.sv';v=out/f'{unit}_sv2v.v';net=out/f'{unit}_yosys.v'
   if a.reuse_export:
    v.write_bytes((a.reuse_export/f'{unit}_sv2v.v').read_bytes());net.write_bytes((a.reuse_export/f'{unit}_yosys.v').read_bytes());converted.append(v);optimized.append(net);continue
   with v.open('w') as f, (out/(unit+'_sv2v.log')).open('w') as log:
    q=subprocess.run(['/opt/qingyu-tools/sv2v-0.0.13/sv2v-Linux/sv2v','-DSYNTHESIS',str(source)],stdout=f,stderr=log,timeout=900)
   assert q.returncode==0
   ys=out/(unit+'.ys');ys.write_text(f'read_verilog {v}\nhierarchy -check -top rice32_{unit}\nproc\nopt\nwreduce\nopt\nmemory_collect\nopt_clean\ncheck -assert\nwrite_verilog -noattr {net}\n')
   assert run(['yosys','-Q','-T','-s',str(ys)],unit+'_yosys.log')==0
   converted.append(v);optimized.append(net)
  for stage,rtl in [('original_sv',tracked[:2]),('sv2v',converted),('yosys_optimized',optimized)]:
   exe=out/(stage+'.vvp')
   tb=tracked[2]
   if stage=='yosys_optimized':
    tb=out/'tb_netlist.sv';body=tracked[2].read_text();assert body.count('#(.LANES(LANES))')==3
    tb.write_text(body.replace('#(.LANES(LANES))',''))
    report['netlist_tb_adaptation']='Remove three parameter overrides (candidate modules plus reference default4) because synthesized modules have already elaborated LANES=4; stimulus/checkers unchanged'
   report.setdefault('generated_artifacts_sha256',{}).update({x.name:sha(x) for x in [*rtl,tb]})
   code=run(['iverilog','-g2012','-Wall','-s','tb_rice32_fixed400','-o',str(exe),*map(str,rtl),str(shadow),str(tb)],stage+'_compile.log')
   sim=run(['vvp',str(exe),'+MANIFEST=manifest.txt','+SEED=17'],stage+'.log',vectors) if code==0 else None
   text=(out/(stage+'.log')).read_text() if sim is not None else ''
   ok=code==0 and sim==0 and 'PASS rice32_fixed400' in text
   report['stages'].append(dict(stage=stage,compile_returncode=code,simulation_returncode=sim,passed=ok,log_sha256=sha(out/(stage+'.log')) if sim is not None else None,tail=text[-1800:]));save();print(stage,'PASS' if ok else 'FAIL',flush=True)
   if not ok:raise RuntimeError(stage+' failed: '+text[-1000:])
  assert all(sha(x)==report['source_sha256'][x.name] for x in tracked)
  report['passed']=True
 except Exception as e:report['failure']=str(e);raise
 finally:save();print(out/'result.json',flush=True)
if __name__=='__main__':main()
