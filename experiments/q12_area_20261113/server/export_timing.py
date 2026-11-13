"""Export only this candidate's reports and the identified baseline reports."""
from pathlib import Path
import hashlib, json, re, shutil, zipfile

expected = '3e53fea269dd62c23642b7bb397234eba0809338061301dbbfe193ba44735c17'
selected = []
for path in Path('/tmp').glob('q12_area_full_*/result.json'):
    result = json.loads(path.read_text())
    if result.get('candidate_sha256') == expected and result.get('compile_complete'):
        selected.append(path.parent)
assert len(selected) == 1, selected
candidate = selected[0]
print('CANDIDATE', candidate)
text = (candidate / 'synth/timing_max.rpt').read_text()
seen = set()
for part in text.split('  Startpoint:')[1:]:
    section = '  Startpoint:' + part
    slack = re.search(r'slack\s*\([^)]*\)\s*([-+\d.]+)', section)
    if not slack or float(slack[1]) >= 0:
        continue
    group = re.search(r'Path Group:\s*(\S+)', section)
    key = group[1] if group else 'unknown'
    if key in seen:
        continue
    seen.add(key)
    print('\nFIRST_VIOLATION', key)
    print(section)
roots = [('candidate', candidate)]
baseline_root = Path('/tmp/q12_final_s4_36usr_20261113')
for path in baseline_root.glob('qingyu_q12_final_assessment_*/result.json'):
    roots.append(('baseline_' + path.parent.name, path.parent))
archive = Path('/tmp/q12_timing_evidence_20261113.zip')
with zipfile.ZipFile(str(archive), 'w', zipfile.ZIP_DEFLATED) as z:
    for label, root in roots:
        for p in sorted(root.rglob('*')):
            rel = p.relative_to(root)
            if p.is_file() and (len(rel.parts) == 1 and p.suffix in ('.json','.txt') or
                rel.parts[0] in ('synth','formal') and p.suffix in ('.rpt','.txt','.json','.tsv','.sdc','.log')):
                if p.stat().st_size < 30_000_000:
                    z.write(str(p), label + '/' + rel.as_posix())
target = Path.home()/'Desktop'/archive.name
shutil.copy2(str(archive), str(target))
print('EXPORT',target,archive.stat().st_size,hashlib.sha256(archive.read_bytes()).hexdigest())
