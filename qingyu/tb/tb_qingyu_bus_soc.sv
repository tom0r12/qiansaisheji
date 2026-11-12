`timescale 1ns/1ps
`include "e203_defines.v"
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
`define ITCM `CPU.u_e203_srams.u_e203_itcm_ram.u_e203_itcm_gnrl_ram.u_sirv_sim_ram
 reg [63:0] firmware [0:8191];
 reg [31:0] expected [0:25343];
 integer i, mismatches=0, cycles=0;
 reg [1023:0] fw_path, shared_path, expected_path;
 initial begin
  if (!$value$plusargs("FIRMWARE=%s",fw_path)) $fatal(1,"missing FIRMWARE");
  if (!$value$plusargs("SHARED=%s",shared_path)) $fatal(1,"missing SHARED");
  if (!$value$plusargs("EXPECTED=%s",expected_path)) $fatal(1,"missing EXPECTED");
  $readmemh(fw_path,firmware);
  for(i=0;i<8192;i=i+1) `ITCM.mem_r[i]=firmware[i];
  $readmemh(shared_path,dut.u_shared.mem);
  $readmemh(expected_path,expected);
  // Give the real 32.768 kHz AON domain sufficient reset clock edges.
  repeat(8) @(negedge lfclk);
  rst_n=1;
 end
 always @(posedge clk) begin
  cycles<=cycles+1;
  if(host_valid) begin
   if(host_code!=1) $fatal(1,"firmware failed code=%h cycles=%0d",host_code,cycles);
`ifdef QINGYU_OUT16
   for(i=0;i<12672;i=i+1) begin  // 25344 INT16 results, two per word
`else
   for(i=0;i<25344;i=i+1) begin
`endif
    if(dut.u_shared.mem[16384+i] !== expected[i]) begin
     if(mismatches<8) $display("mismatch i=%0d actual=%h expected=%h",i,dut.u_shared.mem[16384+i],expected[i]);
     mismatches=mismatches+1;
    end
   end
   if(mismatches) $fatal(1,"SoC output mismatches=%0d",mismatches);
   $display("PASS real E203 + driver + full official SoC peripherals: 25344 outputs, cycles=%0d, driver_task_cycles=%0d",cycles,{dut.u_shared.mem[49153],dut.u_shared.mem[49152]});
   #1; $finish; // allow the independent route monitor to finish its checks
  end
  if(cycles==30000000) $fatal(1,"SoC timeout PC=%h",`CPU.inspect_pc);
  if(cycles%100000==0 && cycles>0) $display("SoC progress cycles=%0d PC=%h",cycles,`CPU.inspect_pc);
 end
endmodule
