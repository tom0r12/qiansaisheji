from pathlib import Path
import hashlib,json,zipfile

here=Path(__file__).resolve().parent;root=here.parents[2]
candidate=here.parent/'variants/data_hold/q12_task4.sv'
monitor=here.parent/'checks/q12_data_init_check.sv'
identity={'candidate':'q12_area_requant_data_hold_v2','data_hold':True,
          'manifest_sha256':hashlib.sha256((root/'final/q12_20261113/vendor/manifest.json').read_bytes()).hexdigest(),
          'candidate_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),
          'monitor_sha256':hashlib.sha256(monitor.read_bytes()).hexdigest()}
archive=here/'q12_data_hold_replay.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    z.write(here/'replay_candidate.py','replay_candidate.py')
    z.write(candidate,'q12_task4.sv')
    z.write(monitor,'q12_data_init_check.sv')
    z.writestr('replay_identity.json',json.dumps(identity,indent=2)+'\n')
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
(here/'qd').write_bytes(('''#!/bin/sh
set -eu
archive="$HOME/Desktop/q12_data_hold_replay.zip"
printf '%s  %s\\n' 'DIGEST' "$archive" | sha256sum -c -
run_dir=$(mktemp -d /tmp/q12_area_package_XXXXXX)
python3 -m zipfile -e "$archive" "$run_dir"
nohup python3 -u "$run_dir/replay_candidate.py" > "$run_dir/run.log" 2>&1 < /dev/null &
echo "Q12_DATA_HOLD_LAUNCH_PID=$!"
echo "Q12_DATA_HOLD_LAUNCH_LOG=$run_dir/run.log"
'''.replace('DIGEST',digest)).encode())
print('data_hold_sha256='+digest)
