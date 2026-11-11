"""Record/check exact code, fixed vectors and current verification artifacts.

The private PDK, downloaded dataset, virtualenv, tool packages and build caches
are not bundled. Their provenance is retained in the associated reports.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'reports/project_manifest.json'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def files_to_freeze():
    paths={ROOT/'README.md',ROOT/'.gitignore'}
    for folder in ['rtl','sw','scripts','constraints','docs']:
        paths.update(p for p in (ROOT/folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts)
    paths.update((ROOT/'model').glob('*.py'))
    paths.update((ROOT/'model').glob('requirements*.txt'))
    paths.update(p for p in (ROOT/'tb').glob('*') if p.is_file() and 'debug' not in p.name)
    final=ROOT/'model/full_v2_run'
    paths.update(p for p in (final/'validation_vectors').rglob('*') if p.is_file())
    paths.update([final/'reproducibility_manifest.json',final/'pipeline_status.json'])
    names=['checks.json','rtl_verilator_result.json','soc_verilator_result.json','soc_performance_result.json',
           'soc_synthetic_verilator_result.json','real_weight_rtl_smoke.json',
           'pdk_inventory.json','synthesis_summary.json','synthesis_area_units.json',
           'synthesis_mapped_netlist.v','gate_smoke.json','gate_smoke_comparison.json',
           'parallelism_study.json','verification_summary.json']
    paths.update(ROOT/'reports'/name for name in names)
    return sorted((p for p in paths if p.is_file()),key=lambda p:p.relative_to(ROOT).as_posix())

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if args.check:
        saved=json.loads(MANIFEST.read_text(encoding='utf-8'))
        failures=[]
        for name,entry in saved['files'].items():
            path=ROOT/name
            if not path.is_file() or digest(path)!=entry['sha256']:
                failures.append(name)
        current={p.relative_to(ROOT).as_posix() for p in files_to_freeze()}
        failures.extend(sorted(current-set(saved['files'])))
        if failures:
            print(json.dumps({'passed':False,'changed_or_missing':failures},indent=2))
            raise SystemExit(1)
        print(f'PASS frozen manifest: {len(saved["files"])} files match SHA256')
        return
    files={p.relative_to(ROOT).as_posix():{'sha256':digest(p),'bytes':p.stat().st_size}
           for p in files_to_freeze()}
    report={'kind':'FUNCTIONAL_ENGINEERING_BASELINE',
            'created_utc':datetime.now(timezone.utc).isoformat(),
            'official_contest_acceptance_complete':False,
            'source_pins':{'e203':'9f3e34f337f5d0a1236a285871ffa2032491617a',
                           'kwt':'237e4097afd4f6851e0b82f0a8d65c2dfe8eae30'},
            'excludes':['private PDK contents','dataset archive/audio',
                        'installed tools/virtualenv','build caches'],
            'files':files}
    MANIFEST.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f'Wrote {len(files)} file fingerprints: {MANIFEST}')

if __name__=='__main__': main()
