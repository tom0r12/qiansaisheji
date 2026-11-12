`timescale 1ns/1ps
`include "e203_defines.v"
module tb_int8soc;
 reg clk=0,lfclk=0,rst_n=0;
 always #3.333333 clk=~clk;
 always #15258.789 lfclk=~lfclk;
 wire host_valid;wire [31:0] host_code;
 qingyu_e203_soc_top dut(
  .qingyu_host_valid(host_valid),.qingyu_host_code(host_code),
  .hfextclk(clk),.hfxoscen(),.lfextclk(lfclk),.lfxoscen(),
  .io_pads_jtag_TCK_i_ival(1'b0),.io_pads_jtag_TMS_i_ival(1'b1),.io_pads_jtag_TDI_i_ival(1'b0),
  .io_pads_gpioA_i_ival(32'b0),.io_pads_gpioB_i_ival(32'b0),
  .io_pads_qspi0_dq_0_i_ival(1'b1),.io_pads_qspi0_dq_1_i_ival(1'b1),
  .io_pads_qspi0_dq_2_i_ival(1'b1),.io_pads_qspi0_dq_3_i_ival(1'b1),
  .io_pads_aon_erst_n_i_ival(rst_n),.io_pads_dbgmode0_n_i_ival(1'b1),
  .io_pads_dbgmode1_n_i_ival(1'b1),.io_pads_dbgmode2_n_i_ival(1'b1),
  .io_pads_bootrom_n_i_ival(1'b0),.io_pads_aon_pmu_dwakeup_n_i_ival(1'b1)
 );
`define MAIN dut.u_e203_subsys_top.u_e203_subsys_main
`define CPU `MAIN.u_e203_cpu_top
`define ITCM `CPU.u_e203_srams.u_e203_itcm_ram.u_e203_itcm_gnrl_ram.u_sirv_sim_ram
 reg [63:0] firmware[0:8191];
 reg [31:0] expected[0:6384],source_image[0:8191];
 reg [31:0] q_addr[0:32767],q_data[0:32767];
 reg q_read[0:32767];
 integer read_seen[0:8191],write_seen[0:6384];
 reg dump_enabled=0,activity_pending=0;
 string activity_path;
 initial if($value$plusargs("ACTIVITY=%s",activity_path))begin
  dump_enabled=1;$dumpfile(activity_path);$dumpvars(0,dut);$dumpoff;
 end
 integer input_words,output_words,layer;
 integer cycles=0,config_cycle=-1,start_cycle=-1,first_read=-1,last_ack=-1,done_cycle=-1;
 integer commands=0,responses=0,reads=0,writes=0,read_responses=0,write_responses=0;
 integer fabric_commands=0,shared_commands=0,shared_responses=0,clear_count=0,peak_pending=0;
 integer macro_reads=0,macro_writes=0;
 integer i,index,tile,slotword,needed,expected_writes,mismatches;
 reg invalidation_acked=0,final_offered=0;
 reg dma_held=0;reg [68:0] held_payload;
 reg [1023:0] firmware_path,input_path,expected_path;
 initial begin
  if(!$value$plusargs("FIRMWARE=%s",firmware_path))$fatal(1,"missing FIRMWARE");
  if(!$value$plusargs("INPUT=%s",input_path))$fatal(1,"missing INPUT");
  if(!$value$plusargs("EXPECTED=%s",expected_path))$fatal(1,"missing EXPECTED");
  if(!$value$plusargs("INPUT_WORDS=%d",input_words))$fatal(1,"missing INPUT_WORDS");
  if(!$value$plusargs("OUTPUT_WORDS=%d",output_words))$fatal(1,"missing OUTPUT_WORDS");
  if(!$value$plusargs("LAYER=%d",layer))layer=0;
  if(input_words<202||input_words>8192||output_words<17||output_words>6385)$fatal(1,"invalid fixture bounds");
  $readmemh(firmware_path,firmware);$readmemh(input_path,source_image,0,input_words-1);$readmemh(expected_path,expected);
  for(i=0;i<8192;i=i+1)begin `ITCM.mem_r[i]=firmware[i];read_seen[i]=0;end
  for(i=0;i<6385;i=i+1)write_seen[i]=0;
  for(i=0;i<131072;i=i+1)dut.u_shared.mem[i]=32'hcccccccc;
  for(i=0;i<input_words;i=i+1)dut.u_shared.mem[65536+i]=source_image[i];
  repeat(8)@(negedge lfclk);
  rst_n=1;
 end
 // This monitor observes the actual bus clock, not an inferred core cadence.
 // done is registered on the preceding rising edge; sample it after NBA.
 always @(negedge dut.qingyu_bus_clk)if(dut.qingyu_bus_rst_n&&dut.u_fio.engine_done)done_cycle=cycles;
 always @(posedge dut.qingyu_bus_clk)begin
  cycles=cycles+1;
  // Include the final accepted ACK edge's complete clock interval. Thus VCD
  // duration equals (last_ack-config_cycle+1) actual bus clock periods.
  if(activity_pending)begin
   if(dump_enabled)$dumpoff;
   $display("QINGYU_ACTIVITY_END cycle=%0d time_ps=%0t marker_ack_cycle=%0d",cycles,$realtime,last_ack);
   activity_pending<=0;
  end
  if(dut.qingyu_bus_rst_n)begin
   if(dut.sysfio_icb_cmd_valid&&dut.sysfio_icb_cmd_ready&&!dut.sysfio_icb_cmd_read&&
      dut.sysfio_icb_cmd_addr==32'hf0000008 && config_cycle<0)begin
     config_cycle=cycles;
     $display("QINGYU_ACTIVITY_START cycle=%0d time_ps=%0t",cycles,$realtime);
     if(dump_enabled)$dumpon;
    end
   if(dut.u_fio.start_command)begin
    if(start_cycle>=0)$fatal(1,"unexpected second START");
    start_cycle=cycles;
   end
   if(dut.shared_cache_clear)clear_count=clear_count+1;
   if(last_ack>=0&&dut.dma_icb_cmd_valid)$fatal(1,"new DMA offer after final marker ACK");
   if(start_cycle>=0 && last_ack<0)begin
    if(dut.u_shared.ram_cs)begin
     if(dut.u_shared.ram_we)macro_writes=macro_writes+1;else macro_reads=macro_reads+1;
    end
    if(dma_held && (!dut.dma_icb_cmd_valid ||
       {dut.dma_icb_cmd_read,dut.dma_icb_cmd_addr,dut.dma_icb_cmd_wdata,dut.dma_icb_cmd_wmask}!==held_payload))
     $fatal(1,"offered DMA command changed under backpressure");
    dma_held=dut.dma_icb_cmd_valid&&!dut.dma_icb_cmd_ready;
    held_payload={dut.dma_icb_cmd_read,dut.dma_icb_cmd_addr,dut.dma_icb_cmd_wdata,dut.dma_icb_cmd_wmask};
    // Register commands before handling legal same-edge downstream responses.
    if(dut.dma_icb_cmd_valid&&dut.dma_icb_cmd_ready)begin
     if(commands>=32768||final_offered)$fatal(1,"DMA overflow/command after marker");
     if(dut.dma_icb_cmd_addr[1:0]!=0||dut.dma_icb_cmd_wmask!=4'hf)$fatal(1,"bad DMA alignment/mask");
     q_addr[commands]=dut.dma_icb_cmd_addr;q_data[commands]=dut.dma_icb_cmd_wdata;q_read[commands]=dut.dma_icb_cmd_read;
     if(dut.dma_icb_cmd_read)begin
      if(first_read<0)begin first_read=cycles;if(clear_count!=1)$fatal(1,"task cache not cold");end
      if(dut.dma_icb_cmd_addr<32'ha0040000 || dut.dma_icb_cmd_addr>=32'ha0040000+32'(4*input_words))$fatal(1,"read outside source packet");
      index=int'((dut.dma_icb_cmd_addr-32'ha0040000)>>2);
      if(read_seen[index]!=0)$fatal(1,"duplicate source read %0d",index);
      if(index>=10&&!invalidation_acked)$fatal(1,"data read before marker invalidation ACK");
      read_seen[index]=read_seen[index]+1;reads=reads+1;
     end else begin
      if(dut.dma_icb_cmd_addr<32'ha0000000 || dut.dma_icb_cmd_addr>=32'ha0000000+32'd25540)$fatal(1,"write outside output");
      index=int'((dut.dma_icb_cmd_addr-32'ha0000000)>>2);
      if(index==0&&write_seen[0]==0)begin
       if(dut.dma_icb_cmd_wdata!=0||writes!=0||reads!=10)$fatal(1,"missing early marker invalidation");
      end else begin
       if(dut.dma_icb_cmd_wdata!==expected[index])$fatal(1,"wrong output write index=%0d got=%h expected=%h",index,dut.dma_icb_cmd_wdata,expected[index]);
       if(index==0)begin
        if(write_seen[0]!=1||write_responses!=output_words)$fatal(1,"final marker before other write ACKs");
        final_offered=1;
       end else if(write_seen[index]!=0)$fatal(1,"duplicate output word %0d",index);
       if(index>=17)begin
        tile=(index-17)/398;slotword=(index-17)%398;needed=int'((expected[tile+1]+31)>>5);
        if(slotword>=needed)$fatal(1,"unused slot written");
       end
      end
      write_seen[index]=write_seen[index]+1;writes=writes+1;
     end
     commands=commands+1;
    end
    if(`MAIN.fabric_mem_icb_cmd_valid&&`MAIN.fabric_mem_icb_cmd_ready)begin
     if(`MAIN.fabric_mem_icb_cmd_wmask!=4'hf)$fatal(1,"fabric byte mask changed");
     if(fabric_commands>=commands || `MAIN.fabric_mem_icb_cmd_addr!==q_addr[fabric_commands] ||
       `MAIN.fabric_mem_icb_cmd_read!==q_read[fabric_commands] ||
       (!q_read[fabric_commands]&&`MAIN.fabric_mem_icb_cmd_wdata!==q_data[fabric_commands]))$fatal(1,"official fabric route mismatch");
     fabric_commands=fabric_commands+1;
    end
    if(dut.sysmem_icb_cmd_valid&&dut.sysmem_icb_cmd_ready)begin
     if(dut.sysmem_icb_cmd_wmask!=4'hf)$fatal(1,"shared byte mask changed");
     if(shared_commands>=fabric_commands || dut.sysmem_icb_cmd_addr!==q_addr[shared_commands] ||
       dut.sysmem_icb_cmd_read!==q_read[shared_commands] ||
       (!q_read[shared_commands]&&dut.sysmem_icb_cmd_wdata!==q_data[shared_commands]))$fatal(1,"shared slave route mismatch");
     shared_commands=shared_commands+1;
    end
    if(dut.sysmem_icb_rsp_valid&&dut.sysmem_icb_rsp_ready)begin
     if(shared_responses>=shared_commands||dut.sysmem_icb_rsp_err)$fatal(1,"shared response mismatch");
     shared_responses=shared_responses+1;
    end
    if(dut.dma_icb_rsp_valid&&dut.dma_icb_rsp_ready)begin
     if(responses>=commands||dut.dma_icb_rsp_err)$fatal(1,"unexpected DMA response/error");
     if(q_read[responses])begin
      index=int'((q_addr[responses]-32'ha0040000)>>2);
      if(dut.dma_icb_rsp_rdata!==source_image[index])$fatal(1,"source response corrupt");
      read_responses=read_responses+1;
     end else begin
      write_responses=write_responses+1;
      if(q_addr[responses]==32'ha0000000)begin
       if(q_data[responses]==0)invalidation_acked=1;
       else begin
        if(q_data[responses]!=32'h31593851||responses+1!=commands)$fatal(1,"invalid last ACK");
        last_ack=cycles;activity_pending<=1;
       end
      end
     end
     responses=responses+1;
    end
    if(commands-responses>peak_pending)peak_pending=commands-responses;
   end
   if(host_valid)begin
    if(host_code!=1)$fatal(1,"firmware failed host=%h PC=%h",host_code,`CPU.inspect_pc);
    if(config_cycle<0||start_cycle<=config_cycle||first_read<start_cycle||last_ack<first_read||done_cycle<=last_ack)$fatal(1,"bad task window ordering");
    if(reads!=input_words||writes!=output_words+1||read_responses!=reads||write_responses!=writes||
       responses!=commands||fabric_commands!=commands||shared_commands!=commands||shared_responses!=commands)$fatal(1,"task count mismatch");
    mismatches=0;
    for(i=0;i<6385;i=i+1)begin
     if(dut.u_shared.mem[i]!==expected[i])mismatches=mismatches+1;
     if(i==0)expected_writes=2;
     else if(i<17)expected_writes=1;
     else begin tile=(i-17)/398;slotword=(i-17)%398;expected_writes=(slotword<int'((expected[tile+1]+31)>>5))?1:0;end
     if(write_seen[i]!=expected_writes)$fatal(1,"missing/extra output write %0d",i);
    end
    for(i=0;i<input_words;i=i+1)if(dut.u_shared.mem[65536+i]!==source_image[i]||read_seen[i]!=1)mismatches=mismatches+1;
    // Include all guard space; only the four explicit post-task diagnostics may differ.
    for(i=6385;i<131072;i=i+1)
     if(!(i>=65536&&i<65536+input_words)&&!(i>=49152&&i<=49155)&&dut.u_shared.mem[i]!==32'hcccccccc)mismatches=mismatches+1;
    if(mismatches)$fatal(1,"final memory/source/guards mismatches=%0d",mismatches);
    if(dut.u_fio.task_cycles!=32'(done_cycle-start_cycle+1))$fatal(1,"cycle counter mismatch");
    $display("INT8SOC_METRICS layer=%0d cpu_setup_to_ack=%0d start_to_ack=%0d first_read_to_ack=%0d done_delay=%0d engine_counter=%0d reads=%0d writes=%0d commands=%0d responses=%0d peak_pending=%0d macro_reads=%0d macro_writes=%0d core=%0d load=%0d factor=%0d cache=%0d compute=%0d store=%0d firmware_cycles=%0d",layer,last_ack-config_cycle+1,last_ack-start_cycle+1,last_ack-first_read+1,done_cycle-last_ack,dut.u_fio.task_cycles,reads,writes,commands,responses,peak_pending,macro_reads,macro_writes,dut.u_fio.core_cycles,dut.u_fio.load_cycles,dut.u_fio.factor_cycles,dut.u_fio.cache_cycles,dut.u_fio.compute_cycles,dut.u_fio.store_cycles,{dut.u_shared.mem[49153],dut.u_shared.mem[49152]});
    $display("PASS real E203 INT8 packet task complete;6385 output words, source and guard memory verified");
    #1;$finish;
   end
  end
  if(cycles>4000000)$fatal(1,"timeout PC=%h engine_state=%0d error=%h",`CPU.inspect_pc,dut.u_fio.engine.state,dut.u_fio.engine_error_code);
 end
endmodule
