"""Independent interval and bit-vector proof for the C-bias metadata word."""
from pathlib import Path
import hashlib,json,subprocess
H=Path(__file__).resolve().parent;O=H/'checks/compact_metadata';O.mkdir(parents=True,exist_ok=True)
# Integer products attain extrema at endpoints of the signed10 interval.
products=[a*b for a in(-512,511)for b in(-512,511)]
cmin,cmax=32*min(products),32*max(products)
bmin,bmax=-(1<<21),(1<<21)-1
lo,hi=cmin-bmax,cmax-bmin
assert -(1<<24)<=lo<=hi<(1<<24)
proof='''module miter(input signed[28:0] c,r,input signed[21:0] bias,
input signed[30:0] pair_sum,input[7:0] shift,output legal,output mismatch);
wire signed[28:0] delta=c-{{7{bias[21]}},bias};
wire[31:0] word={1'b0,shift[5:0],delta[24:0]};
wire signed[28:0] restored={{4{word[24]}},word[24:0]};
wire[7:0] restored_shift={2'b0,word[30:25]};
wire signed[31:0] original={pair_sum[30],pair_sum}-{{3{r[28]}},r}-{{3{c[28]}},c}+{{10{bias[21]}},bias};
wire signed[31:0] compact={pair_sum[30],pair_sum}-{{3{r[28]}},r}-{{3{restored[28]}},restored};
assign legal=(c>=-29'sd8372224)&&(c<=29'sd8388608)&&(shift<=47);
assign mismatch=(original!=compact)||(shift!=restored_shift)||(delta!=restored);
endmodule
'''
(O/'miter.sv').write_text(proof)
with(O/'proof.log').open('w')as f:
 subprocess.run(['yosys','-Q','-T','-p','read_verilog -sv '+str(O/'miter.sv')+'; prep -top miter -flatten; sat -set legal 1 -prove mismatch 0 -verify'],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)
assert 'SUCCESS!'in(O/'proof.log').read_text()
rec={'passed':True,'c_bounds':[cmin,cmax],'accepted_bias_bounds':[bmin,bmax],'stored_c_minus_bias_bounds':[lo,hi],
 'storage_bits':25,'shift_bits':6,'additional_RAMSP128X16_removed':2,'arithmetic_proof':'Yosys SAT: equal corrected int32 result and restored shift for all legal C, all signed22 bias, signed31 pair_sum, signed29 R and shifts0..47',
 'scope':'Metadata arithmetic contract; whole-SoC integration is separately tested',
 'transform_sha256':hashlib.sha256((H/'compact_metadata.py').read_bytes()).hexdigest()}
(O/'result.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(rec))
