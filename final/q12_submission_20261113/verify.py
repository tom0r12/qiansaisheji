"""Verify the frozen public source package without executing EDA tools."""
from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent
for name in ('FREEZE_MANIFEST.json','DELIVERY_SHA256.json'):
    p=H/name
    if not p.exists():
        if name=='DELIVERY_SHA256.json':continue
        raise FileNotFoundError(p)
    m=json.loads(p.read_text())
    for rel,want in m['files_sha256'].items():
        q=H/rel
        assert q.is_file() and hashlib.sha256(q.read_bytes()).hexdigest()==want,rel
    print('PASS',name,len(m['files_sha256']),'files')
f=json.loads((H/'filelist.json').read_text())
assert all((H/s).is_file()for s in f['source_order'])
print('PASS source order; integrity check only, no EDA or acceptance claim')
