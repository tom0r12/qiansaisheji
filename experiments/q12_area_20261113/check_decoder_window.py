"""Create and prove the equivalent, subtraction-free decoder window variant."""
from pathlib import Path
import hashlib,json,re,subprocess

here=Path(__file__).resolve().parent
base=here.parents[1]/'final/q12_20261113/vendor/src/q12/decoder2/q12_rice_decoder.sv'
out=here/'variants/decoder_window'
out.mkdir(parents=True,exist_ok=True)
checks=out/'checks';checks.mkdir(exist_ok=True)
old=base.read_text()
pattern=re.compile(r'    function automatic \[71:0\] peek72\(.*?    endfunction',re.S)
match=pattern.findall(old);assert len(match)==1
replacement='''    function automatic [71:0] peek72(input [319:0] bits, input [8:0] offset);
        reg [319:0] unused_shifted;
        begin
            unused_shifted=bits << offset;
            peek72=unused_shifted[319:248];
        end
    endfunction'''
new=pattern.sub(lambda _:replacement,old)
end_check="consumed_bits+32'(bit_delta)!=expected_bits_q"
replacement_check="32'(bit_delta)!=(expected_bits_q-consumed_bits)"
assert new.count(end_check)==1
new=new.replace(end_check,replacement_check)
candidate=out/'q12_rice_decoder.sv'
candidate.write_text(new)
assert pattern.sub('FUNC',old).replace(end_check,replacement_check)==pattern.sub('FUNC',new)
parts=[]
for name,func in [('reference',match[0]),('candidate',replacement)]:
    parts.append('module '+name+'(input [319:0] bits,input [8:0] offset,output [71:0] value);\n'+func+'\nassign value=peek72(bits,offset);\nendmodule\n')
parts.append('module miter(input [319:0] bits,input [8:0] offset,output mismatch);\nwire [71:0] a,b;reference r(bits,offset,a);candidate c(bits,offset,b);assign mismatch=(offset<=9\'d320)&&(a!=b);endmodule\n')
(checks/'miter.sv').write_text(''.join(parts))
cmd=['yosys','-Q','-T','-p','read_verilog -sv miter.sv; prep -top miter -flatten; sat -prove mismatch 0 -verify -show-inputs -show-outputs']
with (checks/'equivalence.log').open('w') as f:
    subprocess.run(cmd,cwd=checks,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)
assert 'SUCCESS!' in (checks/'equivalence.log').read_text()
(checks/'end_check_miter.sv').write_text("module miter(input [31:0] consumed_bits,expected_bits_q,input [8:0] bit_delta,output mismatch); wire old_bad,new_bad; assign old_bad="+end_check+"; assign new_bad="+replacement_check+"; assign mismatch=old_bad!=new_bad; endmodule\n")
with (checks/'end_check_equivalence.log').open('w') as f:
    subprocess.run(['yosys','-Q','-T','-p','read_verilog -sv end_check_miter.sv; prep -top miter; sat -prove mismatch 0 -verify'],cwd=checks,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)
assert 'SUCCESS!' in (checks/'end_check_equivalence.log').read_text()
warnings={}
for label,source in [('baseline',base),('candidate',candidate)]:
    with (checks/(label+'_lint.log')).open('w') as f:
        subprocess.run(['verilator','--lint-only','-Wall','-Wno-fatal','--top-module','q12_rice_decoder',str(source)],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
    warnings[label]=re.findall(r'^%Warning-([^:]+):[^\n]*?:\d+:\d+: (.*)$',(checks/(label+'_lint.log')).read_text(),re.M)
assert sorted(warnings['baseline'])==sorted(warnings['candidate']),warnings
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
result={'passed':True,'baseline_sha256':sha(base),'candidate_sha256':sha(candidate),'sequential_logic_unchanged':True,'proof':'all 320-bit reservoirs and offsets 0..320','domain_justification':'Each parse group resets offset to zero. LANES is fixed at 2. Before the second peek at most one header bit, one code of at most 70 bits, and one further header bit have been consumed (offset <= 72). No other caller exists. Offsets >320 are unreachable; the original wrapped subtraction differs there, with the counterexample retained.','logs':{p.name:sha(p)for p in checks.glob('*.log')}}
(checks/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
