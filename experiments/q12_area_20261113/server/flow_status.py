from pathlib import Path
import json,re,sys
root=Path('/tmp')
for pattern in ['q12_decoder_package_*/run.log','q12_audit_launcher_*/run.log','q12_full_launcher_*/run.log']:
 for p in root.glob(pattern):print('LAUNCH',p,'\n'+'\n'.join(p.read_text(errors='replace').splitlines()[-4:]))
for pattern in ['q12_decoder_window_*/result.json','q12_decoder_full_*/result.json']:
 for p in root.glob(pattern):
  r=json.loads(p.read_text());print('RESULT',p)
  print(json.dumps({k:r.get(k)for k in ['phase','error','mean_full_window_cycles','mean_energy_uj','mean_energy_uj_unqualified']}))
  for k,v in r.get('stages',{}).items():
   print(k,json.dumps({x:v[x]for x in ['metrics','tool_complete','passed','accepted','error','provisional_unqualified','worst_reported_setup_ns','worst_reported_hold_ns']if x in v}))
  for p2 in p.parent.glob('*/metrics.txt'):print(p2.parent.name,p2.read_text().strip())
for p in root.glob('q12_mode_audit_*/metrics.txt'):print('MODE_METRICS',p,'\n'+p.read_text())
if len(sys.argv)>1 and sys.argv[1]=='cpu':
 for p in root.glob('q12_mode_audit_*/cpu_path.rpt'):
  print('CPU_PATH',p)
  for line in p.read_text().splitlines():
   nums=re.findall(r'[-+]?\d+\.\d+',line)
   if any(t in line for t in ['Startpoint:','Endpoint:','Path Group:','data arrival','data required','slack','clock '])or(nums and max(map(float,nums[:-1]or nums))>0.15):print(line)
if len(sys.argv)>1 and sys.argv[1]=='corners':
 for p in root.glob('q12_mode_audit_*/identity.json'):
  r=json.loads(p.read_text())
  for k in ['available_standard_libraries','available_sram_libraries']:
   print(k);print('\n'.join(Path(s).name for s in r[k]))
