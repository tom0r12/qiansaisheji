"""Check the new physical INT8 fixture using an external functional SRAM model.

This deliberately cannot certify manufacturer timing or PPA. The model remains
outside every generated server bundle.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,shutil,subprocess,tempfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--soc-run',type=Path,required=True)
 p.add_argument('--images',type=Path,required=True)
 p.add_argument('--models',type=Path,required=True)
 p.add_argument('--layer',type=int,default=0)
 p.add_argument('--simulator',choices=['iverilog','verilator'],default='iverilog')
 p.add_argument('--jobs',type=int,default=2)
 a=p.parse_args();run=a.soc_run.resolve();images=a.images.resolve();model=a.models.resolve()
 if not 0<=a.layer<12 or not 1<=a.jobs<=2:p.error('layer0..11/jobs1..2')
 report=json.loads((run/'result.json').read_text())
 if not report['passed'] or report.get('reuse_contract_version')!=2:raise ValueError('Need passed hardened SoC report')
 for path,h in report['sources_sha256'].items():
  if sha(ROOT/path)!=h:raise ValueError('Validated source changed: '+path)
 data=images/f'layer{a.layer:02d}';m=json.loads((data/'manifest.json').read_text())
 row=next(row for row in report['layers'] if row['layer']==a.layer)
 if sha(data/'manifest.json')!=row['packet_manifest_sha256']:raise ValueError('Input is not the compared validated task')
 for name,h in m['files_sha256'].items():
  if sha(data/name)!=h:raise ValueError('Packet differs')
 if sha(run/'firmware64.hex')!=report['firmware_hex_sha256']:raise ValueError('Firmware differs')
 if sha(model)!='cd78caa3d3484f22d397b173e9c6a610c76939f53b7ff332a0dd55354bae9a33':raise ValueError('Only explicitly identified external local stand-in is allowed here')
 oldshared='experiments/h1500v/opt33_readcache/rtl/qingyu_shared_sram.sv'
 replacement={'<run>/config.v':run/'config.v','rtl/qingyu_sram16.sv':ROOT/'rtl/asic/qingyu_sram16.sv',
  oldshared:ROOT/'experiments/h1500v/opt33_readcache/rtl/asic/qingyu_shared_sram.sv',
  'vendor/e203_hbirdv2/rtl/e203/general/sirv_gnrl_ram.v':ROOT/'rtl/asic/sirv_gnrl_ram.v',
  'vendor/e203_hbirdv2/rtl/e203/general/sirv_sim_ram.v':None,
  'experiments/integration/int8soc/tb_int8soc.sv':HERE/'tb_int8soc_macro.sv'}
 sources=[replacement.get(n,ROOT/n) for n in report['source_order']]
 sources=[s for s in sources if s is not None]+[ROOT/'rtl/asic/qingyu_banked_sram.sv',model]
 includes=[ROOT/'vendor/e203_hbirdv2/rtl/e203'/d for d in ['core','perips','perips/apb_i2c']]
 headers=[ROOT/n for n in report['sources_sha256'] if n not in report['source_order'] and not n.startswith('build/int8soc/')]
 out=ROOT/'build/int8soc_physical_fixture'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
 snapshot={str(s):sha(s) for s in sources+headers}
 r=dict(passed=False,model_kind='external_local_functional_standin',manufacturer=False,model_sha256=sha(model),
  simulator=a.simulator,checker_runner_sha256=sha(Path(__file__)),source_run=run.relative_to(ROOT).as_posix(),source_run_sha256=sha(run/'result.json'),
  sources_sha256=snapshot,commands=[],limits=['Four-state functional SRAM substitute only; not manufacturer or timing/PPA evidence','Testbench preload excluded from CPU setup window'])
 def save():(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 def execute(command,name,timeout):
  r['commands'].append(list(map(str,command)));save()
  with (out/name).open('w') as f:subprocess.run(command,cwd=out,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=timeout)
 try:
  if a.simulator=='iverilog':
   execute(['iverilog','-g2012','-s','tb_int8soc','-DDISABLE_SV_ASSERTION=1',*['-I'+str(d) for d in includes],'-o',out/'simv',*sources],'compile.log',600)
   binary=['vvp',out/'simv']
  else:
   obj=Path(tempfile.mkdtemp(prefix='qingyu_int8physical_'))
   execute(['verilator','--binary','--timing','--autoflush','--timescale-override','1ns/1ps','--top-module','tb_int8soc','--prefix','Vint8physical','--Mdir',obj,'-Wno-fatal','-DDISABLE_SV_ASSERTION=1','-j',str(a.jobs),'-CFLAGS','-O1',*['-I'+str(d) for d in includes],*sources],'compile.log',1200)
   binary=[obj/'Vint8physical']
  for source,name in [(run/'firmware64.hex','firmware64.hex'),(data/'input.hex','input.hex'),(data/'expected_output.hex','expected.hex')]:shutil.copy2(source,out/name)
  execute([*binary,'+FIRMWARE=firmware64.hex','+INPUT=input.hex','+EXPECTED=expected.hex','+INPUT_WORDS='+str(m['input_words']),'+OUTPUT_WORDS='+str(m['output_written_words']),'+LAYER='+str(a.layer)],'simulation.log',600)
  log=(out/'simulation.log').read_text()
  if 'PASS real E203 INT8 physical packet task complete;' not in log:raise ValueError('Missing physical readback PASS')
  metrics={tag:[{k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',s)} for s in re.findall('^'+tag+r' (.*)$',log,re.M)] for tag in ['INT8SOC_METRICS','QINGYU_ACTIVITY_START','QINGYU_ACTIVITY_END','QINGYU_MACRO_PRELOAD_COMPLETE','QINGYU_MACRO_READBACK_COMPLETE']}
  if any(len(v)!=1 for v in metrics.values()):raise ValueError('Missing/ambiguous fixture metrics')
  metrics={k:v[0] for k,v in metrics.items()};r['metrics']=metrics
  if metrics['INT8SOC_METRICS']!=row['metrics']:raise ValueError('Physical fixture metrics differ from behavioral SoC baseline')
  start=metrics['QINGYU_ACTIVITY_START'];end=metrics['QINGYU_ACTIVITY_END']
  if end['cycle']-start['cycle']!=row['metrics']['cpu_setup_to_ack']:raise ValueError('Activity cycle duration differs')
  if metrics['QINGYU_MACRO_READBACK_COMPLETE']['words']!=131072:raise ValueError('Incomplete physical readback')
  if any(sha(Path(n))!=h for n,h in snapshot.items()):raise ValueError('Sources changed during verification')
  r.update(passed=True,identical_baseline_metrics=True,simulation_log_sha256=sha(out/'simulation.log'))
 except Exception as e:r['error']=str(e);raise
 finally:save();print(out/'result.json',flush=True)
if __name__=='__main__':main()
