"""Isolated four-macro reduction; never mutate the running native12 package."""
from pathlib import Path
import argparse,ast,base64,hashlib,io,json,zipfile
H=Path(__file__).resolve().parent;E=H.parent
ap=argparse.ArgumentParser();ap.add_argument('--metadata',action='store_true');a=ap.parse_args()
tag='c25'if a.metadata else'compact';macro128=24 if a.metadata else 26;total=macro128+86
B=E/'build/dense12_w10_wp';C=E/('build/dense12_w10_wp_m10'+('_c25'if a.metadata else''))
def sha(b):return hashlib.sha256(b).hexdigest()
def sub(s,a,b):
 assert s.count(a)==1,(a,s.count(a))
 return s.replace(a,b)
base=json.loads((B/'result.json').read_text());candidate=json.loads((C/'result.json').read_text())
assert base['passed']and candidate['passed']and len(candidate['tasks'])==12
assert base['tasks']==candidate['tasks'],'Storage-only change altered a complete task'
with zipfile.ZipFile(H/'native12.zip')as z:files={n:z.read(n)for n in z.namelist()}
old_identity=files.pop('identity.json');ident=json.loads(old_identity)
assert ident['files']['q12_task4.sv']=='15304c13c41e2c76f173d551130248676b4dfb075f9c523c0765f12763e6cd71'
assert ident['files']['run_dense.py']=='491bc0cb2d24ca7fb230c0bd5d70b545012d2b3a7272a8b71d8016cd32c89b8b'
for n,h in ident['files'].items():assert sha(files[n])==h,n
files['q12_task4.sv']=(C/'q12_task4.sv').read_bytes()
files['tb_native_vendor.sv']=sub(files['tb_native_vendor.sv'].decode(),'macro128_count!=30','macro128_count!=%d'%macro128).encode()
runner=files['run_dense.py'].decode()
runner=sub(runner,"prefix='q12_native12_'","prefix='q12_%s12_'"%tag)
anchor=" (P/'run_vendor.py').write_text(runner)"
insert=""" subst("{'RAMSP128X16':30,'RAMSP1024X16':6,'RAMSP4096X16':80,'total':116}",
       "{'RAMSP128X16':MACRO,'RAMSP1024X16':6,'RAMSP4096X16':80,'total':TOTAL}")
 m['baseline_expected_macro_instances']=m['expected_macro_instances']
 m['expected_macro_instances']={'RAMSP128X16':MACRO,'RAMSP1024X16':6,'RAMSP4096X16':80,'total':TOTAL}
""".replace('MACRO',str(macro128)).replace('TOTAL',str(total))
runner=sub(runner,anchor,insert+anchor)
anchor=" report.update(phase='activity_complete'"
insert=""" expected_cycles=[24560,24708,24725,24689,24686,24533,24710,24646,24802,24652,24778,24759]
 actual_cycles=[t['metrics']['full_window_cycles']for t in v['tasks']]
 assert actual_cycles==expected_cycles,'Storage-only change altered full-window cycles'
 report['cycles_identical_to_native12']=True
"""
runner=sub(runner,anchor,insert+anchor)
ast.parse(runner);files['run_dense.py']=runner.encode()
(H/('run_'+tag+'.py')).write_text(runner)
# Exercise the guarded vendor-runner transformations locally without fixtures.
start=runner.index(' runner=(P/');end=runner.index(" (P/'run_vendor.py').write_text",start)
part='\n'.join(s[1:]for s in runner[start:end].splitlines())
ns={'P':E.parents[1]/'final/q12_20261113/vendor','fw':ident['firmware_sha256'],'m':{'expected_macro_instances':{'RAMSP128X16':30,'RAMSP1024X16':6,'RAMSP4096X16':80,'total':116}}}
exec(part,ns);ast.parse(ns['runner']);assert "'total':%d"%total in ns['runner']
ident.update(files={n:sha(b)for n,b in files.items()},local_synthetic_result=candidate,
             parent_package_identity_sha256=sha(old_identity),private_weight_storage_bits=10,
             compact_c_minus_bias_metadata=a.metadata,
             expected_macro_instances={'RAMSP128X16':macro128,'RAMSP1024X16':6,'RAMSP4096X16':80,'total':total})
files['identity.json']=(json.dumps(ident,indent=2)+'\n').encode()
out=E/('candidates/native12_'+tag);out.mkdir(parents=True,exist_ok=True)
for n in ['q12_task4.sv','q12_rice_decoder.sv','q12_icb_stream_prefix.sv','q12_stream_engine_overlap.sv','q12_dense12_writer.sv','tb_native_vendor.sv']:(out/n).write_bytes(files[n])
check_path='checks/compact_metadata_weights/result.json'if a.metadata else'checks/compact_weights/result.json'
checks={'weight_storage':json.loads((E/check_path).read_text())}
assert checks['weight_storage']['source_sha256']==ident['files']['q12_task4.sv']
if a.metadata:checks['metadata_arithmetic']=json.loads((E/'checks/compact_metadata/result.json').read_text())
(out/'candidate.json').write_text(json.dumps({'status':'EXPERIMENTAL_NOT_PROMOTED','identity':ident,
 'local_output_and_cycle_equivalence':True,'checks':checks,
 'area_mm2':None,'energy_uj':None,'timing_pass':False,'official600_accuracy_pass':False},indent=2)+'\n')
changed=[n for n in files if n=='identity.json'or ident['files'][n]!=json.loads(old_identity)['files'][n]]
buf=io.BytesIO()
with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED)as z:
 for n in changed:z.writestr(n,files[n])
payload=base64.b64encode(buf.getvalue()).decode();digest=sha(buf.getvalue())
script='''import base64,hashlib,io,json,pathlib,shutil,tempfile,zipfile,subprocess
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
matches=[p.parent for p in pathlib.Path('/tmp').glob('q12_native_launch_*/identity.json')if sha(p)=='PARENT']
assert len(matches)==1,matches
d=pathlib.Path(tempfile.mkdtemp(prefix='q12_compact_launch_',dir='/tmp'))
for p in matches[0].iterdir():
 if p.is_file()and p.name!='run.log':shutil.copy2(str(p),str(d/p.name))
b=base64.b64decode('PAYLOAD');assert hashlib.sha256(b).hexdigest()=='DIGEST'
zipfile.ZipFile(io.BytesIO(b)).extractall(str(d))
i=json.loads((d/'identity.json').read_text())
for n,h in i['files'].items():assert sha(d/n)==h,n
f=(d/'run.log').open('w');p=subprocess.Popen(['python3','-u',str(d/'run_dense.py')],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
print('Q12_COMPACT_LAUNCH',p.pid,d)
'''.replace('PARENT',sha(old_identity)).replace('PAYLOAD',payload).replace('DIGEST',digest).replace('q12_compact_launch_','q12_'+tag+'_launch_')
ast.parse(script)
cmd="python3 -c 'import base64;exec(base64.b64decode(\""+base64.b64encode(script.encode()).decode()+"\"))'"
(H/(tag+'_launch.txt')).write_text(cmd)
print('PASS compact package guards; identical12 task outputs/cycles; command_chars',len(cmd),'identity',sha(files['identity.json']))
