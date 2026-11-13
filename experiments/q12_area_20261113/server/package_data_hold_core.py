from pathlib import Path
import hashlib,json,zipfile

here=Path(__file__).resolve().parent;root=here.parents[2]
base=root/'final/q12_20261113/vendor/src/q12/core_datareset'
files={'data_hold.sv':here.parent/'variants/data_hold/q12_task4.sv',
       'q12_pair_acc.sv':base/'q12_pair_acc.sv','q12_striped_sram.sv':base/'q12_striped_sram.sv',
       'map_core.tcl':here/'map_core.tcl','run_core.py':here/'run_core.py'}
identity={'baseline_commit':'305648e85802afe19adf1570d79c9a7720feb7eb','variants':['data_hold'],
          'files':{n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in files.items()}}
archive=here/'q12_data_hold_core.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for n,p in files.items():z.write(p,n)
    z.writestr('identity.json',json.dumps(identity,indent=2)+'\n')
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
(here/'qe').write_bytes(('''#!/bin/sh
set -eu
archive="$HOME/Desktop/q12_data_hold_core.zip"
printf '%s  %s\\n' 'DIGEST' "$archive" | sha256sum -c -
run_dir=$(mktemp -d /tmp/q12_core_package_XXXXXX)
python3 -m zipfile -e "$archive" "$run_dir"
nohup python3 -u "$run_dir/run_core.py" > "$run_dir/run.log" 2>&1 < /dev/null &
echo "Q12_DATA_HOLD_CORE_PID=$!"
echo "Q12_DATA_HOLD_CORE_LOG=$run_dir/run.log"
'''.replace('DIGEST',digest)).encode())
print('data_hold_core_sha256='+digest)
