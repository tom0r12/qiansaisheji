"""Pre-register varied and high-traffic samples before integrated RTL timing."""
from pathlib import Path
import json
import os
import subprocess
import sys
import hashlib

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 out=ROOT/'build/int8_packet_corpus_20261112';out.mkdir(exist_ok=False)
 budget_path=ROOT/'build/tiled_codec_budget_20261112/result.json'
 budget=json.loads(budget_path.read_text())['candidates']['global_rice32']['layers']
 metadata_path=ROOT/'build/model_reference_20261111_201956_613/float_validation/extraction_manifest.json'
 metadata=json.loads(metadata_path.read_text())
 records=[dict(v,layer=layer['layer']) for layer in budget for v in layer['samples']]
 selection={i:['fixed_index_variety'] for i in [0,31,127,255]}
 selection[9]=['existing_silence_control']
 for key,metric in [('input_words',lambda r:r['input_words']),('output_words',lambda r:r['output_words']),
                    ('input_plus_output',lambda r:r['input_words']+r['output_words'])]:
  extreme=max(records,key=lambda r:(metric(r),-r['sample_index'],-r['layer']))
  selection.setdefault(extreme['sample_index'],[]).append('maximum_'+key+'_in_frozen3072')
 codec=ROOT/'experiments/codec/rice32';manifest=json.loads((codec/'SOURCE_SHA256.json').read_text())
 for name,digest in manifest['files'].items():
  assert sha(codec/name)==digest,'frozen codec differs: '+name
 exporter=ROOT/'model/export_int8_packets.py'
 report={'passed':False,'script_sha256':sha(Path(__file__)),'exporter_sha256':sha(exporter),
  'frozen_budget_sha256':sha(budget_path),'metadata_sha256':sha(metadata_path),
  'scope':'Diagnostic RTL corpus, not an unbiased throughput mean or official600 score; no numeric/codec fitting',
  'selection_rule':'Fixed indices0,31,127,255 plus existing silence9 and deterministic maxima of input/output/combined traffic over the frozen3072 task budget, before any RTL timings',
  'selected':[{'sample_index':i,'sample_id':metadata['sample_ids'][i],'roles':selection[i]} for i in sorted(selection)],
  'results':[]}
 (out/'preregistration.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report['selected']),flush=True)
 env=dict(os.environ,OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
 for record in report['selected']:
  i=record['sample_index'];destination=out/f'sample{i:03d}'
  command=[sys.executable,str(exporter),'--output',str(destination),'--sample',str(i)]
  with (out/f'sample{i:03d}.log').open('w') as log:
   result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
  if result.returncode:raise RuntimeError('Packet export failed; retained '+str(out/f'sample{i:03d}.log'))
  artifact=destination/'result.json';data=json.loads(artifact.read_text())
  assert data['passed'] and data['sample_index']==i and sha(exporter)==report['exporter_sha256']
  report['results'].append({'sample_index':i,'path':str(artifact.relative_to(ROOT)),
   'sha256':sha(artifact),'tasks':len(data['layers']),
   'input_words':[r['input_words'] for r in data['layers']],
   'output_write_transactions':[r['output_written_words']+1 for r in data['layers']]})
  (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
  print('PASS packet sample',i,flush=True)
 report['passed']=True;report['tasks']=sum(r['tasks'] for r in report['results'])
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print('PASS '+str(out/'result.json'),flush=True)

if __name__=='__main__':main()
