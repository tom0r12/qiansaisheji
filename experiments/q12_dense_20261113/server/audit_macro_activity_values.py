"""Cross-check recorded SRAM input activity against original SAIF numeric data.

This is independent of release-specific source attributes. A mismatch is kept,
never repaired by changing activity. It does not waive full-SoC power warnings.
"""
from pathlib import Path
import csv,hashlib,json,re,sys
deps=list(Path('/tmp').glob('q12_early_launch_*/saif_macro_bridge.py'));assert len(deps)==1
sys.path.insert(0,str(deps[0].parent));from saif_macro_bridge import TOKENS,instance_spans,canonical
def read(p):return json.loads(p.read_text())
def parse(text):
 stack=[];root=None
 for m in TOKENS.finditer('(BODY '+text+')'):
  t=m.group()
  if t=='(':
   x=[]
   if stack:stack[-1].append(x)
   else:root=x
   stack.append(x)
  elif t==')':stack.pop()
  else:stack[-1].append(t.replace('\\','').strip('"'))
 assert not stack
 return root
def ports(body):
 result={}
 for block in parse(body)[1:]:
  if not isinstance(block,list)or block[0]not in ('PORT','NET'):continue
  for x in block[1:]:
   if not isinstance(x,list):continue
   vals={z[0]:float(z[1])for z in x[1:]if isinstance(z,list)and len(z)==2 and z[0]in('T0','T1','TX','TZ','TC')}
   if all(k in vals for k in('T0','T1','TC')):
    if x[0]in result:assert result[x[0]]==vals
    result[x[0]]=vals
 return result
roots=[p for p in Path('/tmp').glob('q12_power_recovery_*/result.json')if read(p).get('windows')];assert len(roots)==1
root=roots[0].parent;r=read(roots[0]);parent=Path(r['parent']);vrec=read(parent/'vendor_completed.json');vf=Path(vrec['vendor_result']);v=read(vf)
report={'phase':'activity_values_audit','scope':'SAIF-to-PT SRAM input values only; full-SoC warnings remain open','accepted':False,'windows':[]}
print('\033[2J\033[H',end='');print('     ORIGINAL SAIF versus PT SRAM INPUT VALUES')
for w in r['windows']:
 layer=w['layer'];cwd=root/('layer%02d'%layer);act=v['tasks'][layer]['activity'];saif=vf.parent/act['saif_relpath']
 assert hashlib.sha256(saif.read_bytes()).hexdigest()==w['saif_sha256']
 text=saif.read_text();spans,_=instance_spans(text);mapped={canonical(k):b for k,b in spans.items()};cache={};bad=[];matched=0
 rows=list(csv.DictReader((cwd/'macro_pin_activity.tsv').open(),delimiter='\t'))
 for row in rows:
  inst=canonical(row['instance']);pin=canonical(row['pin']).rsplit('/',1)[-1]
  if inst not in cache:
   a,b=mapped['tb_q12soc/dut/'+inst];cache[inst]=ports(text[a:b])
  p=cache[inst].get(pin)
  if p is None:bad.append({'pin':row['pin'],'reason':'no exact raw SAIF pin'});continue
  dur=act['duration_ps'];expected=(p['TC']*1000/dur,p['T1']/dur)
  actual=(float(row['toggle_rate']),float(row['static_probability']))
  close=all(abs(x-y)<=max(1e-6,abs(y)*2e-5)for x,y in zip(actual,expected))
  if close:matched+=1
  else:bad.append({'pin':row['pin'],'expected_rate_probability':expected,'actual_rate_probability':actual,'saif':p})
 rec={'layer':layer,'macros':len(cache),'input_rows':len(rows),'matched_values':matched,'mismatches':len(bad),'examples':bad[:8]}
 report['windows'].append(rec);print('     '+json.dumps({k:v for k,v in rec.items()if k!='examples'}),flush=True)
 if bad:print('     FIRST_MISMATCH '+json.dumps(bad[0]),flush=True)
report['accepted']=len(report['windows'])==12 and all(w['macros']==116 and w['mismatches']==0 for w in report['windows'])
report['phase']='complete';(root/'macro_value_audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('     ALL_12_MACRO_VALUE_AUDIT_ACCEPTED',report['accepted'],flush=True)
print('     FORMAL RESULT',json.dumps(read(parent/'formal/result.json')),flush=True)
for name in ('status.rpt','unmatched_after_verify.rpt','unmatched_black_boxes_after_verify.rpt','dont_verify.rpt','constants.rpt'):
 p=parent/'formal'/name
 print('     FORMAL_FILE',name,flush=True)
 if p.exists():
  lines=[x for x in p.read_text(errors='replace').splitlines()if x.strip()]
  for line in lines[:45]:print('     '+line,flush=True)
  print('     TOTAL_LINES',len(lines),flush=True)
