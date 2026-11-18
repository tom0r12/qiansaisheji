`timescale 1ns/1ps
`include "e203_defines.v"
module tb_q12soc;
 reg clk=0,lfclk=0,rst_n=0;
 always #3.333333 clk=~clk;
 always #15258.789 lfclk=~lfclk;
 wire host_valid;wire [31:0] host_code;
 wire [31:0] gpio_data,gpio_b_out,gpio_b_oe,gpio_a_oe;
 wire gpio_ready;
 integer gpio_presented,gpio_requested,gpio_bursts;
 wire [63:0] gpio_first_data_ps,gpio_last_data_ps;
 q12_gpio_source #(.WORDS(8873)) u_source(
  .req(gpio_b_out[1]),.count(gpio_b_out[9:2]),.oe(gpio_b_oe[9:1]),.data(gpio_data),.ready(gpio_ready),
  .presented_words(gpio_presented),.requested_words(gpio_requested),.burst_requests(gpio_bursts),
  .first_data_ps(gpio_first_data_ps),.last_data_ps(gpio_last_data_ps));
 qingyu_e203_soc_top dut(
  .qingyu_host_valid(host_valid),.qingyu_host_code(host_code),
  .hfextclk(clk),.hfxoscen(),.lfextclk(lfclk),.lfxoscen(),
  .io_pads_jtag_TCK_i_ival(1'b0),.io_pads_jtag_TMS_i_ival(1'b1),.io_pads_jtag_TDI_i_ival(1'b0),
  .io_pads_gpioA_i_ival(gpio_data),.io_pads_gpioA_o_oe(gpio_a_oe),
  .io_pads_gpioB_i_ival({31'b0,gpio_ready}),.io_pads_gpioB_o_oval(gpio_b_out),.io_pads_gpioB_o_oe(gpio_b_oe),
  .io_pads_qspi0_dq_0_i_ival(1'b1),.io_pads_qspi0_dq_1_i_ival(1'b1),
  .io_pads_qspi0_dq_2_i_ival(1'b1),.io_pads_qspi0_dq_3_i_ival(1'b1),
  .io_pads_aon_erst_n_i_ival(rst_n),.io_pads_dbgmode0_n_i_ival(1'b1),
  .io_pads_dbgmode1_n_i_ival(1'b1),.io_pads_dbgmode2_n_i_ival(1'b1),
  .io_pads_bootrom_n_i_ival(1'b0),.io_pads_aon_pmu_dwakeup_n_i_ival(1'b1));
`define MAIN dut.u_e203_subsys_top.u_e203_subsys_main
`define PERIPS `MAIN.u_e203_subsys_perips
`define GPIOA `PERIPS.u_perips_apb_gpioA
`define CPU `MAIN.u_e203_cpu_top
`define ITCM `CPU.u_e203_srams.u_e203_itcm_ram.u_e203_itcm_gnrl_ram.u_sirv_sim_ram
`define MERGE `MAIN.u_mem_merge
`define ENG dut.u_fio.engine
`define CORE `ENG.compute
`define TRANS `ENG.transport
 localparam integer INPUT_MAX=8873,OUTPUT_COUNT=12689,WRITE_COUNT=12690,LEDGER=131072;
 reg [63:0] firmware[0:8191];
 reg [31:0] expected[0:OUTPUT_COUNT-1],source_image[0:INPUT_MAX-1];
 reg [31:0] dma_addr[0:32767],dma_data[0:32767];reg dma_read[0:32767];
 reg [31:0] cpu_addr[0:LEDGER-1],cpu_data[0:LEDGER-1];reg cpu_read[0:LEDGER-1];reg [3:0] cpu_mask[0:LEDGER-1];
 reg [31:0] shared_addr[0:LEDGER-1],shared_data[0:LEDGER-1];reg shared_read[0:LEDGER-1];reg [3:0] shared_mask[0:LEDGER-1];
 reg fabric_read[0:LEDGER-1];integer fabric_target_index[0:LEDGER-1];
 reg [31:0] shared_rsp_data[0:LEDGER-1];
 integer read_seen[0:INPUT_MAX-1],source_write_seen[0:INPUT_MAX-1],gpio_read_seen[0:INPUT_MAX-1],write_seen[0:OUTPUT_COUNT-1];
 integer source_write_ack_seen[0:INPUT_MAX-1],gpio_word_ack_seen[0:INPUT_MAX-1];
 integer boundaries[0:8],source_acked_prefix=0,publish_commands=0,commit_responses=0,observed_available=0,start_source_acks=0;
 integer input_words,output_words,layer,serial_load=0;
 integer cycles=0,full_start=-1,config_cycle=-1,start_cycle=-1,first_read=-1,last_ack=-1,done_cycle=-1;
 integer commands=0,responses=0,reads=0,writes=0,read_responses=0,write_responses=0;
 reg[31:0] copy_addr[0:INPUT_MAX-1],copy_data[0:INPUT_MAX-1];
 integer copy_commands=0,copy_responses=0,copy_routed=0;
 reg copy_match,copy_held=0;reg[68:0] copy_held_payload;
 integer gp_commands=0,gp_responses=0;
 integer cpu_commands=0,cpu_responses=0,cpu_routed=0,dma_routed=0;
 integer gpio_words=0,gpio_word_responses=0,source_writes=0,source_write_responses=0;
 integer first_gpio_cycle=-1,last_gpio_read_ack=-1,first_source_cycle=-1,last_source_ack=-1;
 integer fabric_commands=0,fabric_responses=0,fabric_shared=0;
 integer shared_commands=0,shared_responses=0,peak_pending=0;
 integer prof_window=0,prof_fire=0,prof_stall=0,prof_empty=0,prof_dma_stall=0,prof_shared_stall=0;
 integer i,index,expected_writes,mismatches,target_index,layout_words;
 integer clear_count=0,macro_reads=0,macro_writes=0;
 integer gpio_a_commands=0,gpio_a_responses=0,gpio_apb_reads=0,gpio_ready_reads=0;
 reg gpio_a_data_cmd[0:LEDGER-1];

 reg invalidation_acked=0,final_offered=0;
 reg dma_held=0,cpu_held=0,fabric_held=0,shared_held=0;
 reg [68:0] held_payload,cpu_held_payload,fabric_held_payload,shared_held_payload;
 reg cpu_match,dma_match;
 reg [1023:0] firmware_path,input_path,expected_path,output_dump_path;
 integer dump_requested=0,dump_fd;
 reg [63:0] full_start_ps=0,last_ack_ps=0;
 initial begin
  if(!$value$plusargs("FIRMWARE=%s",firmware_path))$fatal(1,"missing FIRMWARE");
  if(!$value$plusargs("INPUT=%s",input_path))$fatal(1,"missing INPUT");
  if(!$value$plusargs("EXPECTED=%s",expected_path))$fatal(1,"missing EXPECTED");
  if(!$value$plusargs("INPUT_WORDS=%d",input_words))$fatal(1,"missing INPUT_WORDS");
  if(!$value$plusargs("OUTPUT_WORDS=%d",output_words))$fatal(1,"missing OUTPUT_WORDS");
  if(!$value$plusargs("LAYER=%d",layer))layer=0;
  if(!$value$plusargs("SERIAL_LOAD=%d",serial_load))serial_load=0;
  if(serial_load!=0&&serial_load!=1)$fatal(1,"SERIAL_LOAD must be 0 or 1");
  dump_requested=$value$plusargs("OUTPUT_DUMP=%s",output_dump_path);
  if(input_words<330||input_words>INPUT_MAX||output_words!=WRITE_COUNT)$fatal(1,"Rice input/dense output fixture allocation mismatch");
  $readmemh(firmware_path,firmware);$readmemh(input_path,source_image,0,input_words-1);$readmemh(expected_path,expected);
  if(source_image[0]!==32'h32583151||source_image[1]!==32'd76032)$fatal(1,"wrong fixed12 source format");
  layout_words=330+int'((source_image[1]+31)>>5);
  boundaries[0]=layout_words;
  for(i=2;i<10;i=i+1)begin
   if(source_image[i]!==32'd24576)$fatal(1,"wrong fixed12 weight block length");
   layout_words=layout_words+int'((source_image[i]+31)>>5);
   boundaries[i-1]=layout_words;
  end
  if(layout_words!=input_words)$fatal(1,"fixed12 input packet length mismatch");
  if(expected[0]!==32'h32443151)$fatal(1,"wrong dense output reference magic");
  for(i=1;i<=16;i=i+1)if(expected[i]!==32'd1584)$fatal(1,"wrong dense metadata");
  for(i=17;i<OUTPUT_COUNT;i=i+1)
   if(expected[i][15:13]!=={3{expected[i][12]}}||expected[i][31:29]!=={3{expected[i][28]}})$fatal(1,"expected value is not signed Y13 in INT16");
  // Host file reads prepare the EXTERNAL GPIO source and independent checker only.
  // DUT memory receives firmware and poison before reset release, never task data.
  for(i=0;i<8192;i=i+1)`ITCM.mem_r[i]=firmware[i];
  for(i=0;i<input_words;i=i+1)begin
   read_seen[i]=0;source_write_seen[i]=0;gpio_read_seen[i]=0;
   source_write_ack_seen[i]=0;gpio_word_ack_seen[i]=0;
  end
  for(i=0;i<OUTPUT_COUNT;i=i+1)write_seen[i]=0;
  for(i=0;i<131072;i=i+1)dut.u_shared.mem[i]=32'hcccccccc;
  repeat(8)@(negedge lfclk);rst_n=1;
 end
 always @(negedge dut.qingyu_bus_clk)if(dut.qingyu_bus_rst_n&&dut.u_fio.engine_done)done_cycle=cycles;
 always @(posedge dut.qingyu_bus_clk)begin
  cycles=cycles+1;
  if(dut.qingyu_bus_rst_n)begin
   if(full_start<0&&dut.sysfio_icb_cmd_valid&&!dut.sysfio_icb_cmd_read&&dut.sysfio_icb_cmd_addr==32'hf0000008)begin
    full_start=cycles;full_start_ps=longint'($realtime*1000.0);
    if(gpio_words!=0||source_writes!=0||gpio_presented!=0)$fatal(1,"task loading preceded full window");
    $display("Q12_FULL_START cycle=%0d time_ps=%0.0f",cycles,$realtime*1000.0);
   end
   if(full_start>=0&&last_ack<0)begin
    prof_window++;
    if(`MAIN.fabric_mem_icb_cmd_valid)begin if(`MAIN.fabric_mem_icb_cmd_ready)prof_fire++;else prof_stall++;end
    else prof_empty++;
    if(dut.dma_icb_cmd_valid&&!dut.dma_icb_cmd_ready)prof_dma_stall++;
    if(dut.sysmem_icb_cmd_valid&&!dut.sysmem_icb_cmd_ready)prof_shared_stall++;
   end
   if(dut.sysfio_icb_cmd_valid&&dut.sysfio_icb_cmd_ready&&!dut.sysfio_icb_cmd_read&&dut.sysfio_icb_cmd_addr==32'hf0000008)begin
    if(config_cycle>=0)$fatal(1,"duplicate source configuration");config_cycle=cycles;
   end
   if(dut.u_fio.start_command)begin
    if(start_cycle>=0||dut.u_fio.source_words!=input_words||
       dut.u_fio.available_words>32'(source_acked_prefix))
      $fatal(1,"START before acknowledged initial source prefix publication");
    start_cycle=cycles;start_source_acks=source_write_responses;
   end
   // Publication is a real CPU MMIO transaction, following completed shared
   // stores. Streaming requires all nine Rice boundaries in strict order;
   // serial comparison requires one full-packet publication before START.
   if(dut.sysfio_icb_cmd_valid&&dut.sysfio_icb_cmd_ready&&!dut.sysfio_icb_cmd_read&&
      dut.sysfio_icb_cmd_addr==32'hf000003c)begin
    if(full_start<0||publish_commands>=LEDGER||dut.sysfio_icb_cmd_wdata>32'(input_words)||
       dut.sysfio_icb_cmd_wdata<32'(observed_available)||
       dut.sysfio_icb_cmd_wdata>32'(source_acked_prefix)||(publish_commands>0&&start_cycle<0))
      $fatal(1,"published prefix is not a completed next Rice chunk");
    publish_commands++;
   end
   if(dut.u_fio.engine_commit_rsp_valid)begin
    if(dut.u_fio.engine_commit_rsp_error||dut.u_fio.offered_commit_words>32'(source_acked_prefix))
      $fatal(1,"engine commit precedes real source store responses");
    commit_responses++;
   end
   if(`ENG.gate_available<32'(observed_available)||`ENG.gate_available>32'(source_acked_prefix)||
      dut.u_fio.available_words>32'(source_acked_prefix))
    $fatal(1,"available prefix regressed or exceeds acknowledged source stores");
   observed_available=int'(`ENG.gate_available);
   if(dut.shared_cache_clear)clear_count++;
   if(full_start>=0&&last_ack<0&&dut.u_shared.ram_cs)begin
    if(dut.u_shared.ram_we)macro_writes++;else macro_reads++;
   end
   if(last_ack>=0&&dut.dma_icb_cmd_valid)$fatal(1,"DMA offer after final marker ACK");
   // Passive checks on the original GPIO bus. These signals never drive
   // the off-chip model; only its physical REQ/count pins start fixed-rate bursts.
   if(gpio_presented>gpio_requested||gpio_requested>input_words||gpio_word_responses-source_writes>16)
    $fatal(1,"GPIO burst exceeds reserved capacity or source bounds");
   if(gpio_presented!=0&&(gpio_a_oe!=0||gpio_b_oe!=32'h3fe))$fatal(1,"GPIO pad direction conflict");
   if(`PERIPS.gpioA_apb_icb_cmd_valid&&`PERIPS.gpioA_apb_icb_cmd_ready)begin
    if(full_start<0||gpio_a_commands>=LEDGER)$fatal(1,"GPIO access outside window/ledger");
    gpio_a_data_cmd[gpio_a_commands]=`PERIPS.gpioA_apb_icb_cmd_read;
    if(`PERIPS.gpioA_apb_icb_cmd_read)begin
     if(`PERIPS.gpioA_apb_icb_cmd_addr!=32'h10012004||gpio_words>=input_words||
        gpio_words>=gpio_requested||gpio_words>=gpio_presented)
      $fatal(1,"GPIO data read lacks one pending physical word");
     gpio_read_seen[gpio_words]++;gpio_words++;
     if(first_gpio_cycle<0)first_gpio_cycle=cycles;
    end else if((`PERIPS.gpioA_apb_icb_cmd_addr!=32'h10012000&&`PERIPS.gpioA_apb_icb_cmd_addr!=32'h1001201c)||
                 `PERIPS.gpioA_apb_icb_cmd_wdata!=0)$fatal(1,"unexpected GPIOA configuration");
    gpio_a_commands++;
   end
   if(`PERIPS.gpioA_apb_icb_rsp_valid&&`PERIPS.gpioA_apb_icb_rsp_ready)begin
    if(`PERIPS.gpioA_apb_icb_rsp_err||gpio_a_responses>=gpio_a_commands)$fatal(1,"GPIOA response owner/error");
    if(gpio_a_data_cmd[gpio_a_responses])begin
     if(`PERIPS.gpioA_apb_icb_rsp_rdata!==source_image[gpio_word_responses])
      $fatal(1,"GPIO input response corrupt index=%0d",gpio_word_responses);
     gpio_word_ack_seen[gpio_word_responses]++;gpio_word_responses++;last_gpio_read_ack=cycles;
    end
    gpio_a_responses++;
   end
   if(`GPIOA.PSEL&&`GPIOA.PENABLE&&!`GPIOA.PWRITE)begin
    if(`GPIOA.PADDR[11:0]!=12'h004||`GPIOA.PRDATA!==source_image[gpio_apb_reads])
     $fatal(1,"GPIO APB response does not match external word");
    gpio_apb_reads++;
   end
   if(`PERIPS.gpioB_apb_icb_cmd_valid&&`PERIPS.gpioB_apb_icb_cmd_ready)begin
    if(full_start<0)$fatal(1,"GPIOB configuration/loading precedes full window");
    if(`PERIPS.gpioB_apb_icb_cmd_read)begin
     if(`PERIPS.gpioB_apb_icb_cmd_addr!=32'h10040004)$fatal(1,"unexpected GPIOB read");
     gpio_ready_reads++;
    end
   end
   if(`MAIN.qspi0_ro_icb_cmd_valid)$fatal(1,"QSPI source access is forbidden in GPIO experiment");
   if(cpu_held&&(!`MAIN.mem_icb_cmd_valid||{`MAIN.mem_icb_cmd_read,`MAIN.mem_icb_cmd_addr,`MAIN.mem_icb_cmd_wdata,`MAIN.mem_icb_cmd_wmask}!==cpu_held_payload))$fatal(1,"CPU held command changed");
   cpu_held=`MAIN.mem_icb_cmd_valid&&!`MAIN.mem_icb_cmd_ready;
   cpu_held_payload={`MAIN.mem_icb_cmd_read,`MAIN.mem_icb_cmd_addr,`MAIN.mem_icb_cmd_wdata,`MAIN.mem_icb_cmd_wmask};
   if(`MAIN.mem_icb_cmd_valid&&`MAIN.mem_icb_cmd_ready)begin
    if(cpu_commands>=LEDGER)$fatal(1,"CPU ledger overflow");
    cpu_addr[cpu_commands]=`MAIN.mem_icb_cmd_addr;cpu_data[cpu_commands]=`MAIN.mem_icb_cmd_wdata;cpu_read[cpu_commands]=`MAIN.mem_icb_cmd_read;cpu_mask[cpu_commands]=`MAIN.mem_icb_cmd_wmask;
    if(`MAIN.mem_icb_cmd_addr>=32'ha0040000&&`MAIN.mem_icb_cmd_addr<32'ha0040000+4*input_words)begin
     if(!`MAIN.mem_icb_cmd_read)$fatal(1,"CPU source store forbidden in internal DMA candidate");
    end else if(`MAIN.mem_icb_cmd_addr>=32'ha0000000&&`MAIN.mem_icb_cmd_addr<32'ha0000000+OUTPUT_COUNT*4)begin
     if(!`MAIN.mem_icb_cmd_read||last_ack<0)$fatal(1,"CPU modifies output or reads it before completion");
    end else if(`MAIN.mem_icb_cmd_addr>=32'ha0030000&&`MAIN.mem_icb_cmd_addr<32'ha0030010)begin
     if(`MAIN.mem_icb_cmd_read||last_ack<0)$fatal(1,"unexpected diagnostics access");
    end else $fatal(1,"unexpected CPU memory target %h",`MAIN.mem_icb_cmd_addr);
    cpu_commands++;
   end
   if(`MAIN.mem_icb_rsp_valid&&`MAIN.mem_icb_rsp_ready)begin
    if(`MAIN.mem_icb_rsp_err||cpu_responses>=cpu_commands)$fatal(1,"CPU response owner/error");
    if(cpu_addr[cpu_responses]>=32'ha0040000&&cpu_addr[cpu_responses]<32'ha0040000+input_words*4)begin
     index=int'((cpu_addr[cpu_responses]-32'ha0040000)>>2);
     if(cpu_read[cpu_responses])begin if(`MAIN.mem_icb_rsp_rdata!==source_image[index])$fatal(1,"CPU source verification corrupt");end
    end else if(cpu_read[cpu_responses]&&cpu_addr[cpu_responses]>=32'ha0000000&&cpu_addr[cpu_responses]<32'ha0000000+OUTPUT_COUNT*4)begin
     index=int'((cpu_addr[cpu_responses]-32'ha0000000)>>2);
     if(`MAIN.mem_icb_rsp_rdata!==expected[index])$fatal(1,"CPU output verification corrupt");
    end
    cpu_responses++;
   end
   if(dut.gp_cmd_valid&&dut.gp_cmd_ready)begin
    if(full_start<0||last_ack>=0)$fatal(1,"peripheral DMA outside window");
    if(dut.gp_cmd_wmask!=4'hf||dut.gp_cmd_addr!=(dut.gp_cmd_read?32'h10012004:32'h10040008))
     $fatal(1,"peripheral DMA bypassed GPIO register target");
    gp_commands++;
   end
   if(dut.gp_rsp_valid&&dut.gp_rsp_ready)begin
    if(dut.gp_rsp_err||gp_responses>=gp_commands)$fatal(1,"peripheral DMA response error/ownership");
    gp_responses++;
   end
   if(copy_held&&(!dut.copy_cmd_valid||{dut.copy_cmd_read,dut.copy_cmd_addr,dut.copy_cmd_wdata,dut.copy_cmd_wmask}!==copy_held_payload))
    $fatal(1,"input DMA changed stalled request");
   copy_held=dut.copy_cmd_valid&&!dut.copy_cmd_ready;
   copy_held_payload={dut.copy_cmd_read,dut.copy_cmd_addr,dut.copy_cmd_wdata,dut.copy_cmd_wmask};
   if(dut.copy_cmd_valid&&dut.copy_cmd_ready)begin
    if(full_start<0||last_ack>=0||copy_commands>=input_words||dut.copy_cmd_read||dut.copy_cmd_wmask!=4'hf||
       dut.copy_cmd_addr!=32'ha0040000+32'(copy_commands)*4)$fatal(1,"input DMA target/order");
    index=copy_commands;
    if(source_write_seen[index]!=0||dut.copy_cmd_wdata!==source_image[index]||gpio_read_seen[index]!=1||gpio_word_ack_seen[index]!=1)
     $fatal(1,"input DMA store lacks completed GPIO read");
    source_write_seen[index]++;source_writes++;if(first_source_cycle<0)first_source_cycle=cycles;
    copy_addr[index]=dut.copy_cmd_addr;copy_data[index]=dut.copy_cmd_wdata;copy_commands++;
   end
   if(dut.copy_rsp_valid&&dut.copy_rsp_ready)begin
    if(dut.copy_rsp_err||copy_responses>=copy_commands)$fatal(1,"input DMA response ownership/error");
    index=copy_responses;
    if(source_write_ack_seen[index]!=0)$fatal(1,"duplicate input DMA response");
    source_write_ack_seen[index]++;source_write_responses++;last_source_ack=cycles;
    while(source_acked_prefix<input_words&&source_write_ack_seen[source_acked_prefix]==1)source_acked_prefix++;
    copy_responses++;
   end
   if(dma_held&&(!dut.dma_icb_cmd_valid||{dut.dma_icb_cmd_read,dut.dma_icb_cmd_addr,dut.dma_icb_cmd_wdata,dut.dma_icb_cmd_wmask}!==held_payload))$fatal(1,"DMA held command changed");
   dma_held=dut.dma_icb_cmd_valid&&!dut.dma_icb_cmd_ready;
   held_payload={dut.dma_icb_cmd_read,dut.dma_icb_cmd_addr,dut.dma_icb_cmd_wdata,dut.dma_icb_cmd_wmask};
   if(dut.dma_icb_cmd_valid&&dut.dma_icb_cmd_ready)begin
    if(start_cycle<0||commands>=32768||final_offered)$fatal(1,"DMA command ordering/overflow");
    if(dut.dma_icb_cmd_addr[1:0]!=0||dut.dma_icb_cmd_wmask!=4'hf)$fatal(1,"DMA alignment/mask");
    dma_addr[commands]=dut.dma_icb_cmd_addr;dma_data[commands]=dut.dma_icb_cmd_wdata;dma_read[commands]=dut.dma_icb_cmd_read;
    if(dut.dma_icb_cmd_read)begin
     if(first_read<0)begin first_read=cycles;if(clear_count!=1)$fatal(1,"task shared readcache not cold");end
     if(dut.dma_icb_cmd_addr<32'ha0040000||dut.dma_icb_cmd_addr>=32'ha0040000+input_words*4)$fatal(1,"DMA read outside source");
     index=int'((dut.dma_icb_cmd_addr-32'ha0040000)>>2);
     if(read_seen[index]!=0||source_write_seen[index]!=1||source_write_ack_seen[index]!=1||
        index>=source_acked_prefix||index>=int'(`ENG.gate_available))$fatal(1,"DMA source read before per-word store ACK and published prefix");
     if(index>=10&&!invalidation_acked)$fatal(1,"data read before invalidation ACK");
     read_seen[index]++;reads++;
    end else begin
     if(dut.dma_icb_cmd_addr<32'ha0000000||dut.dma_icb_cmd_addr>=32'ha0000000+OUTPUT_COUNT*4)$fatal(1,"DMA write outside dense output");
     index=int'((dut.dma_icb_cmd_addr-32'ha0000000)>>2);
     if(index==0&&write_seen[0]==0)begin
      if(dut.dma_icb_cmd_wdata!=0||writes!=0||reads!=10)$fatal(1,"missing initial invalidation");
     end else begin
      if(dut.dma_icb_cmd_wdata!==expected[index])$fatal(1,"wrong dense output index=%0d got=%h expected=%h",index,dut.dma_icb_cmd_wdata,expected[index]);
      if(index==0)begin
       if(write_seen[0]!=1||writes!=OUTPUT_COUNT||write_responses!=OUTPUT_COUNT)$fatal(1,"marker precedes every payload/metadata ACK");
       final_offered=1;
      end else if(write_seen[index]!=0)$fatal(1,"duplicate output write");
     end
     write_seen[index]++;writes++;
    end
    commands++;
   end
   // Match each original-fabric request against the ordered accepted stream of
   // one real master. The GPIO input uses the original peripheral bus; this memory fabric routes shared SRAM.
   if(fabric_held&&(!`MAIN.fabric_mem_icb_cmd_valid||{`MAIN.fabric_mem_icb_cmd_read,`MAIN.fabric_mem_icb_cmd_addr,`MAIN.fabric_mem_icb_cmd_wdata,`MAIN.fabric_mem_icb_cmd_wmask}!==fabric_held_payload))$fatal(1,"fabric held request changed");
   fabric_held=`MAIN.fabric_mem_icb_cmd_valid&&!`MAIN.fabric_mem_icb_cmd_ready;
   fabric_held_payload={`MAIN.fabric_mem_icb_cmd_read,`MAIN.fabric_mem_icb_cmd_addr,`MAIN.fabric_mem_icb_cmd_wdata,`MAIN.fabric_mem_icb_cmd_wmask};
   if(`MAIN.fabric_mem_icb_cmd_valid&&`MAIN.fabric_mem_icb_cmd_ready)begin
    if(fabric_commands>=LEDGER)$fatal(1,"fabric ledger overflow");
    cpu_match=cpu_routed<cpu_commands&&cpu_addr[cpu_routed]===`MAIN.fabric_mem_icb_cmd_addr&&cpu_read[cpu_routed]===`MAIN.fabric_mem_icb_cmd_read&&cpu_mask[cpu_routed]===`MAIN.fabric_mem_icb_cmd_wmask&&(cpu_read[cpu_routed]||cpu_data[cpu_routed]===`MAIN.fabric_mem_icb_cmd_wdata);
    dma_match=dma_routed<commands&&dma_addr[dma_routed]===`MAIN.fabric_mem_icb_cmd_addr&&dma_read[dma_routed]===`MAIN.fabric_mem_icb_cmd_read&&`MAIN.fabric_mem_icb_cmd_wmask==4'hf&&(dma_read[dma_routed]||dma_data[dma_routed]===`MAIN.fabric_mem_icb_cmd_wdata);
    copy_match=copy_routed<copy_commands&&copy_addr[copy_routed]===`MAIN.fabric_mem_icb_cmd_addr&&
       !`MAIN.fabric_mem_icb_cmd_read&&`MAIN.fabric_mem_icb_cmd_wmask==4'hf&&copy_data[copy_routed]===`MAIN.fabric_mem_icb_cmd_wdata;
    if(cpu_match)cpu_routed++;else if(dma_match)dma_routed++;else if(copy_match)copy_routed++;
    else $fatal(1,"fabric request has no CPU/compute-DMA/input-DMA origin");
    fabric_read[fabric_commands]=`MAIN.fabric_mem_icb_cmd_read;
    if(`MAIN.fabric_mem_icb_cmd_addr>=32'ha0000000&&`MAIN.fabric_mem_icb_cmd_addr<32'ha0080000)begin
     fabric_target_index[fabric_commands]=fabric_shared;
     shared_addr[fabric_shared]=`MAIN.fabric_mem_icb_cmd_addr;shared_data[fabric_shared]=`MAIN.fabric_mem_icb_cmd_wdata;
     shared_read[fabric_shared]=`MAIN.fabric_mem_icb_cmd_read;shared_mask[fabric_shared]=`MAIN.fabric_mem_icb_cmd_wmask;fabric_shared++;
    end else $fatal(1,"unexpected original fabric target");
    fabric_commands++;
   end
   if(shared_held&&(!dut.sysmem_icb_cmd_valid||{dut.sysmem_icb_cmd_read,dut.sysmem_icb_cmd_addr,dut.sysmem_icb_cmd_wdata,dut.sysmem_icb_cmd_wmask}!==shared_held_payload))$fatal(1,"shared held request changed");
   shared_held=dut.sysmem_icb_cmd_valid&&!dut.sysmem_icb_cmd_ready;
   shared_held_payload={dut.sysmem_icb_cmd_read,dut.sysmem_icb_cmd_addr,dut.sysmem_icb_cmd_wdata,dut.sysmem_icb_cmd_wmask};
   if(dut.sysmem_icb_cmd_valid&&dut.sysmem_icb_cmd_ready)begin
    if(shared_commands>=fabric_shared||dut.sysmem_icb_cmd_addr!==shared_addr[shared_commands]||dut.sysmem_icb_cmd_read!==shared_read[shared_commands]||dut.sysmem_icb_cmd_wmask!==shared_mask[shared_commands]||(!shared_read[shared_commands]&&dut.sysmem_icb_cmd_wdata!==shared_data[shared_commands]))$fatal(1,"original fabric to shared route mismatch");
    shared_commands++;
   end
   if(dut.sysmem_icb_rsp_valid&&dut.sysmem_icb_rsp_ready)begin
    if(shared_responses>=shared_commands||dut.sysmem_icb_rsp_err)$fatal(1,"shared response mismatch");
    shared_rsp_data[shared_responses]=dut.sysmem_icb_rsp_rdata;shared_responses++;
   end
   if(`MAIN.fabric_mem_icb_rsp_valid&&`MAIN.fabric_mem_icb_rsp_ready)begin
    if(fabric_responses>=fabric_commands||`MAIN.fabric_mem_icb_rsp_err)$fatal(1,"fabric response owner/error");
    target_index=fabric_target_index[fabric_responses];
    if(target_index>=shared_responses||(fabric_read[fabric_responses]&&`MAIN.fabric_mem_icb_rsp_rdata!==shared_rsp_data[target_index]))$fatal(1,"fabric shared response not retired from original target");
    fabric_responses++;
   end
   if(dut.dma_icb_rsp_valid&&dut.dma_icb_rsp_ready)begin
    if(responses>=commands||dut.dma_icb_rsp_err)$fatal(1,"DMA response owner/error");
    if(dma_read[responses])begin
     index=int'((dma_addr[responses]-32'ha0040000)>>2);
     if(dut.dma_icb_rsp_rdata!==source_image[index])$fatal(1,"DMA source response corrupt");read_responses++;
    end else begin
     write_responses++;
     if(dma_addr[responses]==32'ha0000000)begin
      if(dma_data[responses]==0)invalidation_acked=1;
      else begin
       if(dma_data[responses]!=32'h32443151||responses+1!=commands)$fatal(1,"invalid final ACK");
       last_ack=cycles;last_ack_ps=longint'($realtime*1000.0);$display("Q12_FULL_END cycle=%0d time_ps=%0.0f",cycles,$realtime*1000.0);
      end
     end
    end
    responses++;
   end
   if(commands-responses>peak_pending)peak_pending=commands-responses;
   if(host_valid)begin
    if(host_code!=1)$fatal(1,"firmware failed host=%h PC=%h",host_code,`CPU.inspect_pc);
    if(`MERGE.NP!=2||`MERGE.count_q!=0||`TRANS.busy||`TRANS.draining||clear_count!=1)$fatal(1,"CPU/DMA hardware queues or cold-cache contract mismatch");
    if(full_start<0||config_cycle<full_start||first_gpio_cycle<config_cycle||last_source_ack<first_gpio_cycle||
       start_cycle<=config_cycle||first_read<start_cycle||last_ack<first_read||last_ack<last_source_ack||done_cycle<=last_ack)$fatal(1,"full window/load/compute ordering");
    if(source_acked_prefix!=input_words||(publish_commands!=0&&commit_responses!=publish_commands-1)||
       observed_available!=input_words)
      $fatal(1,"all source chunks/publications/commit responses must drain before completion");
    if(gpio_first_data_ps<full_start_ps||gpio_last_data_ps>last_ack_ps||gpio_presented!=input_words||gpio_requested!=input_words||
       gpio_apb_reads!=input_words||gpio_a_commands!=gpio_a_responses)
     $fatal(1,"GPIO burst/presentation and original APB transfer/window mismatch");
    if(prof_window!=last_ack-full_start+1||prof_window!=prof_fire+prof_stall+prof_empty)$fatal(1,"profile cycle partition mismatch");
    if(copy_commands!=input_words||copy_responses!=input_words||copy_routed!=input_words||
       gp_commands!=input_words+gpio_bursts||gp_responses!=gp_commands||dut.u_gpio_dma.busy||dut.u_gpio_dma.error_q)
     $fatal(1,"input DMA original bus accounting mismatch");
    if(reads!=input_words||writes!=WRITE_COUNT||responses!=commands||read_responses!=reads||write_responses!=writes||
       gpio_words!=input_words||gpio_word_responses!=input_words||source_writes!=input_words||source_write_responses!=input_words||
       cpu_commands!=cpu_responses||cpu_routed!=cpu_commands||dma_routed!=commands||fabric_commands!=cpu_commands+commands+copy_commands||fabric_responses!=fabric_commands||
       fabric_shared!=shared_commands||shared_commands!=shared_responses||fabric_commands!=shared_commands)$fatal(1,"CPU/GPIO/DMA/fabric/shared conservation failure");
    mismatches=0;
    for(i=0;i<OUTPUT_COUNT;i=i+1)begin
     if(dut.u_shared.mem[i]!==expected[i])mismatches++;
     expected_writes=i==0?2:1;if(write_seen[i]!=expected_writes)$fatal(1,"output write coverage index=%0d",i);
    end
    for(i=0;i<input_words;i=i+1)begin
     if(dut.u_shared.mem[65536+i]!==source_image[i]||read_seen[i]!=1||source_write_seen[i]!=1||
        source_write_ack_seen[i]!=1||gpio_read_seen[i]!=1||gpio_word_ack_seen[i]!=1)mismatches++;
     if(u_source.image[i]!==source_image[i])$fatal(1,"external GPIO source ROM mutated");
    end
    for(i=OUTPUT_COUNT;i<131072;i=i+1)
     if(!(i>=65536&&i<65536+input_words)&&!(i>=49152&&i<=49155)&&dut.u_shared.mem[i]!==32'hcccccccc)mismatches++;
    for(i=0;i<8192;i=i+1)if(`ITCM.mem_r[i]!==firmware[i])$fatal(1,"instruction image modified");
    if(mismatches)$fatal(1,"output/source/guards mismatches=%0d",mismatches);
    if(dump_requested)begin
     dump_fd=$fopen(output_dump_path,"w");if(!dump_fd)$fatal(1,"cannot create output dump");
     for(i=0;i<OUTPUT_COUNT;i=i+1)$fdisplay(dump_fd,"%08x",dut.u_shared.mem[i]);$fclose(dump_fd);
    end
    if(dut.u_fio.task_cycles!=32'(done_cycle-start_cycle+1))$fatal(1,"engine cycle counter mismatch");
    $display("Q12GPIO_CLOCK core_period_ps=6666 core_assumed_hz=150000000");
    $display("Q12SOC_PHASES core=%0d load=%0d factor=%0d cache=%0d compute=%0d store=%0d",dut.u_fio.core_cycles,dut.u_fio.load_cycles,dut.u_fio.factor_cycles,dut.u_fio.cache_cycles,dut.u_fio.compute_cycles,dut.u_fio.store_cycles);
    $display("Q12GPIO_METRICS layer=%0d full_window_cycles=%0d start_to_ack=%0d first_read_to_ack=%0d first_gpio=%0d last_gpio_read_ack=%0d first_source=%0d last_source_ack=%0d done_delay=%0d engine_counter=%0d reads=%0d writes=%0d cpu_commands=%0d cpu_responses=%0d gpio_words=%0d gpio_word_responses=%0d source_writes=%0d source_write_responses=%0d fabric_commands=%0d fabric_responses=%0d shared_commands=%0d shared_responses=%0d dma_responses=%0d peak_pending=%0d gpio_presented=%0d gpio_requested=%0d gpio_bursts=%0d gpio_apb_reads=%0d gpio_ready_reads=%0d window_bus_fire=%0d window_bus_stall=%0d window_bus_empty=%0d dma_stall=%0d shared_stall=%0d input_words=%0d cache_clear=%0d macro_reads=%0d macro_writes=%0d start_source_acks=%0d publish_commands=%0d commit_responses=%0d serial_load=%0d firmware_cycles=%0d",layer,last_ack-full_start+1,last_ack-start_cycle+1,last_ack-first_read+1,first_gpio_cycle,last_gpio_read_ack,first_source_cycle,last_source_ack,done_cycle-last_ack,dut.u_fio.task_cycles,reads,writes,cpu_commands,cpu_responses,gpio_words,gpio_word_responses,source_writes,source_write_responses,fabric_commands,fabric_responses,shared_commands,shared_responses,responses,peak_pending,gpio_presented,gpio_requested,gpio_bursts,gpio_apb_reads,gpio_ready_reads,prof_fire,prof_stall,prof_empty,prof_dma_stall,prof_shared_stall,input_words,clear_count,macro_reads,macro_writes,start_source_acks,publish_commands,commit_responses,serial_load,{dut.u_shared.mem[49153],dut.u_shared.mem[49152]});
    $display("PASS real E203 Q12 GPIO cold task; original GPIOA/B pins, internal peripheral DMA, NP2 original System Bus, fixed12 input (no entropy coding), plain shared SRAM (no readcache); 12689 dense words/source/guards verified");
    #1;$finish;
   end
  end
  if(cycles%1000000==0)$display("Q12GPIO_PROGRESS cycles=%0d gpio_words=%0d gpio_requested=%0d source_writes=%0d start_cycle=%0d last_ack=%0d PC=%h",cycles,gpio_words,gpio_requested,source_writes,start_cycle,last_ack,`CPU.inspect_pc);
  if(cycles>20000000)$fatal(1,"timeout PC=%h engine_state=%0d error=%h gpio_words=%0d gpio_requested=%0d source_writes=%0d",`CPU.inspect_pc,`ENG.state,dut.u_fio.engine_error_code,gpio_words,gpio_requested,source_writes);
 end
endmodule
