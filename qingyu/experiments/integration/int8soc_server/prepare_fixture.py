"""Derive explicit physical-port preload/readback fixtures from the SoC checker.

No manufacturer-private storage arrays are accessed by the physical fixture.
The original independently validated runtime scoreboard is retained.
"""
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Unexpected source fixture: '+old)
    return text.replace(old,new)

def activity(text):
    text=once(text,' integer input_words,output_words,layer;', ''' reg dump_enabled=0,activity_pending=0;
 string activity_path;
 initial if($value$plusargs("ACTIVITY=%s",activity_path))begin
  dump_enabled=1;$dumpfile(activity_path);$dumpvars(0,dut);$dumpoff;
 end
 integer input_words,output_words,layer;''')
    text=once(text,"dut.sysfio_icb_cmd_addr==32'hf0000008 && config_cycle<0)config_cycle=cycles;",'''dut.sysfio_icb_cmd_addr==32'hf0000008 && config_cycle<0)begin
     config_cycle=cycles;
     $display("QINGYU_ACTIVITY_START cycle=%0d time_ps=%0t",cycles,$realtime);
     if(dump_enabled)$dumpon;
    end''')
    text=once(text,'  cycles=cycles+1;', '''  cycles=cycles+1;
  // Include the final accepted ACK edge's complete clock interval. Thus VCD
  // duration equals (last_ack-config_cycle+1) actual bus clock periods.
  if(activity_pending)begin
   if(dump_enabled)$dumpoff;
   $display("QINGYU_ACTIVITY_END cycle=%0d time_ps=%0t marker_ack_cycle=%0d",cycles,$realtime,last_ack);
   activity_pending<=0;
  end''')
    return once(text,'        last_ack=cycles;', '        last_ack=cycles;activity_pending<=1;')

