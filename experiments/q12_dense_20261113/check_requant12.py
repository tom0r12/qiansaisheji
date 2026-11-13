"""Exhaustive 32-bit accumulator / 8-bit shift proof for signed12 saturation."""
from pathlib import Path
import re,subprocess,json,hashlib
H=Path(__file__).resolve().parent;R=H.parents[1];O=H/'checks';O.mkdir(exist_ok=True)
baseline=R/'final/q12_20261113/vendor/src/q12/core_datareset/q12_task4.sv'
candidate=H/'candidates/native12/q12_task4.sv'
pattern=r'function automatic logic \[12:0\] requantize\(.*?endfunction'
ref=re.search(pattern,baseline.read_text(),re.S)[0]
ref=ref.replace("34'sd4095","34'sd2047").replace("34'sd4096","34'sd2048").replace("13'hfff","13'h7ff").replace("13'h1000","13'h1800")
new=re.search(pattern,candidate.read_text(),re.S)[0]
text=''
for name,func in [('reference',ref),('candidate',new)]:
 text+='module '+name+'(input signed[31:0] value,input[7:0] shift,output[12:0] y);\n'+func+'\nassign y=requantize(value,shift);endmodule\n'
text+='module miter(input signed[31:0] value,input[7:0] shift,output mismatch);wire[12:0]a,b;reference r(value,shift,a);candidate c(value,shift,b);assign mismatch=(a!=b)||(b[12]!=b[11]);endmodule\n'
(O/'requant12_miter.sv').write_text(text)
with(O/'requant12_proof.log').open('w')as f:
 subprocess.run(['yosys','-Q','-T','-p','read_verilog -sv '+str(O/'requant12_miter.sv')+'; prep -top miter -flatten; sat -prove mismatch 0 -verify -show-inputs -show-outputs'],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
assert 'SUCCESS!' in(O/'requant12_proof.log').read_text()
r={'passed':True,'accumulator_bits':32,'shift_bits':8,'all_bit_patterns':True,'signed12_sign_extension':True,'candidate_source_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest()}
(O/'requant12_result.json').write_text(json.dumps(r,indent=2)+'\n');print(r)
