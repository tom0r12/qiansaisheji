"""Four-state optional private-X macro mapping checks; run under WSL/Linux.

The local RAMSP models exercise the actual pin interface but are not vendor
models and provide no physical area, energy or timing evidence.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_frozen(core):
    manifest=json.loads((core/'SOURCE_SHA256.json').read_text())
    for name,h in manifest['files'].items():
        assert sha(core/name)==h,(core,name)
    for name,h in manifest.get('external_dependencies',{}).items():assert sha(ROOT/name)==h,name

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases',type=int,default=12)
    p.add_argument('--seed',type=int,default=2371)
    p.add_argument('--unit-only',action='store_true')
    a=p.parse_args()
    out=ROOT/'build/private_x_compact'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True)
    work=Path(tempfile.mkdtemp(prefix='qingyu_compact_x_'))
    models=ROOT/'build/bundle_template_checks/20261111T162200Z/local_functional_models.sv'
    assert sha(models)=='cd78caa3d3484f22d397b173e9c6a610c76939f53b7ff332a0dd55354bae9a33'
    wrapper=HERE/'qingyu_sram16.sv'
    report={'schema':'qingyu-private-x-compact-checks-v1','passed':False,'scope':'Local functional RAMSP stand-ins, four-state Icarus, strict wrapper lint; no foundry model/STA/PPA',
            'script_sha256':sha(Path(__file__)),'commands':[],'unit':[],'cores':[],
            'models_sha256':sha(models),'wrapper_sha256':sha(wrapper),'temporary_directory':str(work)}
    def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(argv,name,timeout=120,expect_success=True):
        print(name,flush=True)
        with (out/name).open('w') as f:r=subprocess.run(list(map(str,argv)),cwd=work,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
        report['commands'].append({'argv':list(map(str,argv)),'log':name,'returncode':r.returncode});save()
        if expect_success and r.returncode:raise RuntimeError(str(out/name))
        if not expect_success and not r.returncode:raise RuntimeError('Invalid configuration unexpectedly elaborated')
        return (out/name).read_text(errors='replace')
    save();print(out,flush=True)
    try:
        for words in (352,416):
            run(['verilator','--lint-only','--timing','-Wall','-Wno-DECLFILENAME','-Wno-UNUSEDSIGNAL',
                 '--top-module','qingyu_sram16','-GDEPTH=1024','-GADDR_W=10',f'-GX_VALID_WORDS={words}',wrapper,models],f'lint_{words}.log')
        binary=work/'unit.vvp'
        run(['iverilog','-g2012','-Wall','-s','tb_private_x_compact','-o',binary,wrapper,models,HERE/'tb_private_x_compact.sv'],'unit_compile.log')
        for seed in (2371,2477,2551):
            text=run(['vvp','-i',binary,f'+SEED={seed}'],f'unit_{seed}.log')
            match=re.search(r'^PASS private_x_compact (.+)$',text,re.M);assert match
            metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',match.group(1))}
            assert metrics['checks']==5380 and metrics['illegal352']>0 and metrics['illegal416']>0
            report['unit'].append({'seed':seed,'metrics':metrics})
        run(['iverilog','-g2012','-s','qingyu_sram16','-Pqingyu_sram16.DEPTH=1024','-Pqingyu_sram16.ADDR_W=10',
             '-Pqingyu_sram16.X_VALID_WORDS=351','-o',work/'invalid.vvp',wrapper,models],'unsupported_parameter.log',expect_success=False)
        if not a.unit_only:
            vectors=ROOT/'build/winograd_task8_vectors_20261112'
            vm=json.loads((vectors/'manifest.json').read_text());assert vm['completed'] and 1<=a.cases<=len(vm['cases'])
            for case in vm['cases']:
                for key,name in case['files'].items():assert sha(vectors/name)==case['sha256'][key]
            (work/'vectors').symlink_to(vectors,target_is_directory=True)
            report['vectors_manifest_sha256']=sha(vectors/'manifest.json')
            for name,words,rows,expected_cycles in [('winograd_task9',352,9,9355),('winograd_task8_prefetch',416,8,9931)]:
                core=ROOT/'experiments/arithmetic'/name;verify_frozen(core)
                sources=[core/'winograd_int8_task8.sv',ROOT/'experiments/arithmetic/winograd_array8/winograd_int8_pair_acc32.sv',
                         wrapper,models,core/'tb_winograd_task8.sv',HERE/'compact_core_monitor.sv']
                before={s.relative_to(ROOT).as_posix():sha(s) for s in sources}
                binary=work/(name+'.vvp')
                run(['iverilog','-g2012','-Wall',f'-DQINGYU_X_VALID_WORDS={words}',f'-DQINGYU_X_ROWS={rows}',
                     '-s','tb_winograd_task8','-s','compact_core_monitor','-o',binary,*sources],name+'_compile.log')
                elaboration=binary.read_text()
                counts={size:len(re.findall(r'\.scope module, "macro_ram" "RAMSP'+str(size)+'X16"',elaboration)) for size in (128,1024,4096)}
                assert counts=={128:rows*((words+127)//128)+21,1024:0,4096:0},counts
                text=run(['vvp','-i',binary,'+VECTORS='+str(work/'vectors'),f'+CASES={a.cases}',f'+SEED={a.seed}'],name+'_simulation.log',timeout=1800)
                match=re.search(r'^PASS task8 (.+)$',text,re.M);assert match
                metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',match.group(1))}
                assert metrics['real_or_synthetic_cases']==a.cases and metrics['successful']==a.cases+11,metrics
                tasks=[{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)} for line in text.splitlines() if line.startswith('TASK ')]
                assert tasks and all(t['cycles']==sum(t[k] for k in ['load','factor','cache','compute','store']) for t in tasks)
                assert tasks[0]['cycles']==expected_cycles,tasks[0]
                monitor=re.search(r'^COMPACT_CORE (.+)$',text,re.M);assert monitor
                verify_frozen(core);assert before=={s.relative_to(ROOT).as_posix():sha(s) for s in sources}
                report['cores'].append({'core':name,'valid_words_per_bank':words,'source_manifest_sha256':sha(core/'SOURCE_SHA256.json'),
                    'sources_sha256':before,'metrics':metrics,'tasks':tasks,'macro_instances':counts,
                    'monitor':{k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',monitor.group(1))}});save()
        assert sha(wrapper)==report['wrapper_sha256'] and sha(models)==report['models_sha256']
        report['passed']=True
    except Exception as e:report['error']=str(e);raise
    finally:
        report['logs_sha256']={s.name:sha(s) for s in out.glob('*.log')};save();print(out/'result.json',flush=True)

if __name__=='__main__':main()
