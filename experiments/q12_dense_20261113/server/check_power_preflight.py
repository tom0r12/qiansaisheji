"""Diagnose the existing annotation preflight independently of Formality."""
from pathlib import Path
import hashlib,json,sys,time,traceback
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
root=list(Path('/tmp').glob('q12_native12_full_*/result.json'))
assert len(root)==1
root=root[0].parent
identity=json.loads((root/'derived_identity.json').read_text())
vendor_file=Path(identity['vendor_result']);vr=json.loads(vendor_file.read_text())
task=vr['tasks'][0];a=task['activity'];saif=vendor_file.parent/a['saif_relpath']
print('ROOT',root,'VENDOR_RESULT',vendor_file,flush=True)
print('ACTIVITY',a,flush=True)
print('SAIF',saif,'EXISTS',saif.is_file(),'BYTES',saif.stat().st_size if saif.exists()else None,flush=True)
print('SHA_MATCH',sha(saif)==a['saif_sha256'],flush=True)
sys.path.insert(0,str(root/'derived_inputs'))
import audit_reports,validate_activity
try:
 start=time.monotonic()
 r=validate_activity.check_saif(saif,a['start_ps'],a['end_ps'],audit_reports.macro_rows(root/'synth/macros_mapped.tsv'))
 print('PREFLIGHT_PASS',r,'SECONDS',time.monotonic()-start,flush=True)
except Exception:traceback.print_exc()
