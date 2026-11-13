#!/usr/bin/env python3
"""Run from Linux/WSL. No proprietary tools, libraries, or task data required."""
from pathlib import Path
import collections
import hashlib
import json
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'checks'
BASE = ROOT / 'final/q12_20261113/vendor/src/q12/core_datareset'
FUNC = re.compile(r'function automatic logic \[12:0\] requantize\(.*?endfunction', re.S)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def stripped(text):
    text = re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)
    return re.sub(r'\s+', '', text)

def run(name, command):
    started = time.monotonic()
    with (OUT / name).open('w') as log:
        subprocess.run(command, cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=600)
    return {'command': command, 'seconds': time.monotonic()-started,
            'log': 'checks/'+name, 'log_sha256': sha(OUT/name)}

def main():
    OUT.mkdir(exist_ok=True)
    baseline = BASE / 'q12_task4.sv'
    candidate = HERE / 'rtl/q12_task4.sv'
    old, new = baseline.read_text(), candidate.read_text()
    expected = json.loads((HERE/'baseline.json').read_text())
    assert sha(baseline) == expected['source_sha256'], 'Changed frozen baseline'
    assert stripped(FUNC.sub('FUNCTION', old)) == stripped(FUNC.sub('FUNCTION', new)), 'Non-function RTL changed'
    modules=[]
    for name, source in [('quant_reference',old), ('quant_candidate',new)]:
        function = FUNC.findall(source)
        assert len(function)==1
        modules.append('module '+name+'(input signed [31:0] value,input [7:0] shift,output [12:0] y);\n'+
                       function[0]+'\nassign y=requantize(value,shift);\nendmodule\n')
    modules.append('module quant_miter(input signed [31:0] value,input [7:0] shift,output mismatch);\n'
                   'wire [12:0] a,b;quant_reference r(value,shift,a);quant_candidate c(value,shift,b);\n'
                   'assign mismatch=(a!=b);endmodule\n')
    (OUT/'quant_miter.sv').write_text(''.join(modules))
    result={'baseline_commit': expected['git_commit'], 'baseline_sha256':sha(baseline),
            'candidate_sha256':sha(candidate), 'control_pipeline_memory_unchanged':True,
            'area_mm2':None, 'energy_uj':None, 'full_soc_measured':False,
            'baseline_mean_cycles':expected['mean_cycles'],
            'candidate_cycle_equivalence':'unchanged sequential RTL plus exhaustive function equivalence',
            'tools':{}, 'checks':{}, 'generic_logic_cells':{}}
    for tool, arg in [('yosys','-V'),('verilator','--version')]:
        result['tools'][tool]=subprocess.check_output([tool,arg],text=True).strip()
    result['checks']['formal']=run('quant_equivalence.log', ['yosys','-Q','-T','-p',
        'read_verilog -sv checks/quant_miter.sv; prep -top quant_miter -flatten; '+
        'sat -prove mismatch 0 -verify -show-inputs -show-outputs'])
    assert 'SUCCESS!' in (OUT/'quant_equivalence.log').read_text()
    result['checks']['lint']=run('core_lint.log',['verilator','--lint-only','--timing','-Wall','--top-module',
        'q12_task4',str(candidate),str(BASE/'q12_pair_acc.sv'),str(BASE/'q12_striped_sram.sv')])
    for top in ('quant_reference','quant_candidate'):
        result['checks'][top]=run(top+'_synth.log',['yosys','-Q','-T','-p',
            'read_verilog -sv checks/quant_miter.sv; synth -top '+top+'; stat; write_json checks/'+top+'.json'])
        cells=json.loads((OUT/(top+'.json')).read_text())['modules'][top]['cells']
        result['generic_logic_cells'][top]={'total':len(cells),
            'by_type':dict(sorted(collections.Counter(c['type'] for c in cells.values()).items()))}
    counts=result['generic_logic_cells']
    result['generic_logic_reduction_percent']=100*(1-counts['quant_candidate']['total']/counts['quant_reference']['total'])
    result['passed']=True
    (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('passed','generic_logic_cells','generic_logic_reduction_percent')}))

if __name__=='__main__':
    main()
