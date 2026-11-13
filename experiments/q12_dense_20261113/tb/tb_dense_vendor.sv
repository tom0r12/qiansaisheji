`timescale 1ns/1ps
`include "e203_defines.v"
module tb_q12soc;
 reg clk=0,lfclk=0,rst_n=0;
 always #3.333333 clk=~clk;
 always #15258.789 lfclk=~lfclk;
 wire host_valid;wire [31:0] host_code;
 wire loader_clk,loader_rst_n,loader_cmd_valid,loader_cmd_ready,loader_cmd_read;
 wire [31:0] loader_cmd_addr,loader_cmd_wdata,loader_rsp_rdata;wire [3:0] loader_cmd_wmask;
 wire loader_rsp_valid,loader_rsp_ready,loader_rsp_err,loader_active;
 wire loader_request_valid,loader_request_ready;wire [31:0] loader_request_epoch;wire [3:0] loader_request_chunk;
 q12_loader_master_bfm u_loader(.clk(loader_clk),.rst_n(loader_rst_n),
  .request_valid(loader_request_valid),.request_ready(loader_request_ready),.request_epoch(loader_request_epoch),.request_chunk(loader_request_chunk),
  .active(loader_active),.cmd_valid(loader_cmd_valid),.cmd_ready(loader_cmd_ready),.cmd_read(loader_cmd_read),
  .cmd_addr(loader_cmd_addr),.cmd_wdata(loader_cmd_wdata),.cmd_wmask(loader_cmd_wmask),
  .rsp_valid(loader_rsp_valid),.rsp_ready(loader_rsp_ready),.rsp_err(loader_rsp_err));
 qingyu_e203_soc_top dut(
  .loader_clk(loader_clk),.loader_rst_n(loader_rst_n),
  .loader_cmd_valid(loader_cmd_valid),.loader_cmd_ready(loader_cmd_ready),.loader_cmd_read(loader_cmd_read),
  .loader_cmd_addr(loader_cmd_addr),.loader_cmd_wdata(loader_cmd_wdata),.loader_cmd_wmask(loader_cmd_wmask),
  .loader_rsp_valid(loader_rsp_valid),.loader_rsp_ready(loader_rsp_ready),.loader_rsp_err(loader_rsp_err),.loader_rsp_rdata(loader_rsp_rdata),
  .loader_request_valid(loader_request_valid),.loader_request_ready(loader_request_ready),.loader_request_epoch(loader_request_epoch),.loader_request_chunk(loader_request_chunk),

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
`define ITCM `CPU.u_e203_srams.u_e203_itcm_ram.u_e203_itcm_gnrl_ram.u_storage
`define DTCM `CPU.u_e203_srams.u_e203_dtcm_ram.u_e203_dtcm_gnrl_ram.u_storage
`define SHARED dut.u_shared

`define MERGE `MAIN.u_mem_merge
`define LOADER u_loader

`define ENG dut.u_fio.u_engine_fio.engine
`define CORE `ENG.compute
`define TRANS `ENG.transport
 integer prof_window=0,prof_fire=0,prof_stall=0,prof_empty=0,prof_no_offer=0,prof_offer_unselected=0;
 integer prof_cpu_offer=0,prof_loader_offer=0,prof_dma_offer=0,prof_dma_stall=0,prof_shared_stall=0;
 integer prof_pre_start=0,prof_x=0,prof_waitslot=0,prof_dotread=0,prof_dotwait_pipe=0,prof_dotwait_snapshot=0,prof_dot_capture=0,prof_other=0;
 integer prof_out_block=0,prof_encoder_in_block=0,prof_encoder_out_block=0,prof_rd_eligible=0,prof_wr_eligible=0,prof_both_eligible=0;
 integer prof_empty_pre=0,prof_empty_x=0,prof_empty_waitslot=0,prof_empty_dot=0,prof_empty_other=0;
 wire effective_cpu_offer=`MAIN.mem_icb_cmd_valid;
 wire effective_loader_offer=loader_cmd_valid;
 integer request_offers=0,mailbox_commands=0,mailbox_responses=0;
 integer mailbox_writes=0,mailbox_reads=0,mailbox_wait_timeouts=0;reg mailbox_read_pending=0;
 reg request_held=0;reg [35:0] request_payload;
 reg [63:0] firmware[0:8191];
 reg [31:0] expected[0:12688],source_image[0:16383];
 reg [31:0] dma_addr[0:32767],dma_data[0:32767];reg dma_read[0:32767];
 reg [31:0] route_addr[0:131071],route_data[0:131071];reg route_read[0:131071];reg [3:0] route_mask[0:131071];
 integer read_seen[0:16383],write_seen[0:12688];
 integer input_words,output_words,layer;
 integer cycles=0,full_start=-1,config_cycle=-1,start_cycle=-1,first_read=-1,last_ack=-1,done_cycle=-1;
 integer commands=0,responses=0,reads=0,writes=0,read_responses=0,write_responses=0;
 integer cpu_commands=0,cpu_responses=0,loader_commands=0,loader_responses=0;
 integer fabric_commands=0,fabric_responses=0,shared_commands=0,shared_responses=0,clear_count=0,peak_pending=0;
 integer macro_reads=0,macro_writes=0;
 integer i,index,tile,slotword,needed,expected_writes,mismatches;
 reg invalidation_acked=0,final_offered=0;
 reg dma_held=0,cpu_held=0;reg [68:0] held_payload,cpu_held_payload;
 reg [1023:0] firmware_path,input_path,expected_path,output_dump_path;
 integer dump_requested=0,dump_fd;
 reg runtime_enabled=0,assessment_done=0;
 reg activity_enabled=0;
 event fullwindow_dump_stop;
 always @(fullwindow_dump_stop)begin #0.001;$dumpoff;end
 string activity_path;
 initial if($value$plusargs("ACTIVITY=%s",activity_path))begin
  activity_enabled=1;$dumpfile(activity_path);$dumpvars(0,dut);$dumpoff;
 end
 reg fixture_attached=0,tcm_fixture_attached=0;
 reg [31:0] shared_readback[0:131071];
 reg [16:0] shared_address=0;
 reg [12:0] itcm_address=0;
 reg [13:0] dtcm_address=0;
 reg [31:0] shared_din=0;
 reg [63:0] itcm_din=0;
 reg shared_cs=0,itcm_cs=0,dtcm_cs=0,shared_we=1,shared_reset=0,loader_clear=0;
 wire loader_read=!shared_we;
 wire [31:0] loader_address={13'h1400,shared_address,2'b00};
 integer preload_commands=0,preload_responses=0;
 integer macro128_count=0,macro1024_count=0,macro4096_count=0;
 task attach_shared_loader;
  begin
   fixture_attached=1;
   force `SHARED.cache_clear=loader_clear;
   force `SHARED.clk=clk;
   force `SHARED.rst_n=shared_reset;
   force `SHARED.icb_cmd_valid=shared_cs;
   force `SHARED.icb_cmd_read=loader_read;
   force `SHARED.icb_cmd_addr=loader_address;
   force `SHARED.icb_cmd_wdata=shared_din;
   force `SHARED.icb_cmd_wmask=4'hf;
   force `SHARED.icb_rsp_ready=1'b1;
  end
 endtask
 task release_shared_loader;
  begin
   release `SHARED.icb_cmd_valid; release `SHARED.icb_cmd_read; release `SHARED.icb_cmd_addr;
   release `SHARED.icb_cmd_wdata; release `SHARED.icb_cmd_wmask; release `SHARED.icb_rsp_ready;
   release `SHARED.cache_clear;
   release `SHARED.rst_n; release `SHARED.clk;
   fixture_attached=0;
  end
 endtask
 reg [31:0] readback_data;
 task automatic read_shared_word(input [16:0] address,output [31:0] value);
  integer guard;
  reg response_on_accept;
  begin
   @(negedge clk);shared_cs=1;shared_address=address;
   @(posedge clk);guard=0;
   while(`SHARED.icb_cmd_ready!==1'b1)begin @(posedge clk);guard++;if(guard>1000)$fatal(1,"readback command stalled or unknown");end
   // Read-cache hits may return on the command acceptance edge. Capture the
   // value before a speculative next-word macro access changes its output.
   response_on_accept=`SHARED.icb_rsp_valid===1'b1;
   if(response_on_accept)begin
    if(`SHARED.icb_rsp_err!==1'b0)$fatal(1,"same-edge readback error or unknown");
    value=`SHARED.icb_rsp_rdata;
   end
   @(negedge clk);shared_cs=0;
   if(!response_on_accept)begin
    @(posedge clk);guard=0;
    while(`SHARED.icb_rsp_valid!==1'b1)begin @(posedge clk);guard++;if(guard>1000)$fatal(1,"readback response stalled or unknown");end
    if(`SHARED.icb_rsp_err!==1'b0)$fatal(1,"readback response error or unknown");
    value=`SHARED.icb_rsp_rdata;
   end
  end
 endtask
 task automatic preload_shared_word;
  integer guard;
  reg response_on_accept;
  begin
   @(posedge clk);guard=0;
   while(`SHARED.icb_cmd_ready!==1'b1)begin
    @(posedge clk);guard++;if(guard>1000)$fatal(1,"preload command stalled or unknown");
   end
   preload_commands++;
   response_on_accept=`SHARED.icb_rsp_valid===1'b1;
   if(response_on_accept)begin
    if(`SHARED.icb_rsp_err!==1'b0)$fatal(1,"zero-cycle preload error");
    preload_responses++;
   end
   @(negedge clk);shared_cs=0;itcm_cs=0;dtcm_cs=0;
   if(!response_on_accept)begin
    @(posedge clk);guard=0;
    while(`SHARED.icb_rsp_valid!==1'b1)begin
     @(posedge clk);guard++;if(guard>1000)$fatal(1,"preload response stalled or unknown");
    end
    if(`SHARED.icb_rsp_err!==1'b0)$fatal(1,"registered preload error");
    preload_responses++;
   end
  end
 endtask

 initial begin
  if(!$value$plusargs("FIRMWARE=%s",firmware_path))$fatal(1,"missing FIRMWARE");
  if(!$value$plusargs("INPUT=%s",input_path))$fatal(1,"missing INPUT");
  if(!$value$plusargs("EXPECTED=%s",expected_path))$fatal(1,"missing EXPECTED");
  if(!$value$plusargs("INPUT_WORDS=%d",input_words))$fatal(1,"missing INPUT_WORDS");
  if(!$value$plusargs("OUTPUT_WORDS=%d",output_words))$fatal(1,"missing OUTPUT_WORDS");
  if(!$value$plusargs("LAYER=%d",layer))layer=0;
  dump_requested=$value$plusargs("OUTPUT_DUMP=%s",output_dump_path);
  // OUTPUT_WORDS includes initial invalidation, 16 length words and final magic.
  if(input_words<330||input_words>8873||output_words!=12690)$fatal(1,"invalid fixture bounds");
  $readmemh(firmware_path,firmware);$readmemh(input_path,source_image,0,input_words-1);$readmemh(expected_path,expected);
  if(expected[0]!=32'h31443151)$fatal(1,"dense format identity");
  for(integer t=1;t<=16;t++)if(expected[t]!=25344)$fatal(1,"fixed dense length");

  for(i=0;i<16384;i=i+1)read_seen[i]=0;
  for(i=0;i<12689;i=i+1)write_seen[i]=0;
  // Initialization contains no tensor or parameter preload. Every source word
  // must arrive later through platform ingress -> original bus -> shared SRAM.
  attach_shared_loader;
  tcm_fixture_attached=1;
  force `ITCM.clk=clk;force `ITCM.cs=itcm_cs;force `ITCM.we=1'b1;
  force `ITCM.addr=itcm_address;force `ITCM.din=itcm_din;force `ITCM.wem=8'hff;
  force `DTCM.clk=clk;force `DTCM.cs=dtcm_cs;force `DTCM.we=1'b1;
  force `DTCM.addr=dtcm_address;force `DTCM.din=32'b0;force `DTCM.wem=4'hf;
  repeat(4)@(negedge clk);shared_reset=1;
  for(i=0;i<131072;i=i+1)begin
   @(negedge clk);shared_cs=1;shared_address=17'(i);shared_din=32'hcccccccc;
   itcm_cs=i<8192;itcm_address=13'(i);itcm_din=i<8192?firmware[i]:64'b0;
   dtcm_cs=i<16384;dtcm_address=14'(i);
   preload_shared_word();
  end
  @(negedge clk);shared_cs=0;itcm_cs=0;dtcm_cs=0;
  @(posedge clk);#1;release_shared_loader;
  release `ITCM.cs;release `ITCM.we;release `ITCM.addr;release `ITCM.din;release `ITCM.wem;release `ITCM.clk;
  release `DTCM.cs;release `DTCM.we;release `DTCM.addr;release `DTCM.din;release `DTCM.wem;release `DTCM.clk;
  tcm_fixture_attached=0;
  if(preload_commands!=131072||preload_responses!=131072||rst_n!==1'b0)$fatal(1,"incomplete physical poison preload or CPU not reset");
  if(macro128_count!=30||macro1024_count!=6||macro4096_count!=80)$fatal(1,"wrong elaborated macro organization");
  $display("Q12_VENDOR_MACROS RAMSP128X16=%0d RAMSP1024X16=%0d RAMSP4096X16=%0d total=%0d",macro128_count,macro1024_count,macro4096_count,macro128_count+macro1024_count+macro4096_count);
  $display("Q12_POISON_PRELOAD_COMPLETE commands=%0d responses=%0d tensor_words=0 CPU_reset=%b",preload_commands,preload_responses,rst_n);
  repeat(8)@(negedge lfclk);runtime_enabled=1;if(activity_enabled)$dumpon;rst_n=1;
 end
 always @(negedge dut.qingyu_bus_clk)if(runtime_enabled&&!assessment_done&&dut.qingyu_bus_rst_n&&dut.u_fio.u_engine_fio.engine_done)done_cycle=cycles;
 always @(posedge dut.qingyu_bus_clk)begin
  cycles=cycles+1;
  if(runtime_enabled&&!assessment_done&&dut.qingyu_bus_rst_n)begin
   // Earliest control offer counts CPU setup and every subsequent loader wait.
   if(full_start<0&&((`MAIN.mem_icb_cmd_valid&&!`MAIN.mem_icb_cmd_read&&
      `MAIN.mem_icb_cmd_addr>=32'ha0030100&&`MAIN.mem_icb_cmd_addr<32'ha0030140)||
      (dut.sysfio_icb_cmd_valid&&!dut.sysfio_icb_cmd_read&&dut.sysfio_icb_cmd_addr[31:4]==28'hf002000)||
      loader_request_valid||loader_cmd_valid))begin
    full_start=cycles;$display("Q12_FULL_START cycle=%0d time_ps=%0.0f",cycles,$realtime*1000.0);
   end

   if(full_start>=0&&last_ack<0)begin
    prof_window++;
    if(`MAIN.fabric_mem_icb_cmd_valid)begin
     if(`MAIN.fabric_mem_icb_cmd_ready)prof_fire++;else prof_stall++;
    end else begin
     prof_empty++;
     if(!effective_cpu_offer&&!effective_loader_offer&&!dut.dma_icb_cmd_valid)prof_no_offer++;
     else prof_offer_unselected++;
     if(start_cycle<0)prof_empty_pre++;
     else if(`CORE.state_q==1||`CORE.state_q==2)prof_empty_x++;
     else if(`CORE.state_q==3)prof_empty_waitslot++;
     else if(`CORE.state_q==10||`CORE.state_q==11)prof_empty_dot++;
     else prof_empty_other++;
    end
    if(effective_cpu_offer)prof_cpu_offer++;
    if(effective_loader_offer)prof_loader_offer++;
    if(dut.dma_icb_cmd_valid)prof_dma_offer++;
    if(dut.dma_icb_cmd_valid&&!dut.dma_icb_cmd_ready)prof_dma_stall++;
    if(dut.sysmem_icb_cmd_valid&&!dut.sysmem_icb_cmd_ready)prof_shared_stall++;
    if(start_cycle<0)prof_pre_start++;
    else if(`CORE.state_q==1||`CORE.state_q==2)prof_x++;
    else if(`CORE.state_q==3)prof_waitslot++;
    else if(`CORE.state_q==10)prof_dotread++;
    else if(`CORE.state_q==11)begin
     if(!`CORE.dot_all_valid)prof_dotwait_pipe++;
     else if(`CORE.snapshot_valid_q&&!`CORE.snapshot_last_ack)prof_dotwait_snapshot++;
     else prof_dot_capture++;
    end else prof_other++;
    if(`CORE.out_valid&&!`CORE.out_ready)prof_out_block++;
    if(`ENG.formatter.in_valid&&!`ENG.formatter.in_ready)prof_encoder_in_block++;
    if(`ENG.formatter.out_valid&&!`ENG.formatter.out_ready)prof_encoder_out_block++;
    if(`TRANS.read_eligible)prof_rd_eligible++;
    if(`TRANS.write_eligible)prof_wr_eligible++;
    if(`TRANS.read_eligible&&`TRANS.write_eligible)prof_both_eligible++;
   end
   if(dut.sysfio_icb_cmd_valid&&dut.sysfio_icb_cmd_ready&&!dut.sysfio_icb_cmd_read&&
      dut.sysfio_icb_cmd_addr==32'hf0000008&&config_cycle<0)config_cycle=cycles;
   if(dut.u_fio.u_engine_fio.start_command)begin
    if(start_cycle>=0)$fatal(1,"unexpected second START");start_cycle=cycles;
    if(dut.u_fio.u_engine_fio.available_words>32'(`LOADER.source_acks))$fatal(1,"START publishes unacknowledged source");
   end
   if(dut.u_fio.u_engine_fio.engine_commit_rsp_valid&&!dut.u_fio.u_engine_fio.engine_commit_rsp_error&&
      dut.u_fio.u_engine_fio.offered_commit_words>32'(`LOADER.source_acks))$fatal(1,"CPU commit precedes actual loader ACKs");
   if(request_held&&(!loader_request_valid||{loader_request_epoch,loader_request_chunk}!==request_payload))$fatal(1,"public loader request changed under backpressure");
   request_held=loader_request_valid&&!loader_request_ready;request_payload={loader_request_epoch,loader_request_chunk};
   if(loader_request_valid&&loader_request_ready)begin
    if(full_start<0||loader_request_epoch!=1||loader_request_chunk!=4'(request_offers+1))$fatal(1,"public request epoch/order/window");request_offers++;
   end
   if(dut.u_fio.u_request.icb_cmd_valid&&dut.u_fio.u_request.icb_cmd_ready)begin
    mailbox_commands++;mailbox_read_pending=dut.u_fio.u_request.icb_cmd_read;
    if(dut.u_fio.u_request.icb_cmd_read)begin
     if(dut.u_fio.u_request.icb_cmd_addr!=32'hf002000c)$fatal(1,"unexpected mailbox read");
     mailbox_reads++;
    end else mailbox_writes++;
   end
   if(dut.u_fio.u_request.icb_rsp_valid&&dut.u_fio.u_request.icb_rsp_ready)begin
    if(mailbox_read_pending&&dut.u_fio.u_request.icb_rsp_rdata!=0)begin mailbox_wait_timeouts++;$fatal(1,"blocking WAIT timeout/error");end
    if(dut.u_fio.u_request.icb_rsp_err||mailbox_responses>=mailbox_commands)$fatal(1,"mailbox real response mismatch");mailbox_responses++;
   end
   if(dut.shared_cache_clear)clear_count=clear_count+1;
   if(last_ack>=0&&dut.dma_icb_cmd_valid)$fatal(1,"new DMA offer after final marker ACK");
   if(cpu_held&&(!`MAIN.mem_icb_cmd_valid||
      {`MAIN.mem_icb_cmd_read,`MAIN.mem_icb_cmd_addr,`MAIN.mem_icb_cmd_wdata,`MAIN.mem_icb_cmd_wmask}!==cpu_held_payload))
      $fatal(1,"CPU command changed under real arbiter backpressure");
   cpu_held=`MAIN.mem_icb_cmd_valid&&!`MAIN.mem_icb_cmd_ready;
   cpu_held_payload={`MAIN.mem_icb_cmd_read,`MAIN.mem_icb_cmd_addr,`MAIN.mem_icb_cmd_wdata,`MAIN.mem_icb_cmd_wmask};
   if(`MAIN.mem_icb_cmd_valid&&`MAIN.mem_icb_cmd_ready)cpu_commands=cpu_commands+1;
   if(`MAIN.mem_icb_rsp_valid&&`MAIN.mem_icb_rsp_ready)begin
    if(`MAIN.mem_icb_rsp_err||cpu_responses>=cpu_commands)$fatal(1,"CPU ingress response mismatch");cpu_responses=cpu_responses+1;
   end
   if(`LOADER.cmd_valid&&`LOADER.cmd_ready)loader_commands=loader_commands+1;
   if(`LOADER.rsp_valid&&`LOADER.rsp_ready)begin
    if(`LOADER.rsp_err||loader_responses>=loader_commands)$fatal(1,"loader response ownership mismatch");loader_responses=loader_responses+1;
   end
   if(full_start>=0&&last_ack<0&&dut.u_shared.ram_cs)begin
    if(dut.u_shared.ram_we)macro_writes=macro_writes+1;else macro_reads=macro_reads+1;
   end
   if(dma_held&&(!dut.dma_icb_cmd_valid||
      {dut.dma_icb_cmd_read,dut.dma_icb_cmd_addr,dut.dma_icb_cmd_wdata,dut.dma_icb_cmd_wmask}!==held_payload))
      $fatal(1,"offered DMA command changed under backpressure");
   dma_held=dut.dma_icb_cmd_valid&&!dut.dma_icb_cmd_ready;
   held_payload={dut.dma_icb_cmd_read,dut.dma_icb_cmd_addr,dut.dma_icb_cmd_wdata,dut.dma_icb_cmd_wmask};
   if(dut.dma_icb_cmd_valid&&dut.dma_icb_cmd_ready)begin
    if(start_cycle<0||commands>=32768||final_offered)$fatal(1,"DMA command ordering/overflow");
    if(dut.dma_icb_cmd_addr[1:0]!=0||dut.dma_icb_cmd_wmask!=4'hf)$fatal(1,"bad DMA alignment/mask");
    dma_addr[commands]=dut.dma_icb_cmd_addr;dma_data[commands]=dut.dma_icb_cmd_wdata;dma_read[commands]=dut.dma_icb_cmd_read;
    if(dut.dma_icb_cmd_read)begin
     if(first_read<0)begin first_read=cycles;if(clear_count!=1)$fatal(1,"task cache not cold");end
     if(dut.dma_icb_cmd_addr<32'ha0040000||dut.dma_icb_cmd_addr>=32'ha0040000+32'(4*input_words))$fatal(1,"read outside source packet");
     index=int'((dut.dma_icb_cmd_addr-32'ha0040000)>>2);
     if(index>=int'(dut.u_fio.u_engine_fio.engine.gate_available)||index>=`LOADER.source_acks)$fatal(1,"read beyond CPU committed and acknowledged prefix");
     if(read_seen[index]!=0)$fatal(1,"duplicate source read %0d",index);
     if(index>=10&&!invalidation_acked)$fatal(1,"data read before marker invalidation ACK");
     read_seen[index]=read_seen[index]+1;reads=reads+1;
    end else begin
     if(dut.dma_icb_cmd_addr<32'ha0000000||dut.dma_icb_cmd_addr>=32'ha0000000+32'd50756)$fatal(1,"write outside output");
     index=int'((dut.dma_icb_cmd_addr-32'ha0000000)>>2);
     if(index==0&&write_seen[0]==0)begin
      if(dut.dma_icb_cmd_wdata!=0||writes!=0||reads!=10)$fatal(1,"missing early marker invalidation");
     end else begin
      if(dut.dma_icb_cmd_wdata!==expected[index])$fatal(1,"wrong output index=%0d got=%h expected=%h",index,dut.dma_icb_cmd_wdata,expected[index]);
      if(index==0)begin
       if(write_seen[0]!=1||write_responses!=output_words-1)$fatal(1,"final marker before other write ACKs");final_offered=1;
      end else if(write_seen[index]!=0)$fatal(1,"duplicate output word");
      if(index>=17)begin
       tile=(index-17)/792;slotword=(index-17)%792;needed=int'((expected[tile+1]+31)>>5);
       if(slotword>=needed)$fatal(1,"unused output slot written");
      end
     end
     write_seen[index]=write_seen[index]+1;writes=writes+1;
    end
    commands=commands+1;
   end
   // Independent all-origin ledger after the original merger. CPU, loader and
   // engine are permitted concurrently; each must traverse the same fabric.
   if(`MAIN.fabric_mem_icb_cmd_valid&&`MAIN.fabric_mem_icb_cmd_ready)begin
    if(fabric_commands>=131072)$fatal(1,"fabric ledger overflow");
    route_addr[fabric_commands]=`MAIN.fabric_mem_icb_cmd_addr;route_data[fabric_commands]=`MAIN.fabric_mem_icb_cmd_wdata;
    route_read[fabric_commands]=`MAIN.fabric_mem_icb_cmd_read;route_mask[fabric_commands]=`MAIN.fabric_mem_icb_cmd_wmask;
    fabric_commands=fabric_commands+1;
   end
   if(dut.sysmem_icb_cmd_valid&&dut.sysmem_icb_cmd_ready)begin
    if(shared_commands>=fabric_commands||dut.sysmem_icb_cmd_addr!==route_addr[shared_commands]||
       dut.sysmem_icb_cmd_read!==route_read[shared_commands]||dut.sysmem_icb_cmd_wmask!==route_mask[shared_commands]||
       (!route_read[shared_commands]&&dut.sysmem_icb_cmd_wdata!==route_data[shared_commands]))$fatal(1,"original bus to shared route mismatch");
    shared_commands=shared_commands+1;
   end
   if(dut.sysmem_icb_rsp_valid&&dut.sysmem_icb_rsp_ready)begin
    if(shared_responses>=shared_commands||dut.sysmem_icb_rsp_err)$fatal(1,"shared response mismatch");shared_responses=shared_responses+1;
   end
   if(`MAIN.fabric_mem_icb_rsp_valid&&`MAIN.fabric_mem_icb_rsp_ready)begin
    if(fabric_responses>=shared_responses||`MAIN.fabric_mem_icb_rsp_err)$fatal(1,"fabric response mismatch");fabric_responses=fabric_responses+1;
   end
   if(dut.dma_icb_rsp_valid&&dut.dma_icb_rsp_ready)begin
    if(responses>=commands||dut.dma_icb_rsp_err)$fatal(1,"unexpected DMA response/error");
    if(dma_read[responses])begin
     index=int'((dma_addr[responses]-32'ha0040000)>>2);
     if(dut.dma_icb_rsp_rdata!==source_image[index])$fatal(1,"source response corrupt");read_responses=read_responses+1;
    end else begin
     write_responses=write_responses+1;
     if(dma_addr[responses]==32'ha0000000)begin
      if(dma_data[responses]==0)invalidation_acked=1;
      else begin
       if(dma_data[responses]!=32'h31443151||responses+1!=commands)$fatal(1,"invalid final ACK");
       last_ack=cycles;$display("Q12_FULL_END cycle=%0d time_ps=%0.0f",cycles,$realtime*1000.0);if(activity_enabled)->fullwindow_dump_stop;
      end
     end
    end
    responses=responses+1;
   end
   if(commands-responses>peak_pending)peak_pending=commands-responses;
   if(host_valid)begin
    if(`MERGE.u_original.NP!=3||`MERGE.u_original.count_q!=0||request_offers!=9||mailbox_writes!=10||mailbox_reads!=9||mailbox_commands!=mailbox_writes+mailbox_reads||mailbox_responses!=mailbox_commands||loader_active||loader_request_valid)
      $fatal(1,"explicit loader master/request queues not drained");
    $display("Q12_EXPLICIT_LOADER masters=3 requests=%0d mailbox_commands=%0d mailbox_responses=%0d independent_cpu=1",request_offers,mailbox_commands,mailbox_responses);
    $display("Q12_MAILBOX_WAIT writes=%0d reads=%0d commands=%0d responses=%0d timeouts=%0d",mailbox_writes,mailbox_reads,mailbox_commands,mailbox_responses,mailbox_wait_timeouts);
    if(prof_window!=last_ack-full_start+1 || prof_window!=prof_fire+prof_stall+prof_empty || prof_empty!=prof_no_offer+prof_offer_unselected)
     $fatal(1,"profiling window partition mismatch");
    $display("Q12_PROFILE_BUS window=%0d fire=%0d valid_stall=%0d no_fabric_valid=%0d no_master_offer=%0d offered_unselected=%0d cpu_offer=%0d loader_offer=%0d dma_offer=%0d dma_stall=%0d shared_stall=%0d",prof_window,prof_fire,prof_stall,prof_empty,prof_no_offer,prof_offer_unselected,prof_cpu_offer,prof_loader_offer,prof_dma_offer,prof_dma_stall,prof_shared_stall);
    $display("Q12_PROFILE_CORE pre=%0d x=%0d waitslot=%0d dotread=%0d dotwait_pipe=%0d dotwait_snapshot=%0d capture=%0d other=%0d out_block=%0d encoder_in_block=%0d encoder_out_block=%0d read_eligible=%0d write_eligible=%0d both_eligible=%0d",prof_pre_start,prof_x,prof_waitslot,prof_dotread,prof_dotwait_pipe,prof_dotwait_snapshot,prof_dot_capture,prof_other,prof_out_block,prof_encoder_in_block,prof_encoder_out_block,prof_rd_eligible,prof_wr_eligible,prof_both_eligible);
    $display("Q12_PROFILE_EMPTY pre=%0d x=%0d waitslot=%0d dot=%0d other=%0d",prof_empty_pre,prof_empty_x,prof_empty_waitslot,prof_empty_dot,prof_empty_other);

    if(host_code!=1)$fatal(1,"firmware failed host=%h PC=%h",host_code,`CPU.inspect_pc);
    if(full_start<0||config_cycle<full_start||start_cycle<=config_cycle||first_read<start_cycle||last_ack<first_read||done_cycle<=last_ack)$fatal(1,"bad window ordering");
    if(reads!=input_words||writes!=output_words||read_responses!=reads||write_responses!=writes||responses!=commands||
       loader_commands!=input_words+45||loader_responses!=loader_commands||`LOADER.source_acks!=input_words||`LOADER.chunks!=9||
       cpu_responses!=cpu_commands||fabric_commands!=commands+cpu_commands+loader_commands||shared_commands!=fabric_commands||
       shared_responses!=shared_commands||fabric_responses!=fabric_commands)$fatal(1,"transaction conservation failure");
    assessment_done=1;
   end
  end
  if(runtime_enabled&&!assessment_done&&cycles>4000000)$fatal(1,"timeout PC=%h engine_state=%0d error=%h loader_state=%0d seq=%0d pending=%0d",`CPU.inspect_pc,dut.u_fio.u_engine_fio.engine.state,dut.u_fio.u_engine_fio.engine_error_code,`LOADER.state,`LOADER.next_seq,`LOADER.pending_seq);
 end
 always @(posedge clk)begin
  if(runtime_enabled&&!assessment_done&&(fixture_attached||tcm_fixture_attached))
   $fatal(1,"fixture force active during measured runtime");
  if(assessment_done&&fixture_attached&&shared_cs&&shared_we)
   $fatal(1,"post-task fixture attempted a write");
 end
 initial begin
  wait(assessment_done===1'b1);
  @(negedge clk);shared_cs=0;shared_we=0;loader_clear=1;
  attach_shared_loader;
  repeat(2)@(negedge clk);loader_clear=0;
  for(integer word_index=0;word_index<131072;word_index++)begin
   read_shared_word(17'(word_index),readback_data);
   shared_readback[word_index]=readback_data;
  end
  @(negedge clk);shared_cs=0;
  @(posedge clk);#1;release_shared_loader;
  $display("Q12_MACRO_READBACK_COMPLETE words=131072 output_slots=12689 source_words=%0d",input_words);
    mismatches=0;
    for(i=0;i<12689;i=i+1)begin
     if(shared_readback[i]!==expected[i])mismatches=mismatches+1;
     if(i==0)expected_writes=2;else if(i<17)expected_writes=1;
     else begin tile=(i-17)/792;slotword=(i-17)%792;expected_writes=1;end
     if(write_seen[i]!=expected_writes)$fatal(1,"missing/extra output write %0d",i);
    end
    for(i=0;i<input_words;i=i+1)if(shared_readback[65536+i]!==source_image[i]||read_seen[i]!=1)mismatches=mismatches+1;
    // Only seven specified protocol words and four diagnostic words may differ.
    for(i=12689;i<131072;i=i+1)
     if(!(i>=65536&&i<65536+input_words)&&!(i>=49152&&i<=49155)&&!(i>=49216&&i<=49222)&&
        shared_readback[i]!==32'hcccccccc)mismatches=mismatches+1;
    if(shared_readback[49216]!=9||shared_readback[49217]!=9||shared_readback[49218]!=32'(input_words)||
       shared_readback[49219]!=1||shared_readback[49220]!=32'(input_words)||shared_readback[49221]!=0||shared_readback[49222]!=1)
       $fatal(1,"final control protocol state mismatch");
    if(mismatches)$fatal(1,"memory/source/guards mismatches=%0d",mismatches);
    if(dump_requested)begin
     dump_fd=$fopen(output_dump_path,"w");if(!dump_fd)$fatal(1,"cannot create output dump");
     for(i=0;i<12689;i=i+1)$fdisplay(dump_fd,"%08x",shared_readback[i]);$fclose(dump_fd);
    end
    if(dut.u_fio.u_engine_fio.task_cycles!=32'(done_cycle-start_cycle+1))$fatal(1,"engine counter mismatch");
    $display("Q12SOC_PHASES core=%0d load=%0d factor=%0d cache=%0d compute=%0d store=%0d",
      dut.u_fio.u_engine_fio.core_cycles,dut.u_fio.u_engine_fio.load_cycles,dut.u_fio.u_engine_fio.factor_cycles,dut.u_fio.u_engine_fio.cache_cycles,dut.u_fio.u_engine_fio.compute_cycles,dut.u_fio.u_engine_fio.store_cycles);
    $display("Q12SOC_METRICS layer=%0d full_window_cycles=%0d start_to_ack=%0d first_read_to_ack=%0d load_first=%0d load_last_ack=%0d done_delay=%0d engine_counter=%0d reads=%0d writes=%0d cpu_commands=%0d loader_commands=%0d fabric_commands=%0d responses=%0d peak_pending=%0d macro_reads=%0d macro_writes=%0d firmware_cycles=%0d",layer,last_ack-full_start+1,last_ack-start_cycle+1,last_ack-first_read+1,`LOADER.first_source_cycle,`LOADER.last_source_ack_cycle,done_cycle-last_ack,dut.u_fio.u_engine_fio.task_cycles,reads,writes,cpu_commands,loader_commands,fabric_commands,responses,peak_pending,macro_reads,macro_writes,{shared_readback[49153],shared_readback[49152]});
    $display("PASS real E203 Q12 vendor task; explicit independent loader and original System Bus; manufacturer SRAM and full physical readback verified");
  #1;$finish;
 end
endmodule
`undef MAIN
`undef CPU
`undef ITCM
`undef DTCM
`undef SHARED
`undef MERGE
`undef LOADER
