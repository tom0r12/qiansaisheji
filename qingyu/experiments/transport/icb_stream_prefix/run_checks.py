"""Standalone stream transport tests through unchanged official E203 memory fabric."""
import argparse,hashlib,json,re,shutil,subprocess
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seeds',nargs='+',type=int,default=[17,271,818]);p.add_argument('--outstanding',nargs='+',type=int,default=[4,8]);p.add_argument('--response-queue',nargs='+',type=int,default=[0,1]);a=p.parse_args()
 if any(n not in [4,8] for n in a.outstanding):p.error('tested configurations are 4 and 8')
 if any(n not in [0,1] for n in a.response_queue):p.error('response-queue must be 0 (native bandwidth) or 1 (extra test-only return delay)')
 out=ROOT/'build/icb_stream_prefix'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
 inventory=ROOT/'reports/e203-source-manifest.json';pin=json.loads(inventory.read_text())
 assert pin['ready'] and pin['commit']=='9f3e34f337f5d0a1236a285871ffa2032491617a'
 vendor=ROOT/'vendor/e203_hbirdv2';sources=[]
 fixed=HERE.parent/'icb_stream';fixed_manifest=fixed/'SOURCE_SHA256.json'
 assert sha(fixed_manifest)=='09260f88c58e452a03056756e6c4fba937605b549836c18bb10dfe061b748096'
 for name,h in json.loads(fixed_manifest.read_text())['files'].items():assert sha(fixed/name)==h
 for f in sorted((vendor/'rtl').rglob('*.v')):
  entry=pin['files'][f.relative_to(vendor).as_posix()];assert entry['matches_commit'] and sha(f)==entry['sha256'];sources.append(f)
 candidate=ROOT/'experiments/h1500v/opt33_readcache';frozen=json.loads((candidate/'SOURCE_SHA256.json').read_text())
 slave=candidate/'rtl/qingyu_shared_sram.sv';assert sha(slave)==frozen['files']['rtl/qingyu_shared_sram.sv']
 sources += [slave,HERE/'qingyu_icb_stream_prefix.sv',HERE/'tb_icb_stream_prefix.sv']
 snapshot={p.relative_to(ROOT).as_posix():sha(p) for p in sources+[Path(__file__),HERE/'CONTRACT.md']}
 r=dict(passed=False,scope='Standalone transport through unchanged official fabric; no SoC task, PPA or official-loader result',
        source_sha256=snapshot,fixed_source_manifest_sha256=sha(fixed_manifest),vendor_manifest_sha256=sha(inventory),slave_manifest_sha256=sha(candidate/'SOURCE_SHA256.json'),
        official_parameters=dict(ICB_FIFO_DP=2,ICB_FIFO_CUT_READY=1,SPLT_FIFO_OUTS_NUM=1,SPLT_FIFO_CUT_READY=1),runs=[],commands=[],tools={})
 def save():(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 def run(cmd,name,timeout=120):
  r['commands'].append(list(map(str,cmd)));save()
  proc=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=timeout)
  log=out/(name+'.log');log.write_text(proc.stdout+proc.stderr);proc.check_returncode();return log
 ts=out/'timescale.v';ts.write_text('`timescale 1ns/1ps\n')
 includes=['-I'+str((vendor/'rtl/e203'/d).relative_to(ROOT)) for d in ['core','perips','perips/apb_i2c']]
 try:
  for tool in ['iverilog','vvp','verilator']:
   version=subprocess.run([tool,'--version' if tool=='verilator' else '-V'],capture_output=True,text=True)
   r['tools'][tool]=dict(path=shutil.which(tool),version=(version.stdout+version.stderr).splitlines()[0]);save()
  for depth in a.outstanding:
   lint=run(['verilator','--lint-only','-Wall','--top-module','qingyu_icb_stream_prefix',f'-GOUTSTANDING={depth}',str((HERE/'qingyu_icb_stream_prefix.sv').relative_to(ROOT))],f'lint_{depth}')
   for queue in a.response_queue:
    exe=out/f'stream{depth}_queue{queue}.vvp'
    run(['iverilog','-g2012','-DDISABLE_SV_ASSERTION=1','-s','tb_icb_stream_prefix',f'-Ptb_icb_stream_prefix.OUTSTANDING={depth}',f'-Ptb_icb_stream_prefix.RESPONSE_QUEUE={queue}',*includes,'-o',str(exe.relative_to(ROOT)),str(ts.relative_to(ROOT)),*[str(f.relative_to(ROOT)) for f in sources]],f'compile_{depth}_queue{queue}')
    for seed in a.seeds:
     log=run(['vvp',str(exe.relative_to(ROOT)),f'+SEED={seed}'],f'depth{depth}_queue{queue}_seed{seed}')
     text=log.read_text();passed=re.findall(r'^PASS icb_stream_prefix (.*)$',text,re.M);assert len(passed)==1
     summary={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',passed[0])}
     assert summary['outstanding']==depth and summary['seed']==seed and summary['response_queue']==queue
     rows=[{k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)} for line in text.splitlines() if line.startswith('STREAM_CASE ')]
     for row in rows:
      if row['commands']>1:row['measured_shared_ii']=row['shared_span']/(row['commands']-1)
     r['runs'].append(dict(outstanding=depth,seed=seed,response_queue=queue,bandwidth_eligible=(queue==0),summary=summary,
                          log=log.relative_to(ROOT).as_posix(),log_sha256=sha(log),cases=rows));save()
     print(f'PASS outstanding={depth} queue={queue} seed={seed} scenarios={summary["cases"]}',flush=True)
  assert snapshot=={name:sha(ROOT/name) for name in snapshot},'Sources changed during regression'
  r['passed']=True
 except Exception as e:r['error']=str(e);raise
 finally:save();print(out/'result.json',flush=True)
if __name__=='__main__':main()

