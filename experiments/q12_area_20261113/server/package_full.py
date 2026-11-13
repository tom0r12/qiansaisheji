from pathlib import Path
import hashlib,json,zipfile

here=Path(__file__).resolve().parent;root=here.parents[2]
assessment=root/'final/q12_20261113/assessment'
candidate=here.parent/'variants/data_hold/q12_task4.sv'
identity={'baseline_package_identity_sha256':hashlib.sha256((assessment/'package_identity.json').read_bytes()).hexdigest(),
          'baseline_source_sha256':hashlib.sha256((assessment/'hardware/src/output/eda/q12_candidate/core_datareset/q12_task4.sv').read_bytes()).hexdigest(),
          'candidate_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest()}
archive=here/'q12_area_full.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    z.write(here/'run_full_candidate.py','run_full_candidate.py')
    z.write(candidate,'q12_task4.sv')
    z.writestr('identity.json',json.dumps(identity,indent=2)+'\n')
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
(here/'qf.zip').write_bytes(archive.read_bytes())
(here/'qf').write_bytes(('''#!/bin/sh
set -eu
archive="$HOME/Desktop/qf.zip"
printf '%s  %s\\n' 'DIGEST' "$archive" | sha256sum -c -
run_dir=$(mktemp -d /tmp/q12_full_package_XXXXXX)
python3 -m zipfile -e "$archive" "$run_dir"
nohup python3 -u "$run_dir/run_full_candidate.py" > "$run_dir/run.log" 2>&1 < /dev/null &
echo "Q12_FULL_LAUNCH_PID=$!"
echo "Q12_FULL_LAUNCH_LOG=$run_dir/run.log"
'''.replace('DIGEST',digest)).encode())
print('full_sha256='+digest)
