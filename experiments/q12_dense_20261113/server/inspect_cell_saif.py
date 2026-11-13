from pathlib import Path
import json,sys
f=list(Path('/tmp').glob('q12_cell_activity_*/result.json'));assert len(f)==1
r=json.loads(f[0].read_text());assert r['phase']=='activity_complete'
v=Path(r['vendor_result']);vr=json.loads(v.read_text());saif=v.parent/vr['tasks'][0]['activity']['saif_relpath']
original=list(Path('/tmp').glob('q12_native12_full_*/derived_inputs'));assert len(original)==1
sys.path.insert(0,str(original[0]));import audit_reports
launch=list(Path('/tmp').glob('q12_early_launch_*/saif_macro_bridge.py'));assert len(launch)==1
sys.path.insert(0,str(launch[0].parent));import saif_macro_bridge as b
macros=audit_reports.macro_rows(original[0].parent/'synth/macros_mapped.tsv')
text=saif.read_text();spans,_=b.instance_spans(text)
lookup={}
def normalized(s):return s.replace('\\','').replace('.','/')
for name in spans:lookup.setdefault(normalized(name),[]).append(name)
found=[];missing=[]
for target,ref,lib in macros:
 key='tb_q12soc/dut/'+target;m=lookup.get(normalized(key),[])
 if len(m)==1:found.append((target,m[0]))
 else:missing.append((target,m))
print('SOURCE',saif,'INSTANCES',len(spans),'MACROS',len(macros),'ONE_TO_ONE',len(found),'MISSING',len(missing))
print('EXAMPLES')
for target,source in found[:2]+found[-4:]:print('MAPPED',target,'\nSAIF',source)
print('MISSING',missing[:5])
try:
 overlay,audit=b.build_macro_overlay(text,macros);print('CURRENT_BRIDGE_PASS',audit['macro_count'])
except Exception as e:print('CURRENT_BRIDGE_ERROR',str(e))
for target,source in found[-1:]:
 a,z=spans[source];print('MACRO_BODY_BEGIN',text[a:min(a+1800,z)])
