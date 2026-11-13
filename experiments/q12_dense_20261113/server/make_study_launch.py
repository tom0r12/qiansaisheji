from pathlib import Path
import base64,hashlib,zlib
h=Path(__file__).resolve().parent;r=h.parents[2]
p=h/'analyze_bandwidth.py'
s=p.read_text().replace("'BASE_HASH'",repr(hashlib.sha256((r/'final/q12_20261113/vendor/manifest.json').read_bytes()).hexdigest()))
b=base64.b64encode(zlib.compress(s.encode(),9)).decode()
cmd='''python3 -c 'import base64,zlib,tempfile,pathlib,subprocess;d=pathlib.Path(tempfile.mkdtemp(prefix="q12_bandwidth_",dir="/tmp"));p=d/"run.py";p.write_bytes(zlib.decompress(base64.b64decode("PAYLOAD")));f=(d/"run.log").open("w");j=subprocess.Popen(["python3","-u",str(p)],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True);print(j.pid,d)' '''.replace('PAYLOAD',b)
(h/'bandwidth_launch.txt').write_text(cmd)
print('launch chars',len(cmd))
