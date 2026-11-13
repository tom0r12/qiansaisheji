from pathlib import Path
import hashlib
import zipfile

here=Path(__file__).resolve().parent
archive=here/'q12_quant_area.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for p in (here/'run_quant.py',here/'map_quant.tcl',here.parent/'checks/quant_miter.sv'):
        z.write(p,p.name)
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
launcher='''#!/bin/sh
set -eu
archive="$HOME/Desktop/q12_quant_area.zip"
printf '%s  %s\\n' 'DIGEST' "$archive" | sha256sum -c -
run_dir=$(mktemp -d /tmp/q12_quant_package_XXXXXX)
python3 -m zipfile -e "$archive" "$run_dir"
nohup python3 -u "$run_dir/run_quant.py" > "$run_dir/run.log" 2>&1 < /dev/null &
echo "Q12_QUANT_LAUNCH_PID=$!"
echo "Q12_QUANT_LAUNCH_LOG=$run_dir/run.log"
'''.replace('DIGEST',digest)
(here/'qa').write_bytes(launcher.encode())
print('package_sha256='+digest)
print('package_bytes='+str(archive.stat().st_size))
