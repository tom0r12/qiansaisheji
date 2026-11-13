"""Encode a reviewed helper as one VNC clipboard command."""
from pathlib import Path
import argparse,ast,base64,zlib
ap=argparse.ArgumentParser()
ap.add_argument('source',type=Path)
ap.add_argument('destination',type=Path)
ap.add_argument('--detached-prefix')
ap.add_argument('--dependency',type=Path,action='append',default=[])
a=ap.parse_args()
raw=a.source.read_bytes();ast.parse(raw)
b64=base64.b64encode(zlib.compress(raw,9)).decode()
if a.detached_prefix:
 assert a.detached_prefix.isidentifier()
 body=('import base64,zlib,tempfile,pathlib,subprocess;'
       'd=pathlib.Path(tempfile.mkdtemp(prefix="'+a.detached_prefix+'_",dir="/tmp"));'
       +''.join('(d/"'+p.name+'").write_bytes(zlib.decompress(base64.b64decode("'+base64.b64encode(zlib.compress(p.read_bytes(),9)).decode()+'")));'for p in a.dependency)+
       'p=d/"run.py";p.write_bytes(zlib.decompress(base64.b64decode("'+b64+'")));'
       'f=(d/"run.log").open("w");'
       'j=subprocess.Popen(["python3","-u",str(p)],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True);'
       'print("Q12_LAUNCH",j.pid,d)')
else:
 assert not a.dependency,'Dependencies require a detached directory'
 body='import base64,zlib;exec(zlib.decompress(base64.b64decode("'+b64+'")))'
assert "'" not in body
a.destination.write_text("python3 -c '"+body+"'",encoding='utf-8')
print('WROTE',a.destination,'chars',len(body)+13)
