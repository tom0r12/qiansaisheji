`timescale 1ns/1ps
`include "e203_defines.v"
module tb_qingyu_soc;
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
`define SHARED dut.u_shared.u_storage
 reg [63:0] firmware [0:8191];
 reg [31:0] expected [0:25343];
 reg [31:0] shared_image[0:131071];
 reg [31:0] mailbox[0:4];
 reg [16:0] shared_address=0;
 reg [12:0] itcm_address=0;
 reg [13:0] dtcm_address=0;
 reg [31:0] shared_din=0;
 reg [63:0] itcm_din=0;
 reg shared_cs=0,itcm_cs=0,dtcm_cs=0,shared_we=1;
 integer i, mismatches=0, cycles=0;
 task attach_shared_loader;
  begin
   force `SHARED.clk=clk;
   force `SHARED.cs=shared_cs;
   force `SHARED.we=shared_we;
   force `SHARED.addr=shared_address;
   force `SHARED.din=shared_din;
   force `SHARED.wem=4'hf;
  end
 endtask
 task release_shared_loader;
  begin
   release `SHARED.cs; release `SHARED.we; release `SHARED.addr;
   release `SHARED.din; release `SHARED.wem; release `SHARED.clk;
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
  for(i=0;i<131072;i=i+1) begin
   @(negedge clk);
   shared_cs=1; shared_address=i; shared_din=shared_image[i];
   itcm_cs=(i<8192); itcm_address=i; itcm_din=(i<8192)?firmware[i]:64'b0;
   dtcm_cs=(i<16384); dtcm_address=i;
   @(posedge clk);#2;
  end
  @(negedge clk); shared_cs=0;itcm_cs=0;dtcm_cs=0;
  #1;
  release_shared_loader;
  release `ITCM.cs;release `ITCM.we;release `ITCM.addr;release `ITCM.din;release `ITCM.wem;release `ITCM.clk;
  release `DTCM.cs;release `DTCM.we;release `DTCM.addr;release `DTCM.din;release `DTCM.wem;release `DTCM.clk;
  $display("QINGYU_MACRO_PRELOAD_COMPLETE: ITCM firmware; shared image; DTCM zero initialized; CPU still reset");
  $readmemh(expected_path,expected);
  // Give the real 32.768 kHz AON domain sufficient reset clock edges.
  repeat(8) @(negedge lfclk);
  rst_n=1;
 end
 always @(posedge clk) begin
  cycles<=cycles+1;
  if(cycles==30000000) $fatal(1,"SoC timeout PC=%h",`CPU.inspect_pc);
  if(cycles%100000==0 && cycles>0) $display("SoC progress cycles=%0d PC=%h",cycles,`CPU.inspect_pc);
 end
 // Independently read the physical shared-memory macro ports after completion.
 // Final output checks are not based on a shadow copy of write-bus data.
 initial begin
  wait(host_valid===1'b1);
  if(host_code!==32'd1) $fatal(1,"macro SoC firmware failed code=%h",host_code);
  @(negedge clk);shared_cs=0;shared_we=0;
  attach_shared_loader;
  for(integer j=0;j<25344;j=j+1) begin
   @(negedge clk);shared_cs=1;shared_address=16384+j;
   @(posedge clk);#2;
   if(`SHARED.dout !== expected[j]) begin
    if(mismatches<8) $display("macro readback mismatch i=%0d actual=%h expected=%h",j,`SHARED.dout,expected[j]);
    mismatches=mismatches+1;
   end
  end
  for(integer j=0;j<5;j=j+1) begin
   @(negedge clk);shared_cs=1;shared_address=49152+j;
   @(posedge clk);#2;mailbox[j]=`SHARED.dout;
  end
  @(negedge clk);shared_cs=0;#1;release_shared_loader;
  if(mismatches) $fatal(1,"macro SoC output mismatches=%0d",mismatches);
  $display("QINGYU_MACRO_MAILBOX outer_cycles=%0d driver_cycles=%0d compute_cycles=%0d",{mailbox[3],mailbox[2]},{mailbox[1],mailbox[0]},mailbox[4]);
  $display("PASS real E203 + 89 SRAM macros: 25344 physical readback outputs, cycles=%0d",cycles);
  $finish;
 end
`undef CPU
`undef ITCM
`undef DTCM
`undef SHARED
endmodule
