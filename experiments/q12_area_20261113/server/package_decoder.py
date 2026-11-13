from pathlib import Path
import hashlib,json,zipfile
here=Path(__file__).resolve().parent;experiment=here.parent;root=experiment.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files={'q12_task4.sv':experiment/'variants/data_hold/q12_task4.sv',
       'q12_rice_decoder.sv':experiment/'variants/decoder_window/q12_rice_decoder.sv',
       'map_decoder.tcl':here/'map_decoder.tcl','run_decoder_candidate.py':here/'run_decoder_candidate.py'}
identity={'baseline_vendor_manifest_sha256':sha(root/'final/q12_20261113/vendor/manifest.json'),'files':{n:sha(p)for n,p in files.items()},'local_proof':json.loads((experiment/'variants/decoder_window/checks/result.json').read_text()),'local_replay':json.loads((experiment/'variants/decoder_window/checks/replay_result.json').read_text())}
assert identity['local_proof']['passed']and identity['local_replay']['passed']
assert identity['local_proof']['candidate_sha256']==identity['files']['q12_rice_decoder.sv']==identity['local_replay']['candidate_sha256']
with zipfile.ZipFile(here/'qg.zip','w',zipfile.ZIP_DEFLATED)as z:
 for n,p in files.items():z.write(p,n)
 z.writestr('identity.json',json.dumps(identity,indent=2)+'\n')
script='''#!/bin/sh
set -eu
archive="$HOME/Desktop/qg.zip"
printf '%s  %s\\n' 'DIGEST' "$archive" | sha256sum -c -
run_dir=$(mktemp -d /tmp/q12_decoder_package_XXXXXX)
python3 -m zipfile -e "$archive" "$run_dir"
nohup python3 -u "$run_dir/run_decoder_candidate.py" > "$run_dir/run.log" 2>&1 < /dev/null &
echo "Q12_DECODER_LAUNCH_PID=$!"
echo "Q12_DECODER_LAUNCH_LOG=$run_dir/run.log"
'''.replace('DIGEST',sha(here/'qg.zip'))
(here/'qg').write_bytes(script.encode());print('qg.zip',sha(here/'qg.zip'))
