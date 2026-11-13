"""Freeze the single-line feedback fix without changing the measured parent."""
from pathlib import Path
import hashlib,json,shutil
H=Path(__file__).resolve().parent;source=H/'candidates/native12';target=H/'candidates/native12_earlycheck'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
parent=json.loads((source/'candidate.json').read_text())
for n,h in parent['source_sha256'].items():assert sha(source/n)==h,n
assert not target.exists(),'Refuse to overwrite a frozen candidate'
target.mkdir()
for name in parent['source_sha256']:shutil.copy2(source/name,target/name)
p=target/'q12_stream_engine_overlap.sv';data=p.read_text();old='wire invalid_core_output=formatter_input && formatter_in_ready &&';assert data.count(old)==1
p.write_text(data.replace(old,'wire invalid_core_output=formatter_input &&'),newline='\n')
reg=json.loads((H/'build/dense12_w10_wp_earlycheck/result.json').read_text());previous=parent['evidence']['synthetic_soc12']
assert reg['passed']and [t['cycles']for t in reg['tasks']]==[t['cycles']for t in previous['tasks']]
fault=json.loads((H/'checks/output_fault/result.json').read_text());assert fault['passed']
assert sha(p)==fault['engine_sha256']
record={'candidate':'q12_native12_early_output_identity_check','status':'EXPERIMENTAL_NOT_PROMOTED','parent_manifest_sha256':sha(source/'candidate.json'),
 'source_sha256':{n:sha(target/n)for n in parent['source_sha256']},'change':'Validate a presented output identity independently of formatter ready; breaks ready->abort->ready combinational feedback without delaying legal transactions.',
 'unchanged':['Numeric rules and fixed signed12 output format','Full matrix writeback','32-bit original System Bus and shared SRAM access','Firmware and task windows'],
 'output':parent['output'],'numeric_transform':parent['numeric_transform'],'requirements':parent['requirements'],
 'synthetic_soc12':reg,'synthetic_faults':fault['fault_cases'],'server_result':None,'timing_pass':False,'official600_accuracy_pass':False,'energy_uj':None}
(target/'candidate.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
print('FROZEN',target,'ENGINE',sha(p))
