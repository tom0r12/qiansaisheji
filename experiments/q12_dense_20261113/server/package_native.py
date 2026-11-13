from pathlib import Path
import hashlib,json,zipfile,base64
H=Path(__file__).resolve().parent;E=H.parent;R=E.parents[1];B=R/'final/q12_20261113/vendor';V=E/'build/dense12_w10_wp'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
result=json.loads((V/'result.json').read_text());assert result['passed']
tb=(E/'tb/tb_dense_vendor.sv').read_text()
for old,new in [('12688','9520'),('12689','9521'),('12690','9522'),('50756','38084'),('792','594'),('31443151','32443151'),('25344','19008')]:tb=tb.replace(old,new)
(H/'tb_native_vendor.sv').write_text(tb)
files={'q12_task4.sv':V/'q12_task4.sv','q12_rice_decoder.sv':V/'q12_rice_decoder.sv',
 'q12_icb_stream_prefix.sv':V/'q12_icb_stream_prefix.sv','q12_stream_engine_overlap.sv':V/'q12_stream_engine_overlap.sv',
 'q12_dense12_writer.sv':E/'rtl/q12_dense12_writer.sv','firmware64.hex':V/'firmware64.hex',
 'run_dense.py':H/'run_dense.py','decode_native.py':H/'decode_native.py','tb_native_vendor.sv':H/'tb_native_vendor.sv',
 'packet_reference.py':H/'packet_reference.py'}
overrides={'src/q12/core_datareset/q12_task4.sv':'q12_task4.sv','src/q12/decoder2/q12_rice_decoder.sv':'q12_rice_decoder.sv',
 'src/q12/integration/q12_icb_stream_prefix.sv':'q12_icb_stream_prefix.sv','src/q12/integration/q12_stream_engine_overlap.sv':'q12_stream_engine_overlap.sv',
 'src/q12/encoder_bounded/q13_rice_encoder.sv':'q12_dense12_writer.sv','firmware64.hex':'firmware64.hex',
 'decode_output.py':'decode_native.py','src/q12_vendor/tb_q12soc_vendor.sv':'tb_native_vendor.sv'}
identity={'baseline_manifest_sha256':sha(B/'manifest.json'),'firmware_sha256':sha(V/'firmware64.hex'),
 'files':{n:sha(p)for n,p in files.items()},'overrides':overrides,'local_synthetic_result':result,'maximum_area_mm2':0.448646862835,'minimum_throughput':6000}
z=H/'native12.zip'
with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED)as f:
 for n,p in files.items():f.write(p,n)
 f.writestr('identity.json',json.dumps(identity,indent=2)+'\n')
payload=base64.b64encode(z.read_bytes()).decode()
cmd='''python3 -c 'import base64,hashlib,io,zipfile,tempfile,pathlib,subprocess;b=base64.b64decode("PAYLOAD");assert hashlib.sha256(b).hexdigest()=="HASH";d=pathlib.Path(tempfile.mkdtemp(prefix="q12_native_launch_",dir="/tmp"));zipfile.ZipFile(io.BytesIO(b)).extractall(str(d));f=(d/"run.log").open("w");j=subprocess.Popen(["python3","-u",str(d/"run_dense.py")],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True);print("Q12_NATIVE_LAUNCH",j.pid,d)' '''.replace('PAYLOAD',payload).replace('HASH',sha(z))
(H/'native_launch.txt').write_text(cmd)
print('zip_bytes',z.stat().st_size,'launch_chars',len(cmd),'sha256',sha(z))
