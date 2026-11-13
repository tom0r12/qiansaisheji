from pathlib import Path
import hashlib,json,zipfile

here=Path(__file__).resolve().parent
root=here.parents[2]
candidate=here.parent/'rtl/q12_task4.sv'
identity={'manifest_sha256':hashlib.sha256((root/'final/q12_20261113/vendor/manifest.json').read_bytes()).hexdigest(),
          'candidate_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest()}
archive=here/'q12_area_replay.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    z.write(here/'replay_candidate.py','replay_candidate.py')
    z.write(candidate,'q12_task4.sv')
    z.writestr('replay_identity.json',json.dumps(identity,indent=2)+'\n')
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
(here/'qb').write_bytes(('''#!/bin/sh
set -eu
archive="$HOME/Desktop/q12_area_replay.zip"
printf '%s  %s\\n' 'DIGEST' "$archive" | sha256sum -c -
run_dir=$(mktemp -d /tmp/q12_area_package_XXXXXX)
python3 -m zipfile -e "$archive" "$run_dir"
nohup python3 -u "$run_dir/replay_candidate.py" > "$run_dir/run.log" 2>&1 < /dev/null &
echo "Q12_AREA_LAUNCH_PID=$!"
echo "Q12_AREA_LAUNCH_LOG=$run_dir/run.log"
'''.replace('DIGEST',digest)).encode())
(here/'qr').write_bytes(b'''#!/bin/sh
python3 - <<'PY'
from pathlib import Path
import json
for prefix in ('q12_quant_package_','q12_area_package_'):
 paths=sorted(Path('/tmp').glob(prefix+'*/run.log'),key=lambda p:p.stat().st_mtime)
 for p in paths[-2:]:
  print(str(p)); print('\\n'.join(p.read_text(errors='replace').splitlines()[-4:]))
for prefix in ('q12_quant_area_','q12_area_replay_'):
 paths=sorted(Path('/tmp').glob(prefix+'*/result.json'),key=lambda p:p.stat().st_mtime)
 for p in paths[-2:]:
  r=json.loads(p.read_text());print(str(p))
  if 'results' in r:print(json.dumps(r['results']))
  else:print(json.dumps({k:r.get(k) for k in ('passed','phase','error','mean_full_window_cycles','throughput_at_assumed_150mhz')}));print('TASKS',len(r.get('tasks',[])))
PY
''')
print('replay_sha256='+digest)
