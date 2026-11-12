"""Combine immutable per-candidate bundles under distinct neutral directories."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root=Path(__file__).resolve().parents[1]
    output=args.output or root/'build/bus_server_bundles'/('comparison_'+stamp)
    output.mkdir(parents=True,exist_ok=False)
    rows=[];seen=set();files={}
    reference_images=None
    for b in args.bundle:
        manifest=json.loads((b/'manifest.json').read_text());name=manifest['candidate']
        if not re.fullmatch(r'opt[0-9]+_[a-z0-9_]+',name):raise ValueError('Invalid candidate directory')
        if name in seen:raise ValueError('Duplicate candidate')
        seen.add(name)
        actual={p.relative_to(b).as_posix() for p in b.rglob('*') if p.is_file()}
        if actual!=set(manifest['files_sha256'])|{'manifest.json'}:raise ValueError('Unlisted/missing bundle content')
        for p,h in manifest['files_sha256'].items():
            if not (b/p).resolve().is_relative_to(b.resolve()):raise ValueError('Escaping manifest path')
            if sha(b/p)!=h:raise ValueError('Changed bundle '+p)
        local=json.loads((b/'evidence/local_run.json').read_text())
        images={row['layer']:{k:v for k,v in row['input_sha256'].items() if k in ['shared.hex','expected.hex']} for row in local['layers']}
        if reference_images is None:reference_images=images
        elif reference_images!=images:raise ValueError('Comparison candidates use different task data/reference outputs')
        for p in b.rglob('*'):
            if p.is_file():files[name+'/'+p.relative_to(b).as_posix()]=p.read_bytes()
        rows.append(dict(candidate=name,runner_kind=manifest['runner_kind'],checker_top=manifest['checker']['top'],
                         bundle_manifest_sha256=sha(b/'manifest.json'),
                         standalone_zip_sha256=sha(b.parent/'qingyu_bus_bundle.zip')))
        files['verify_'+name+'.sh']=('#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\nexec python3 '+name+'/run_bus_server.py "$@"\n').encode()
    files['README.txt']=('Each candidate has its own immutable inputs and independent runner.\n'
                        'Run sh verify_<candidate>.sh --mode validate first.\n'
                        'Then --mode macro --activity for physical-memory functional validation.\n'
                        'Read each candidate README.md before assessment; real official libraries and full-SoC constraints are required.\n'
                        'No remote EDA or PPA acceptance is implied by this archive.\n').encode()
    files['run_comparison.sh']=('#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\n'+
        ''.join('sh verify_'+row['candidate']+'.sh "$@"\n' for row in rows)).encode()
    manifest=dict(schema='qingyu-bus-comparison-bundle-v2',created_utc=stamp,candidates=rows,
                  same_twelve_task_data=True,status='local packaging only; server validation and PPA pending',
                  files_sha256={p:hashlib.sha256(data).hexdigest() for p,data in files.items()})
    files['comparison_manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    archive=output/'qingyu_bus_comparison.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(files.items()):z.writestr('qingyu_bus_comparison/'+name,data)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('CRC failed')
    (output/'qingyu_bus_comparison.zip.sha256').write_text(sha(archive)+'  qingyu_bus_comparison.zip\n')
    (output/'comparison_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    launcher='''#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
archive="$base/qingyu_bus_comparison.zip"
printf '%s  %s\n' 'ARCHIVE_SHA256' "$archive" | sha256sum -c -
parent=${QINGYU_RUN_PARENT:-$HOME/Desktop}
test -d "$parent"
work=$(mktemp -d "$parent/qingyu_compare_XXXXXXXX")
unzip -q "$archive" -d "$work"
printf 'QINGYU_COMPARISON_DIRECTORY=%s\n' "$work/qingyu_bus_comparison"
exec sh "$work/qingyu_bus_comparison/run_comparison.sh" "$@"
'''.replace('ARCHIVE_SHA256',sha(archive))
    (output/'qb').write_text(launcher,newline='\n')
    print(archive);print('SHA256='+sha(archive))


if __name__=='__main__':main()
