"""Freeze the independent profile without touching its baseline fixture manifest."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads((HERE/'PROFILE_VALIDATION.json').read_text())
files={p.name:sha(p) for p in [HERE/'prepare_profile.py',HERE/'tb_streaming_loader_profile.sv',HERE/'summarize_profile.py',HERE/'freeze_profile.py',HERE/'PROFILE.md',HERE/'PROFILE_VALIDATION.json']}
deps={(HERE.parent/'run_profile.py').relative_to(ROOT).as_posix():sha(HERE.parent/'run_profile.py')}
for row in report['runs']:
 p=ROOT/row['result']
 if sha(p)!=row['result_sha256']:raise ValueError('Result changed')
 r=json.loads(p.read_text())
 for k,h in {**r['compiled_source_sha256'],**r['source_sha256']}.items():
  if sha(ROOT/k)!=h:raise ValueError('Source changed: '+k)
  deps[k]=h
manifest=dict(schema='qingyu-conditional-loader-profile-source-v1',frozen=True,files=files,external_dependencies=deps,
 baseline_manifest='SOURCE_SHA256.json',baseline_manifest_sha256=sha(HERE/'SOURCE_SHA256.json'),
 validation='PROFILE_VALIDATION.json',validation_sha256=sha(HERE/'PROFILE_VALIDATION.json'),
 limitations=report['limitations'])
(HERE/'PROFILE_SOURCE_SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(sha(HERE/'PROFILE_SOURCE_SHA256.json'))
