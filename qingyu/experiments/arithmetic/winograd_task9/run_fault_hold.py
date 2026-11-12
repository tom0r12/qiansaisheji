"""Focused four-state metadata fault while output is already backpressured."""
from pathlib import Path
import hashlib,json,subprocess
from datetime import datetime,timezone

here=Path(__file__).resolve().parent;root=here.parents[2]
out=root/'build/winograd_task9_fault_hold'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
out.mkdir(parents=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
tb=here/'tb_winograd_task8.sv';src=tb.read_text()
old='if(nm<192) meta_data=meta_mem[nm];'
new='''if(nm<192) meta_data=meta_mem[nm];
                if(nm==191 && error_group==7) begin
                    if(!out_valid) meta_valid=0;
                    else begin force_output_stall=1;out_ready=0;end
                end'''
assert src.count(old)==1
src=src.replace(old,new)
start=src.index('        reset_block();\n        for(n=0;')
end=src.index('        $finish;',start)
src=src[:start]+'''        reset_block();
        load_case(0);error_group=7;meta_mem[191]=32'h00000030;
        target=completed+1;start_task();wait(error);
        repeat(20) @(posedge clk);
        if(!busy || done || !out_valid || !force_output_stall) $fatal(1,"Metadata fault revoked held output");
        @(negedge clk);force_output_stall=0;
        wait(completed==target);@(negedge clk);error_group=-1;run_case(0);
        if(errors!=1 || successful!=1 || error_held_contexts!=1 || stalled_cycles<20) $fatal(1,"Missing held-fault coverage");
        $display("PASS fault_hold error_held=%0d stalled=%0d checks=%0d recovery=%0d",error_held_contexts,stalled_cycles,checked_accumulators,successful);
'''+src[end:]
derived=out/'tb_fault_hold.sv';derived.write_text(src)
sources=[here/'winograd_int8_task8.sv',here.parent/'winograd_array8/winograd_int8_pair_acc32.sv',here/'tb_sram_write_poison.sv',tb,Path(__file__)]
before={str(p.relative_to(root)):sha(p) for p in sources}
commands=[([r'G:\iverilog\bin\iverilog.exe','-g2012','-s','tb_winograd_task8','-o',str(out/'sim.vvp'),str(derived),*[str(p) for p in sources[:3]]],'compile.log'),
          ([r'G:\iverilog\bin\vvp.exe','-i',str(out/'sim.vvp'),'+VECTORS=build/winograd_task8_vectors_20261112','+SEED=2371'],'sim.log')]
for argv,log in commands:
    with (out/log).open('w') as f:done=subprocess.run(argv,cwd=root,stdout=f,stderr=subprocess.STDOUT)
    if done.returncode:raise RuntimeError(str(out/log))
text=(out/'sim.log').read_text()
assert 'PASS fault_hold error_held=1' in text and 'FATAL' not in text
assert before=={str(p.relative_to(root)):sha(p) for p in sources}
report={'schema':'qingyu-task9-held-error-v1','passed':True,'source_sha256':before,'derived_tb_sha256':sha(derived),
        'commands':[a for a,b in commands],'sim_log_sha256':sha(out/'sim.log'),'scope':'final-group invalid metadata while outputvalid andready0,held20cycles,error drain,full fresh task reload;four-statewriteQpoison'}
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(text);print('RESULT',out/'result.json')
