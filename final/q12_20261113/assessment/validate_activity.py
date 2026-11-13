"""Strict preflight for a source-matched exact-window whole-SoC SAIF; no PT launch."""
from pathlib import Path
from decimal import Decimal
import argparse,hashlib,json,re
UNIT_PS={'s':Decimal('1e12'),'ms':Decimal('1e9'),'us':Decimal('1e6'),'ns':Decimal('1e3'),'ps':Decimal(1),'fs':Decimal('.001')}
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(p.read_text())
def saif_instances(text):
    # Track instance hierarchy independently of NET/PORT/bit subexpressions.
    tokens=re.finditer(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+',text)
    stack=[];path=[];instances=set();expect_kind=False;expect_name=False
    for match in tokens:
        token=match.group()
        if token=='(':
            stack.append(False);expect_kind=True;expect_name=False
        elif token==')':
            if not stack:raise ValueError('unbalanced SAIF')
            if stack.pop():path.pop()
            expect_kind=False;expect_name=False
        elif expect_kind:
            expect_name=token=='INSTANCE';expect_kind=False
        elif expect_name:
            name=token[1:-1]if token.startswith('"')else token
            stack[-1]=True;path.append(name);instances.add('/'.join(path));expect_name=False
    if stack:raise ValueError('unbalanced SAIF end')
    return instances
def check_saif(saif,start_ps,end_ps,macro_rows,scope='tb_q12soc/dut'):
    text=saif.read_text(errors='replace')
    t=re.search(r'\(TIMESCALE\s+([\d.]+)\s+(fs|ps|ns|us|ms|s)\s*\)',text)
    d=re.search(r'\(DURATION\s+([\d.]+)\s*\)',text)
    if not t or not d:raise ValueError('Missing SAIF time header')
    duration=Decimal(d[1])*Decimal(t[1])*UNIT_PS[t[2]]
    if abs(duration-Decimal(end_ps-start_ps))>Decimal(1):raise ValueError('SAIF duration differs from exact full-window timestamps')
    instances=saif_instances(text)
    required=scope+'/u_e203_subsys_top/u_e203_subsys_main/u_mem_merge/u_original'
    if required not in instances:raise ValueError('Original custom merger activity hierarchy missing')
    expected={'RAMSP128X16':30,'RAMSP1024X16':6,'RAMSP4096X16':80};counts=dict.fromkeys(expected,0);missing=[]
    for name,ref,_lib in macro_rows:
        if ref not in counts:raise ValueError('Unexpected macro reference')
        counts[ref]+=1
        if scope+'/'+name not in instances:missing.append(name)
    if counts!=expected:raise ValueError('Mapped macro inventory is not30/6/80')
    if missing:raise ValueError('Macro SAIF paths mismatch; explicit reviewed mapping required: '+repr(missing[:8]))
    fixture_scope=scope+'/u_e203_subsys_top/u_e203_subsys_main/u_mem_merge/u_loader'
    return {'duration_ps':str(duration),'macro_instance_paths_matched':116,'simulation_only_loader_subtree_present':fixture_scope in instances,'original_merger_path':required,'note':'Instance presence does not prove port/net activity coverage; PT report_switching_activity/check_power remain mandatory.'}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',type=Path,required=True);p.add_argument('--vendor-bundle',type=Path,required=True)
    p.add_argument('--activity-run',type=Path,required=True);p.add_argument('--conversion-result',type=Path,required=True)
    p.add_argument('--mapped-macros',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();stage=read(a.stage/'manifest.json');vendor=read(a.vendor_bundle/'manifest.json');run=read(a.activity_run/'result.json');conversion=read(a.conversion_result)
    for n,h in stage['sources_sha256'].items():
        if sha(a.stage/n)!=h:raise ValueError('Mapping input source changed: '+n)
    if vendor['baseline_evidence']['sha256']!=stage['source_result_sha256']:raise ValueError('Vendor activity and hardware manifest derive from different SoC source records')
    if run['manifest_sha256']!=sha(a.vendor_bundle/'manifest.json'):raise ValueError('Different vendor bundle activity')
    if not run.get('passed')or not run.get('activity_requested')or run.get('activity_timestamp_precision_ps')!=1:raise ValueError('Exact-time successful activity run required')
    if not conversion.get('passed')or conversion['source_result_sha256']!=sha(a.activity_run/'result.json'):raise ValueError('SAIF conversion did not use same frozen activity result')
    rows=[tuple(x.split('\t'))for x in a.mapped_macros.read_text().splitlines()[1:]if x.strip()]
    if any(len(x)!=3 or '/'not in x[2]for x in rows):raise ValueError('Malformed/unlinked mapped macro table')
    tasks=[]
    for item in conversion['tasks']:
        source=[x for x in run['tasks']if x['task']==item['task']]
        if len(source)!=1:raise ValueError('Missing/duplicate activity task')
        task=source[0];act=task['activity'];cmd=item['command'];saif=Path(cmd[cmd.index('-output')+1]);vcd=Path(act['vcd'])
        if sha(saif)!=item['saif_sha256']or sha(vcd)!=item['vcd_sha256']:raise ValueError('Converted activity files changed')
        if item['start_ps']!=act['start_ps']or item['end_ps']!=act['end_ps']:raise ValueError('Conversion boundary changed')
        tasks.append(dict(task=item['task'],**check_saif(saif,act['start_ps'],act['end_ps'],rows)))
    if len(tasks)!=len(run['tasks']):raise ValueError('Incomplete task conversion')
    result={'passed':True,'scope':'source/time/instance-path preflight only; no annotated power or energy acceptance','tasks':tasks,'stage_manifest_sha256':sha(a.stage/'manifest.json'),'activity_result_sha256':sha(a.activity_run/'result.json'),'macro_table_sha256':sha(a.mapped_macros),'pending':['Actual mapped net/port toggle provenance and116macro power-pin coverage','Library unit/clock/timing/power reports','External loader hardware-boundary interpretation review']}
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(a.output)
if __name__=='__main__':main()
