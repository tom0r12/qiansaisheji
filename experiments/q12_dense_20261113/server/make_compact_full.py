"""Prepare a separately bound whole-SoC assessment for the smaller private RAM."""
from pathlib import Path
import argparse,ast,base64,hashlib,json,zlib
H=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--metadata',action='store_true');a=ap.parse_args()
tag='c25'if a.metadata else'compact'
record=json.loads((H.parent/('candidates/native12_'+tag+'/candidate.json')).read_text())
ident=record['identity']
source=(H/'run_native_full.py').read_text()
def sub(a,b,count=1):
 global source
 assert source.count(a)==count,(a,source.count(a))
 source=source.replace(a,b)
sub('15304c13c41e2c76f173d551130248676b4dfb075f9c523c0765f12763e6cd71',ident['files']['q12_task4.sv'],2)
sub('491bc0cb2d24ca7fb230c0bd5d70b545012d2b3a7272a8b71d8016cd32c89b8b',ident['files']['run_dense.py'])
source=source.replace('q12_native12_','q12_compact12_').replace('Q12_NATIVE','Q12_COMPACT')
sub("out=Path(tempfile.mkdtemp(prefix='q12_compact12_full_',dir='/tmp'))",'''# Keep only one of our full-SoC DC jobs active at a time.
print('WAITING_FOR_NATIVE12_SYNTHESIS',flush=True)
deadline=time.monotonic()+21600
while True:
 prior=[read(p)for p in Path('/tmp').glob('q12_native12_full_*/result.json')]
 assert len(prior)==1,prior
 if prior[0].get('stages',{}).get('synth',{}).get('tool_complete'):break
 if prior[0].get('phase')=='failed':raise RuntimeError('Native12 synthesis failed; diagnose before repeating')
 if time.monotonic()>deadline:raise TimeoutError('Previous synthesis has not completed')
 time.sleep(15)
out=Path(tempfile.mkdtemp(prefix='q12_compact12_full_',dir='/tmp'))''')
sub("'q12_x12_w10_y12_native_write_priority'","'q12_x12_w10_y12_native_write_priority_compact_weights'")
anchor="hw=read(package/'hardware/manifest.json')"
insert='''# Update exact expected macro counts in all independent checkers, retaining
# every source, path, unit, coverage, and formal equivalence gate.
changes={
 'audit.tcl':[('All 116 macros','All 112 macros'),('RAMSP128X16 30','RAMSP128X16 26'),('$stage 30 6 80','$stage 26 6 80')],
 'hardware/report_explicit_area.tcl':[('RAMSP128X16 30','RAMSP128X16 26')],
 'audit_reports.py':[("'RAMSP128X16':30","'RAMSP128X16':26"),('len(macros)!=116','len(macros)!=112')],
 'validate_activity.py':[("'RAMSP128X16':30","'RAMSP128X16':26"),('not30/6/80','not26/6/80'),("'macro_instance_paths_matched':116","'macro_instance_paths_matched':112"),('116macro','112macro')],
 'formal_audit.py':[("'RAMSP128X16': 30","'RAMSP128X16': 26"),('30/6/80','26/6/80')]
}
for name,pairs in changes.items():
 p=package/name;s=p.read_text()
 for a,b in pairs:
  assert a in s,(name,a);s=s.replace(a,b)
 p.write_text(s)
'''
sub(anchor,insert+anchor+"\nhw['baseline_expected_macros']=hw['expected_macros'];hw['expected_macros']={'RAMSP128X16':26,'RAMSP1024X16':6,'RAMSP4096X16':80}")
sub("'baseline_files':original['files'],'actual_files'","'baseline_files':original['files'],'macro_inventory_change':'Private weights only: 30/6/80 to 26/6/80; all checkers remain exact','actual_files'")
if a.metadata:
 source=source.replace('q12_compact12_','q12_c2512_')
 for old,new in [("'RAMSP128X16':26","'RAMSP128X16':24"),("'RAMSP128X16': 26","'RAMSP128X16': 24"),('RAMSP128X16 26','RAMSP128X16 24'),('$stage 26 6 80','$stage 24 6 80'),('26/6/80','24/6/80'),('All 112 macros','All 110 macros'),('len(macros)!=112','len(macros)!=110'),("'macro_instance_paths_matched':112","'macro_instance_paths_matched':110"),('112macro','110macro'),('Private weights only:','Private weights and C-bias metadata:'),('write_priority_compact_weights','write_priority_compact_weights_c25')]:
  assert old in source,old;source=source.replace(old,new)
 sub("out=Path(tempfile.mkdtemp(prefix='q12_c2512_full_',dir='/tmp'))",'''print('WAITING_FOR_COMPACT12_SYNTHESIS',flush=True)
deadline=time.monotonic()+21600
while True:
 prior=[read(p)for p in Path('/tmp').glob('q12_compact12_full_*/result.json')]
 assert len(prior)<=1,prior
 if prior and prior[0].get('stages',{}).get('synth',{}).get('tool_complete'):break
 if prior and prior[0].get('phase')=='failed':raise RuntimeError('Compact12 synthesis failed; diagnose before repeating')
 if time.monotonic()>deadline:raise TimeoutError('Previous compact synthesis has not completed')
 time.sleep(15)
out=Path(tempfile.mkdtemp(prefix='q12_c2512_full_',dir='/tmp'))''')
# Validate checker edits locally against the exact frozen source package.
part=source[source.index('changes={'):source.index("hw=read(package/'hardware/manifest.json')")]
import tempfile,shutil
baseline=H.parents[2]/'final/q12_20261113/assessment'
with tempfile.TemporaryDirectory()as d:
 package=Path(d)
 for name in ['audit.tcl','audit_reports.py','validate_activity.py','formal_audit.py','hardware/report_explicit_area.tcl']:
  (package/name).parent.mkdir(parents=True,exist_ok=True)
  shutil.copyfile(baseline/name,package/name)
 exec(part,{'package':package})
 for p in package.glob('*.py'):ast.parse(p.read_text())
ast.parse(source);(H/('run_'+tag+'_full.py')).write_text(source)
payload=base64.b64encode(zlib.compress(source.encode(),9)).decode()
cmd='''python3 -c 'import base64,zlib,tempfile,pathlib,subprocess;d=pathlib.Path(tempfile.mkdtemp(prefix="q12_compact_full_launch_",dir="/tmp"));p=d/"run.py";p.write_bytes(zlib.decompress(base64.b64decode("PAYLOAD")));f=(d/"run.log").open("w");j=subprocess.Popen(["python3","-u",str(p)],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True);print("Q12_COMPACT_FULL_LAUNCH",j.pid,d)' '''.replace('PAYLOAD',payload).replace('q12_compact_full_launch_','q12_'+tag+'_full_launch_')
(H/(tag+'_full_launch.txt')).write_text(cmd)
print('PASS compact assessment inventory transformations',hashlib.sha256(source.encode()).hexdigest(),'launch_chars',len(cmd))
