"""Inspect real simulation/mapped SRAM instance naming; read-only."""
from pathlib import Path
import json,re,sys,csv
root=list(Path('/tmp').glob('q12_native12_full_*/result.json'))[0].parent
ident=json.loads((root/'derived_identity.json').read_text())
v=Path(ident['vendor_result']);r=json.loads(v.read_text());a=r['tasks'][0]['activity']
saif=v.parent/a['saif_relpath'];s=saif.read_text()
sys.path.insert(0,str(root/'derived_inputs'))
from validate_activity import saif_instances
instances=saif_instances(s)
def canonical(p):return p.replace('\\','').replace('].',']/')
lookup={}
for p in instances:lookup.setdefault(canonical(p),[]).append(p)
rows=list(csv.DictReader((root/'synth/macros_mapped.tsv').open(),delimiter='\t'))
missing=[];pairs=[]
for row in rows:
 target='tb_q12soc/dut/'+row['instance'];matches=lookup.get(canonical(target),[])
 if len(matches)!=1:missing.append((target,matches))
 else:pairs.append((target,matches[0]))
print('SOURCE_INSTANCES',len(instances),'MACROS',len(rows),'MATCHED',len(pairs),'MISSING',len(missing))
for p in pairs[:6]:print('MAPPING',p)
for p in missing[:6]:print('UNMATCHED',p)
macros=[p for p in sorted(instances)if p.endswith('macro_ram')]
print('SAIF_MACRO_EXAMPLES',macros[:5])
start=s.find('(INSTANCE macro_ram')
print('RAW_MACRO_SECTION',s[start:start+3500]if start>=0 else 'No unescaped literal macro_ram instance marker')
for p in Path('/tmp').glob('q12_native12_timing_*/synth/tool.log'):
 print('TIMING_TAIL',p,'\n'.join(p.read_text(errors='replace').splitlines()[-6:]))
