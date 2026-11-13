"""Derive an auditable uncompressed-output candidate; never edit final/ inputs."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE=ROOT/'final/q12_20261113/vendor'
MAGIC=0x31443151
WORDS=17+16*792

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def replace(text,old,new,count=None):
    n=text.count(old)
    assert n and (count is None or n==count),(old,n,count)
    return text.replace(old,new)

def main():
    for d in ('rtl','firmware','tb','checks'): (HERE/d).mkdir(exist_ok=True)
    path=BASE/'src/q12/integration/q12_stream_engine_overlap.sv'
    text=path.read_text()
    start=text.index(' q13_rice_encoder encoder(')
    end=text.index('\n );',start)+len('\n );')
    text=text[:start]+''' q12_dense16_writer formatter(
  .clk(clk),.rst_n(pipe_rst_n),.start_valid(encoder_start_valid),.start_ready(encoder_start_ready),
  .in_valid(encoder_input),.in_ready(encoder_in_ready),.in_data(core_out_data),.in_last(core_out_index==9'd395),
  .out_valid(encoder_out_valid),.out_ready(encode_transfer&&wr_word_ready),.out_data(encoder_out_data),
  .out_last(encoder_out_last),.busy(encoder_busy),.done(encoder_done),.error(encoder_error),
  .total_cycles(encoder_cycles),.output_words(encoder_output_words)
 );
 assign encoder_valid_bits=6'd32;
 assign encoder_bits=32'd25344; // 1584 independent signed16 values per tile.
''' + text[end:]
    text=replace(text,'wr_desc_prefix=1;wr_desc_base=output_base+32\'d68+32\'(tile)*32\'d2584;wr_desc_count=646;',
                 'wr_desc_prefix=0;wr_desc_base=output_base+32\'d68+32\'(tile)*32\'d3168;wr_desc_count=792;',1)
    text=replace(text,'41412','50756',2)
    text=replace(text,'31593151','31443151',1)
    text=text.replace('encoder','formatter').replace('ENCODE_START','FORMAT_START').replace('encode_','format_').replace('encoding','formatting')
    # Avoid two formatter instance-name substitutions when replacing encoder.
    (HERE/'rtl/q12_stream_engine_overlap.sv').write_text(text)
    sw=ROOT/'final/q12_20261113/vendor/evidence/firmware_sources'
    for name in ('startup.S','linker.ld'):(HERE/'firmware'/name).write_bytes((sw/name).read_bytes())
    fw=ROOT/'final/q12_20261113/freeze_snapshot/output/eda/q12_candidate/loader_master/blocking_wait/soc/soc_main.c'
    c=replace(fw.read_text(),'0x31593151u','0x31443151u',1)
    c=replace(c,'output[i]==0||output[i]>20642u','output[i]!=25344u',1)
    (HERE/'firmware/soc_main.c').write_text(c)
    for name,p in [('behavioral',BASE/'evidence/tb_q12soc_behavioral.sv'),('vendor',BASE/'src/q12_vendor/tb_q12soc_vendor.sv')]:
        tb=p.read_text().replace('10352','12688').replace('10353','12689').replace('10354','12690').replace('41412','50756').replace('646','792').replace('31593151','31443151')
        tb=replace(tb,'output_words<18||output_words>12690','output_words!=12690',1)
        tb=replace(tb,'expected_writes=(slotword<int\'((expected[tile+1]+31)>>5))?1:0;', 'expected_writes=1;',1)
        tb=tb.replace('`ENG.encoder.','`ENG.formatter.')
        # Guard each header independently of the generated expected image.
        tb=replace(tb,'$readmemh(expected_path,expected);',
                   '$readmemh(expected_path,expected);\n  if(expected[0]!=32\'h31443151)$fatal(1,"dense format identity");\n  for(integer t=1;t<=16;t++)if(expected[t]!=25344)$fatal(1,"fixed dense length");',1)
        (HERE/'tb'/('tb_dense_'+name+'.sv')).write_text(tb)
    identity={'candidate':'q12_dense16_v1','baseline':'305648e85802afe19adf1570d79c9a7720feb7eb',
      'output_format':'signed13 sign-extended to signed16; tile-major 16 tiles of 99x16; no compression',
      'matrix_elements':25344,'matrix_bytes':50688,'allocation_words':WORDS,'writes_per_task':WORDS+1,
      'magic_hex':hex(MAGIC),'baseline_engine_sha256':sha(path),
      'candidate_sources':{str(p.relative_to(HERE)):sha(p) for d in ('rtl','firmware','tb') for p in (HERE/d).iterdir() if p.is_file()},
      'limits':{'minimum_tasks_per_s':6000,'preferred_tasks_per_s':6022.403340426386,'max_incremental_area_mm2':0.448646862835},
      'measured_throughput':None,'measured_area_mm2':None,'energy_uj':None,'timing_pass':None}
    (HERE/'identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    print('Prepared dense16 source and independent fixed-layout checks')
if __name__=='__main__':main()