def main():
    source=(ROOT/'experiments/integration/int8soc/tb_int8soc.sv').read_text()
    behavior=activity(source)
    (HERE/'tb_int8soc_behavior.sv').write_text(behavior,newline='\n')
    text=once(behavior,'u_e203_itcm_gnrl_ram.u_sirv_sim_ram','u_e203_itcm_gnrl_ram.u_storage')
    text=once(text,' reg [63:0] firmware[0:8191];','''`define DTCM `CPU.u_e203_srams.u_e203_dtcm_ram.u_e203_dtcm_gnrl_ram.u_storage
`define SHARED dut.u_shared
 reg runtime_enabled=0,assessment_done=0;
 reg [31:0] shared_image[0:131071],shared_readback[0:131071];
 reg [16:0] shared_address=0;
 reg [12:0] itcm_address=0;
 reg [13:0] dtcm_address=0;
 reg [31:0] shared_din=0;
 reg [63:0] itcm_din=0;
 reg shared_cs=0,itcm_cs=0,dtcm_cs=0,shared_we=1,shared_reset=0,loader_clear=0;
 wire loader_read=!shared_we;
 wire [31:0] loader_address={13'h1400,shared_address,2'b00};
 integer preload_commands=0,preload_responses=0;
 reg [63:0] firmware[0:8191];''')
    old=(ROOT/'scripts/server_bus_bundle/fixtures/tb_macro.sv').read_text()
    helpers=old[old.index(' task attach_shared_loader;'):old.index(' reg [1023:0] fw_path')]
    helpers=once(helpers,'   force `SHARED.clk=clk;','   force `SHARED.cache_clear=loader_clear;\n   force `SHARED.clk=clk;')
    helpers=once(helpers,'   release `SHARED.rst_n; release `SHARED.clk;','   release `SHARED.cache_clear;\n   release `SHARED.rst_n; release `SHARED.clk;')
    text=once(text,' initial begin\n  if(!$value$plusargs("FIRMWARE=%s",firmware_path))',helpers+' initial begin\n  if(!$value$plusargs("FIRMWARE=%s",firmware_path))')
    text=once(text,'  for(i=0;i<8192;i=i+1)begin `ITCM.mem_r[i]=firmware[i];read_seen[i]=0;end','  for(i=0;i<8192;i=i+1)read_seen[i]=0;')
    text=once(text,"  for(i=0;i<131072;i=i+1)dut.u_shared.mem[i]=32'hcccccccc;","  for(i=0;i<131072;i=i+1)shared_image[i]=32'hcccccccc;")
    text=once(text,'  for(i=0;i<input_words;i=i+1)dut.u_shared.mem[65536+i]=source_image[i];','''  for(i=0;i<input_words;i=i+1)shared_image[65536+i]=source_image[i];
  attach_shared_loader;
  force `ITCM.clk=clk;force `ITCM.cs=itcm_cs;force `ITCM.we=1'b1;
  force `ITCM.addr=itcm_address;force `ITCM.din=itcm_din;force `ITCM.wem=8'hff;
  force `DTCM.clk=clk;force `DTCM.cs=dtcm_cs;force `DTCM.we=1'b1;
  force `DTCM.addr=dtcm_address;force `DTCM.din=32'b0;force `DTCM.wem=4'hf;
  repeat(4)@(negedge clk);shared_reset=1;
  for(i=0;i<131072;i=i+1)begin
   @(negedge clk);shared_cs=1;shared_address=17'(i);shared_din=shared_image[i];
   itcm_cs=i<8192;itcm_address=13'(i);itcm_din=i<8192?firmware[i]:64'b0;
   dtcm_cs=i<16384;dtcm_address=14'(i);
   preload_shared_word();
  end
  @(negedge clk);shared_cs=0;itcm_cs=0;dtcm_cs=0;
  @(posedge clk);#1;release_shared_loader;
  release `ITCM.cs;release `ITCM.we;release `ITCM.addr;release `ITCM.din;release `ITCM.wem;release `ITCM.clk;
  release `DTCM.cs;release `DTCM.we;release `DTCM.addr;release `DTCM.din;release `DTCM.wem;release `DTCM.clk;
  if(preload_commands!=131072||preload_responses!=131072)$fatal(1,"incomplete physical preload");
  $display("QINGYU_MACRO_PRELOAD_COMPLETE commands=%0d responses=%0d CPU_reset=%b",preload_commands,preload_responses,rst_n);''')
    text=once(text,'  rst_n=1;','  runtime_enabled=1;rst_n=1;')
    text=once(text,'if(dut.qingyu_bus_rst_n&&dut.u_fio.engine_done)','if(runtime_enabled&&!assessment_done&&dut.qingyu_bus_rst_n&&dut.u_fio.engine_done)')
    text=once(text,'  if(dut.qingyu_bus_rst_n)begin','  if(runtime_enabled&&!assessment_done&&dut.qingyu_bus_rst_n)begin')
    start=text.index('   if(host_valid)begin')
    end=text.index('  end\n  if(cycles>4000000)',start)
    final=text[start:end]
    text=text[:start]+text[end:]
    final=once(final,'   if(host_valid)begin',''' initial begin
    wait(host_valid===1'b1);assessment_done=1;
    if(host_code!==32'd1)$fatal(1,"physical INT8 firmware failed");
    @(negedge clk);shared_cs=0;shared_we=0;loader_clear=1;
    attach_shared_loader;
    repeat(2)@(negedge clk);loader_clear=0;
    for(integer word_index=0;word_index<131072;word_index++)begin
     read_shared_word(17'(word_index),readback_data);
     shared_readback[word_index]=readback_data;
    end
    @(negedge clk);shared_cs=0;
    @(posedge clk);#1;release_shared_loader;
    $display("QINGYU_MACRO_READBACK_COMPLETE words=131072 output_words=6385 source_words=%0d",input_words);''')
    final=final.replace('dut.u_shared.mem[','shared_readback[')
    final=final.replace('PASS real E203 INT8 packet task complete;','PASS real E203 INT8 physical packet task complete;')
    text=once(text,'endmodule',final+'endmodule\n`undef MAIN\n`undef CPU\n`undef ITCM\n`undef DTCM\n`undef SHARED')
    if '.mem[' in text or '.mem_r[' in text:raise ValueError('Physical fixture accesses a private memory array')
    (HERE/'tb_int8soc_macro.sv').write_text(text,newline='\n')
    print('Generated physical fixture with',text.count('$fatal'),'fatal checks')

if __name__=='__main__':main()
