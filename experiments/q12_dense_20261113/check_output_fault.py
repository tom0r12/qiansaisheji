"""Full-SoC invalid-output identity injection, including downstream backpressure."""
from pathlib import Path
import hashlib,json,os,subprocess
H=Path(__file__).resolve().parent;B=H/'build/dense12_w10_wp_earlycheck';O=H/'checks/output_fault';O.mkdir(parents=True,exist_ok=True)
identity=json.loads((B/'build_identity.json').read_text())
source=B/'tb_dense.sv';text=source.read_text();assert text.count('if(host_valid)begin')==1
text=text.replace('if(host_valid)begin','if(host_valid && !fault_injected)begin')
fault=r'''
reg fault_injected=0;
integer fault_mode,guard;
initial begin
 if(!$value$plusargs("FAULTMODE=%d",fault_mode))fault_mode=0;
 guard=0;
 while(!(`ENG.formatter_input && (`ENG.formatter_in_ready == (fault_mode==0)))) begin
  @(negedge dut.qingyu_bus_clk);guard++;
  if(guard>800000)$fatal(1,"fault injection point not reached");
 end
 fault_injected=1;
 force `ENG.core_out_index=9'h1ff;
 #0.001;
 if(!`ENG.abort_now)$fatal(1,"bad identity failed to abort independently of ready");
 @(negedge dut.qingyu_bus_clk);
 release `ENG.core_out_index;
 if(!`ENG.error || `ENG.error_code!=8'h13)$fatal(1,"wrong error classification");
 guard=0;
 while(!`ENG.done)begin
  @(negedge dut.qingyu_bus_clk);guard++;
  if(guard>2000)$fatal(1,"error drain did not terminate");
 end
 if(`TRANS.busy||`TRANS.draining||commands!=responses)$fatal(1,"outstanding DMA not drained");
 if(dut.u_shared.mem[0]!=0||final_offered)$fatal(1,"failed task published valid matrix");
 $display("PASS output identity fault mode=%0d drain_cycles=%0d commands=%0d responses=%0d",fault_mode,guard,commands,responses);
 $finish;
end
'''
assert text.count('endmodule')==1
(O/'tb_fault.sv').write_text(text.replace('endmodule',fault+'\nendmodule'))
sources=[str(O/'tb_fault.sv')if Path(p)==source else p for p in identity['sources']]
flags=list(identity['flags']);flags[flags.index('--Mdir')+1]='/tmp/q12_output_fault_obj'
def run(cmd,log,cwd=None,timeout=900):
 with log.open('w')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=cwd,check=True,timeout=timeout)
run(['verilator',*flags,*sources],O/'compile.log')
compile_text=(O/'compile.log').read_text()
assert not any('Circular combinational logic:'in line and '.engine.'in line for line in compile_text.splitlines())
cases=[]
for mode in (0,1):
 args=['/tmp/q12_output_fault_obj/sim','+FAULTMODE='+str(mode),'+FIRMWARE='+os.path.relpath(B/'firmware64.hex',O),'+INPUT='+os.path.relpath(B/'case00/input.hex',O),'+EXPECTED='+os.path.relpath(B/'case00/expected.hex',O),'+INPUT_WORDS=5883','+OUTPUT_WORDS=9522','+LAYER=0']
 run(args,O/('mode%d.log'%mode),cwd=O,timeout=120)
 log=(O/('mode%d.log'%mode)).read_text();assert 'PASS output identity fault'in log
 cases.append({'mode':mode,'summary':next(x for x in log.splitlines()if x.startswith('PASS'))})
result={'passed':True,'engine_sha256':hashlib.sha256((B/'q12_stream_engine_overlap.sv').read_bytes()).hexdigest(),'normal_regression':json.loads((B/'result.json').read_text()),'fault_cases':cases,'scope':'Synthetic behavioral-SRAM full SoC error drain; not PPA'}
(O/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(cases))
