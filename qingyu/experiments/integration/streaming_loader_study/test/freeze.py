"""Record this fixture's tested sources without changing any original result."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
summary=json.loads((HERE/'VALIDATION.json').read_text())
names=['PLAN.md','README.md','tb_streaming_loader.sv','summarize.py','freeze.py','VALIDATION.json']
files={n:sha(HERE/n) for n in names};files['../run_checks.py']=sha(HERE.parent/'run_checks.py')
dependencies={}
for run in summary['runs']:
 r=json.loads((ROOT/run['result']).read_text())
 if sha(ROOT/run['result'])!=run['result_sha256']:raise ValueError('Result changed')
 for k,h in {**r['compiled_source_sha256'],**r['source_sha256']}.items():
  if sha(ROOT/k)!=h:raise ValueError('Source changed')
  dependencies[k]=h
manifest=dict(schema='qingyu-conditional-loader-fixture-source-v1',frozen=True,
 files=files,external_dependencies=dependencies,
 validation='VALIDATION.json',validation_sha256=sha(HERE/'VALIDATION.json'),
 limitation='Conditional loader ONE_PER_PORT01; not actual CPU/official loader or PPA; primary only reset-cold case id1')
(HERE/'SOURCE_SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(sha(HERE/'SOURCE_SHA256.json'))
