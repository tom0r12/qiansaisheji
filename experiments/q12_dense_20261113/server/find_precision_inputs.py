"""Read-only search for the original frozen calibration and float inputs."""
from pathlib import Path
import hashlib,json,os,time
roots=[Path.home(),Path('/tmp/q12_final_s4_36usr_20261113')]
expected='5029c9c202b30dd78353a1f4112f36ea354bca6c16e58232beb08634817f4dee'
skip={'.git','.cache','WORK','csrc','simv.daidir','smic_official','qingyu_sram_corners','node_modules'}
start=time.monotonic();seen=0;calibration=[];floats=[]
for root in roots:
 for directory,dirs,files in os.walk(str(root)):
  depth=len(Path(directory).relative_to(root).parts)
  dirs[:]=[n for n in dirs if n not in skip and not n.startswith('.') and depth<9]
  for name in files:
   seen+=1
   if name=='layer00.json':
    p=Path(directory)/name;digest=hashlib.sha256(p.read_bytes()).hexdigest()
    calibration.append({'path':str(p),'sha256':digest,'exact_frozen_config':digest==expected})
   if name=='layer00.npz':floats.append(str(Path(directory)/name))
  if seen>300000 or time.monotonic()-start>90:dirs[:]=[];break
print('PRECISION_INPUT_SEARCH',json.dumps({'files_seen':seen,'seconds':time.monotonic()-start,'calibration':calibration[:30],'float_archives':floats[:30]},sort_keys=True))
