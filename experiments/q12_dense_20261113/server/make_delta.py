"""Small dependency repair copied into a fresh server package, never in-place."""
from pathlib import Path
import hashlib,json,zipfile,zlib,base64,subprocess,sys
H=Path(__file__).resolve().parent
with zipfile.ZipFile(H/'native12.zip')as z:old_identity=z.read('identity.json')
oldhash=hashlib.sha256(old_identity).hexdigest()
subprocess.run([sys.executable,str(H/'package_native.py')],check=True)
with zipfile.ZipFile(H/'native12.zip')as z:
 blobs={n:z.read(n).decode()for n in ['run_dense.py','packet_reference.py','identity.json']}
payload=base64.b64encode(zlib.compress(json.dumps(blobs).encode(),9)).decode()
source='''from pathlib import Path
import hashlib,json,tempfile,shutil,subprocess,base64,zlib
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
matches=[p.parent for p in Path('/tmp').glob('q12_native_launch_*/identity.json')if sha(p)=='OLDHASH']
assert len(matches)==1,matches
old=matches[0];prev=json.loads((old/'identity.json').read_text())
for n,h in prev['files'].items():assert sha(old/n)==h,n
new=json.loads(zlib.decompress(base64.b64decode('PAYLOAD')))
ident=json.loads(new['identity.json']);d=Path(tempfile.mkdtemp(prefix='q12_native_launch_',dir='/tmp'))
for n in ident['files']:
 if n in new:(d/n).write_text(new[n])
 else:shutil.copy2(str(old/n),str(d/n))
(d/'identity.json').write_text(new['identity.json'])
for n,h in ident['files'].items():assert sha(d/n)==h,n
f=(d/'run.log').open('w');p=subprocess.Popen(['python3','-u',str(d/'run_dense.py')],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
print('Q12_NATIVE_DEPENDENCY_REPAIR',p.pid,d)
'''.replace('OLDHASH',oldhash).replace('PAYLOAD',payload)
outer=base64.b64encode(zlib.compress(source.encode(),9)).decode()
(H/'native_delta_launch.txt').write_text('python3 -c \'import zlib,base64;exec(zlib.decompress(base64.b64decode("'+outer+'")))\'')
print('delta_launch_chars',len((H/'native_delta_launch.txt').read_text()))
