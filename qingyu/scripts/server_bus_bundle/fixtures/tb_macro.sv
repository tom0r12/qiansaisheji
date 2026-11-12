`timescale 1ns/1ps
`include "e203_defines.v"
// Single-port macro preload/readback fixture. Forces end before CPU boot.
module tb_qingyu_bus_soc;
 reg clk=0, lfclk=0, rst_n=0;
 always #3.333333 clk=~clk;
 always #15258.789 lfclk=~lfclk;
 wire host_valid; wire [31:0] host_code;
 qingyu_e203_soc_top dut(
  .qingyu_host_valid(host_valid), .qingyu_host_code(host_code),
  .hfextclk(clk), .hfxoscen(), .lfextclk(lfclk), .lfxoscen(),
  .io_pads_jtag_TCK_i_ival(1'b0), .io_pads_jtag_TMS_i_ival(1'b1),
  .io_pads_jtag_TDI_i_ival(1'b0),
  .io_pads_gpioA_i_ival(32'b0), .io_pads_gpioB_i_ival(32'b0),
  .io_pads_qspi0_dq_0_i_ival(1'b1), .io_pads_qspi0_dq_1_i_ival(1'b1),
  .io_pads_qspi0_dq_2_i_ival(1'b1), .io_pads_qspi0_dq_3_i_ival(1'b1),
  .io_pads_aon_erst_n_i_ival(rst_n),
  .io_pads_dbgmode0_n_i_ival(1'b1), .io_pads_dbgmode1_n_i_ival(1'b1),
  .io_pads_dbgmode2_n_i_ival(1'b1), .io_pads_bootrom_n_i_ival(1'b0),
  .io_pads_aon_pmu_dwakeup_n_i_ival(1'b1)
 );
`define CPU dut.u_e203_subsys_top.u_e203_subsys_main.u_e203_cpu_top
`define ITCM `CPU.u_e203_srams.u_e203_itcm_ram.u_e203_itcm_gnrl_ram.u_storage
`define DTCM `CPU.u_e203_srams.u_e203_dtcm_ram.u_e203_dtcm_gnrl_ram.u_storage
`define SHARED dut.u_shared
 reg [63:0] firmware [0:8191];
 reg [31:0] expected [0:25343];
 reg [31:0] shared_image[0:131071];
 reg [31:0] perf_mailbox[0:4];
 reg [16:0] shared_address=0;
 reg [12:0] itcm_address=0;
 reg [13:0] dtcm_address=0;
 reg [31:0] shared_din=0;
 reg [63:0] itcm_din=0;
 reg shared_cs=0,itcm_cs=0,dtcm_cs=0,shared_we=1;
 wire loader_read=!shared_we;
 wire [31:0] loader_address={13'h1400,shared_address,2'b00};
 reg assessment_done=0, runtime_enabled=0, shared_reset=0;
 integer preload_commands=0,preload_responses=0;
 integer i, mismatches=0, cycles=0;
 // Preload through the single shared-memory macro interface before boot.
 task attach_shared_loader;
  begin
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
   release `SHARED.rst_n; release `SHARED.clk;
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
 reg [1023:0] fw_path, shared_path, expected_path;
 initial begin
  if (!$value$plusargs("FIRMWARE=%s",fw_path)) $fatal(1,"missing FIRMWARE");
  if (!$value$plusargs("SHARED=%s",shared_path)) $fatal(1,"missing SHARED");
  if (!$value$plusargs("EXPECTED=%s",expected_path)) $fatal(1,"missing EXPECTED");
  $readmemh(fw_path,firmware);
  $readmemh(shared_path,shared_image);
  // CPU remains in reset. Load through real macro write ports; no access to
  // vendor-private arrays. These simulation-only forces are released before boot.
  attach_shared_loader;
  force `ITCM.clk=clk; force `ITCM.cs=itcm_cs; force `ITCM.we=1'b1;
  force `ITCM.addr=itcm_address; force `ITCM.din=itcm_din; force `ITCM.wem=8'hff;
  force `DTCM.clk=clk; force `DTCM.cs=dtcm_cs; force `DTCM.we=1'b1;
  force `DTCM.addr=dtcm_address; force `DTCM.din=32'b0; force `DTCM.wem=4'hf;
  // A four-state simulator must observe actual reset edges before a zero-ACK
  // wrapper is used. The runtime scoreboard stays disabled during this loader.
  repeat(4)@(negedge clk);
  shared_reset=1;
  for(i=0;i<131072;i=i+1) begin
   @(negedge clk);
   shared_cs=1; shared_address=i; shared_din=shared_image[i];
   itcm_cs=(i<8192); itcm_address=i; itcm_din=(i<8192)?firmware[i]:64'b0;
   dtcm_cs=(i<16384); dtcm_address=i;
   preload_shared_word();
  end
  @(negedge clk); shared_cs=0;itcm_cs=0;dtcm_cs=0;
  @(posedge clk); #1;
  release_shared_loader;
  release `ITCM.cs;release `ITCM.we;release `ITCM.addr;release `ITCM.din;release `ITCM.wem;release `ITCM.clk;
  release `DTCM.cs;release `DTCM.we;release `DTCM.addr;release `DTCM.din;release `DTCM.wem;release `DTCM.clk;
  if(preload_commands!=131072||preload_responses!=131072)$fatal(1,"incomplete physical shared preload");
  $display("QINGYU_MACRO_PRELOAD_COMPLETE commands=%0d responses=%0d CPU_reset=%b",preload_commands,preload_responses,rst_n);
  $readmemh(expected_path,expected);
  // Give the real 32.768 kHz AON domain sufficient reset clock edges.
  repeat(8) @(negedge lfclk);
  runtime_enabled=1;rst_n=1;
 end
 always @(posedge clk) begin
  cycles<=cycles+1;
  if(cycles==30000000) $fatal(1,"SoC timeout PC=%h",`CPU.inspect_pc);
  if(cycles%100000==0 && cycles>0) $display("SoC progress cycles=%0d PC=%h",cycles,`CPU.inspect_pc);
 end
 // Independently read the physical shared-memory macros after completion
 // (single-port read; data comes from the addressed physical macros).
 initial begin
  wait(host_valid===1'b1);
  assessment_done=1;
  if(host_code!==32'd1) $fatal(1,"macro SoC firmware failed code=%h",host_code);
  @(negedge clk);shared_cs=0;shared_we=0;
  attach_shared_loader;
  for(integer j=0;j<12672;j=j+1) begin
   read_shared_word(17'(16384+j),readback_data);
   if(readback_data !== expected[j]) begin
    if(mismatches<8)$display("macro readback mismatch i=%0d actual=%h expected=%h",j,readback_data,expected[j]);
    mismatches++;
   end
  end
  for(integer j=0;j<5;j=j+1)read_shared_word(17'(49152+j),perf_mailbox[j]);
  @(negedge clk);shared_cs=0;
  @(posedge clk);#1;release_shared_loader;
  if(mismatches) $fatal(1,"macro SoC output mismatches=%0d",mismatches);
  $display("QINGYU_MACRO_MAILBOX outer_cycles=%0d driver_cycles=%0d compute_cycles=%0d",{perf_mailbox[3],perf_mailbox[2]},{perf_mailbox[1],perf_mailbox[0]},perf_mailbox[4]);
  $display("PASS real E203 + official bus + physical SRAM: 25344 physical readback outputs, cycles=%0d",cycles);
  $finish;
 end
`undef CPU
`undef ITCM
`undef DTCM
`undef SHARED
endmodule
