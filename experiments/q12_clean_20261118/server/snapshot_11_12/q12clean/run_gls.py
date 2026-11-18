"""Pre-CTS SDF-annotated Gate-Level Simulation of whole-SoC mapped.v (layer00_sample000).

Generates TT SDF via PrimeTime, back-annotates IOPATH cell delays onto mapped.v with
official SCC40NLL RVT standard-cell Verilog + manufacturer SRAM Verilog models,
disables pre-CTS un-balanced clock-gate / async-GPIO-synchronizer specify notifier
toggling (+notimingcheck, since timing is verified across corners by PrimeTime STA),
and checks 131,072-word preload + full cold GPIO task + 12,689-word bit-exact output.
"""
from pathlib import Path
import argparse, json, os, re, shutil, subprocess, sys

TB_GLS = r'''`timescale 1ns/1ps
module q12_gpio_source_gls #(parameter integer WORDS=8873)(
 input wire req,input wire[7:0]count,input wire[8:0]oe,
 output reg[31:0]data,output reg ready,
 output integer presented_words,requested_words,burst_requests,
 output reg[63:0]first_data_ps,last_data_ps
);
 reg[31:0]image[0:WORDS-1];reg[1023:0]input_path;
 integer input_words,k,n;reg previous_req,transmitting=0;
 real period_ns=26.664,access_ns=1.0;
 localparam real SETTLE_NS=0.2;
 initial begin
  data=0;ready=0;presented_words=0;requested_words=0;burst_requests=0;first_data_ps=0;last_data_ps=0;
  if(!$value$plusargs("INPUT=%s",input_path))$fatal(1,"GPIO missing INPUT");
  if(!$value$plusargs("INPUT_WORDS=%d",input_words))$fatal(1,"GPIO missing INPUT_WORDS");
  if(input_words<1||input_words>WORDS)$fatal(1,"GPIO capacity exceeded");
  for(k=0;k<input_words;k++)image[k]=32'bx;
  $readmemh(input_path,image,0,input_words-1);
  for(k=0;k<input_words;k++)if(^image[k]===1'bx)$fatal(1,"GPIO incomplete image");
  wait(oe===9'h1ff);
  #0.2;
  if(req!==0)$fatal(1,"GPIO request must start low");
  ready=1;
  forever begin
   @(req);
   #(SETTLE_NS);
   n=int'(count);previous_req=req;
   if(n<1||n>255||requested_words+n>input_words||oe!==9'h1ff)
    $fatal(1,"GPIO invalid burst req=%b count=%b n=%0d oe=%b",req,count,n,oe);
   requested_words+=n;burst_requests++;transmitting=1;
   for(k=0;k<n;k++)begin
    if(k==0)#(access_ns-SETTLE_NS);else #(period_ns);
    if(req!==previous_req||count!==8'(n)||oe!==9'h1ff)$fatal(1,"GPIO changed burst while transmitting");
    data=image[presented_words];
    if(presented_words==0)first_data_ps=longint'($realtime*1000.0);
    presented_words++;last_data_ps=longint'($realtime*1000.0);
   end
   transmitting=0;
  end
 end
 always @(oe)begin #0.2; if(presented_words!=0&&oe!==9'h1ff)$fatal(1,"GPIO output disabled mid-task"); end
 always @(req)if(transmitting&&req!==previous_req)$fatal(1,"GPIO burst overlap");
endmodule

module tb_gls;
 reg clk=0,lfclk=0,rst_n=0;
 always #3.333333 clk=~clk;
 always #15258.789 lfclk=~lfclk;
 wire host_valid; wire [31:0] host_code;
 wire [31:0] gpio_data,gpio_b_out,gpio_b_oe,gpio_a_oe;
 wire gpio_ready;
 integer gpio_presented,gpio_requested,gpio_bursts;
 wire [63:0] gpio_first_data_ps,gpio_last_data_ps;

 q12_gpio_source_gls #(.WORDS(8873)) u_source(
  .req(gpio_b_out[1]),.count(gpio_b_out[9:2]),.oe(gpio_b_oe[9:1]),.data(gpio_data),.ready(gpio_ready),
  .presented_words(gpio_presented),.requested_words(gpio_requested),.burst_requests(gpio_bursts),
  .first_data_ps(gpio_first_data_ps),.last_data_ps(gpio_last_data_ps));

 qingyu_e203_soc_top dut(
  .qingyu_host_valid(host_valid),.qingyu_host_code(host_code),
  .hfextclk(clk),.hfxoscen(),.lfextclk(lfclk),.lfxoscen(),
  .io_pads_jtag_TCK_i_ival(1'b0),.io_pads_jtag_TMS_i_ival(1'b1),.io_pads_jtag_TDI_i_ival(1'b0),
  .io_pads_jtag_TDO_o_oval(),.io_pads_jtag_TDO_o_oe(),
  .io_pads_gpioA_i_ival(gpio_data),.io_pads_gpioA_o_oval(),.io_pads_gpioA_o_oe(gpio_a_oe),
  .io_pads_gpioB_i_ival({31'b0,gpio_ready}),.io_pads_gpioB_o_oval(gpio_b_out),.io_pads_gpioB_o_oe(gpio_b_oe),
  .io_pads_qspi0_sck_o_oval(),.io_pads_qspi0_cs_0_o_oval(),
  .io_pads_qspi0_dq_0_i_ival(1'b1),.io_pads_qspi0_dq_0_o_oval(),.io_pads_qspi0_dq_0_o_oe(),
  .io_pads_qspi0_dq_1_i_ival(1'b1),.io_pads_qspi0_dq_1_o_oval(),.io_pads_qspi0_dq_1_o_oe(),
  .io_pads_qspi0_dq_2_i_ival(1'b1),.io_pads_qspi0_dq_2_o_oval(),.io_pads_qspi0_dq_2_o_oe(),
  .io_pads_qspi0_dq_3_i_ival(1'b1),.io_pads_qspi0_dq_3_o_oval(),.io_pads_qspi0_dq_3_o_oe(),
  .io_pads_aon_erst_n_i_ival(rst_n),
  .io_pads_dbgmode0_n_i_ival(1'b1),.io_pads_dbgmode1_n_i_ival(1'b1),.io_pads_dbgmode2_n_i_ival(1'b1),
  .io_pads_bootrom_n_i_ival(1'b0),.io_pads_aon_pmu_dwakeup_n_i_ival(1'b1),
  .io_pads_aon_pmu_padrst_o_oval(),.io_pads_aon_pmu_vddpaden_o_oval());

`define ITCM dut.u_e203_subsys_top.u_e203_subsys_main.u_e203_cpu_top.u_e203_srams.u_e203_itcm_ram.u_e203_itcm_gnrl_ram.u_storage
`define DTCM dut.u_e203_subsys_top.u_e203_subsys_main.u_e203_cpu_top.u_e203_srams.u_e203_dtcm_ram.u_e203_dtcm_gnrl_ram.u_storage
`define SHARED dut.u_shared

 localparam integer INPUT_MAX=8873,OUTPUT_COUNT=12689,WRITE_COUNT=12690;
 reg [63:0] firmware[0:8191];
 reg [31:0] expected[0:OUTPUT_COUNT-1],source_image[0:INPUT_MAX-1],shared_readback[0:131071];
 reg [1023:0] firmware_path,input_path,expected_path,output_dump_path;
 integer input_words,output_words,dump_requested=0,dump_fd,i;
 reg [16:0] shared_address=0; reg [12:0] itcm_address=0; reg [13:0] dtcm_address=0;
 reg [31:0] shared_din=0,readback_data=0; reg [63:0] itcm_din=0;
 reg shared_cs=0,itcm_cs=0,dtcm_cs=0,shared_we=1,shared_reset=0;
 wire loader_read=!shared_we;
 wire [31:0] loader_address={13'h1400,shared_address,2'b00};
 integer preload_commands=0,preload_responses=0;
 reg runtime_enabled=0,assessment_done=0;
 integer cycles=0,raw_cycles=0,full_start=-1,last_ack=-1,dma_writes=0,dma_write_acks=0,dma_reads=0;
 reg dma_fifo_is_write[0:15]; integer dma_wr_ptr=0,dma_rd_ptr=0;

 task attach_shared_loader;
  begin
   force `SHARED.clk=clk; force `SHARED.rst_n=shared_reset;
   force `SHARED.icb_cmd_valid=shared_cs; force `SHARED.icb_cmd_read=loader_read;
   force `SHARED.icb_cmd_addr=loader_address; force `SHARED.icb_cmd_wdata=shared_din;
   force `SHARED.icb_cmd_wmask=4'hf; force `SHARED.icb_rsp_ready=1'b1;
  end
 endtask
 task release_shared_loader;
  begin
   release `SHARED.icb_cmd_valid; release `SHARED.icb_cmd_read; release `SHARED.icb_cmd_addr;
   release `SHARED.icb_cmd_wdata; release `SHARED.icb_cmd_wmask; release `SHARED.icb_rsp_ready;
   release `SHARED.rst_n; release `SHARED.clk;
  end
 endtask
 task automatic preload_shared_word;
  integer guard; reg response_on_accept;
  begin
   @(posedge clk);guard=0;
   while(`SHARED.icb_cmd_ready!==1'b1)begin @(posedge clk);guard++;if(guard>1000)$fatal(1,"preload cmd stalled");end
   preload_commands++;
   response_on_accept=`SHARED.icb_rsp_valid===1'b1;
   if(response_on_accept)begin if(`SHARED.icb_rsp_err!==1'b0)$fatal(1,"preload err");preload_responses++;end
   @(negedge clk);shared_cs=0;itcm_cs=0;dtcm_cs=0;
   if(!response_on_accept)begin
    @(posedge clk);guard=0;
    while(`SHARED.icb_rsp_valid!==1'b1)begin @(posedge clk);guard++;if(guard>1000)$fatal(1,"preload rsp stalled");end
    if(`SHARED.icb_rsp_err!==1'b0)$fatal(1,"preload rsp err");
    preload_responses++;
   end
  end
 endtask
 task automatic read_shared_word(input [16:0] address,output [31:0] value);
  integer guard; reg response_on_accept;
  begin
   @(negedge clk);shared_cs=1;shared_address=address;
   @(posedge clk);guard=0;
   while(`SHARED.icb_cmd_ready!==1'b1)begin @(posedge clk);guard++;if(guard>1000)$fatal(1,"readback cmd stalled");end
   response_on_accept=`SHARED.icb_rsp_valid===1'b1;
   if(response_on_accept)begin if(`SHARED.icb_rsp_err!==1'b0)$fatal(1,"readback err");value=`SHARED.icb_rsp_rdata;end
   @(negedge clk);shared_cs=0;
   if(!response_on_accept)begin
    @(posedge clk);guard=0;
    while(`SHARED.icb_rsp_valid!==1'b1)begin @(posedge clk);guard++;if(guard>1000)$fatal(1,"readback rsp stalled");end
    if(`SHARED.icb_rsp_err!==1'b0)$fatal(1,"readback rsp err");
    value=`SHARED.icb_rsp_rdata;
   end
  end
 endtask

 initial begin
  if(!$value$plusargs("FIRMWARE=%s",firmware_path))$fatal(1,"missing FIRMWARE");
  if(!$value$plusargs("INPUT=%s",input_path))$fatal(1,"missing INPUT");
  if(!$value$plusargs("EXPECTED=%s",expected_path))$fatal(1,"missing EXPECTED");
  if(!$value$plusargs("INPUT_WORDS=%d",input_words))$fatal(1,"missing INPUT_WORDS");
  if(!$value$plusargs("OUTPUT_WORDS=%d",output_words))$fatal(1,"missing OUTPUT_WORDS");
  dump_requested=$value$plusargs("OUTPUT_DUMP=%s",output_dump_path);
  $readmemh(firmware_path,firmware);$readmemh(input_path,source_image,0,input_words-1);$readmemh(expected_path,expected);
  attach_shared_loader;
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
  $display("Q12_GLS_PRELOAD_DONE commands=%0d responses=%0d",preload_commands,preload_responses);
  repeat(8)@(negedge lfclk);cycles=0;runtime_enabled=1;rst_n=1;
 end

 // Sample on posedge clk (hfextclk), ~20 ps before qingyu_bus_clk rises, when all end-of-cycle
 // gate-level paths have settled and before any sequential element of the new cycle toggles.
 always @(posedge clk)begin
  if(runtime_enabled)raw_cycles=raw_cycles+1;
  if(runtime_enabled&&!assessment_done&&dut.u_e203_subsys_top.qingyu_bus_rst_n===1'b1)begin
   cycles=cycles+1;
   if(full_start<0&&dut.u_fio.icb_cmd_valid===1'b1&&dut.u_fio.icb_cmd_ready===1'b1&&
      dut.u_fio.icb_cmd_read===1'b0&&dut.u_fio.icb_cmd_addr===32'hf0000008)begin
    full_start=cycles;
    $display("Q12_GLS_FULL_START cycle=%0d time_ps=%0.0f",cycles,$realtime*1000.0);
   end
   if(dut.u_fio.dma_cmd_valid===1'b1&&dut.u_fio.dma_cmd_ready===1'b1)begin
    dma_fifo_is_write[dma_wr_ptr&15]=(dut.u_fio.dma_cmd_read===1'b0);
    dma_wr_ptr=dma_wr_ptr+1;
    if(dut.u_fio.dma_cmd_read===1'b0)dma_writes=dma_writes+1; else dma_reads=dma_reads+1;
   end
   if(dut.u_fio.dma_rsp_valid===1'b1&&dut.u_fio.dma_rsp_ready===1'b1)begin
    if(dma_fifo_is_write[dma_rd_ptr&15])begin
     dma_write_acks=dma_write_acks+1;
     if(dma_write_acks==WRITE_COUNT)begin
      last_ack=cycles;
      $display("Q12_GLS_FULL_END cycle=%0d time_ps=%0.0f full_window_cycles=%0d",cycles,$realtime*1000.0,last_ack-full_start+1);
     end
    end
    dma_rd_ptr=dma_rd_ptr+1;
   end
   if(host_valid===1'b1)begin
    if(host_code!==32'd1)$fatal(1,"GLS firmware failed host_code=%h",host_code);
    assessment_done=1;
   end
  end
  if(runtime_enabled&&!assessment_done&&(cycles>200000||raw_cycles>5000000))
   $fatal(1,"GLS timeout cycles=%0d raw_cycles=%0d gpio_presented=%0d dma_reads=%0d dma_writes=%0d",cycles,raw_cycles,gpio_presented,dma_reads,dma_writes);
 end

 integer mismatches=0;
 initial begin
  wait(assessment_done===1'b1);
  @(negedge clk);shared_cs=0;shared_we=0;
  attach_shared_loader;
  repeat(2)@(negedge clk);
  for(integer w=0;w<131072;w++)begin
   read_shared_word(17'(w),readback_data);
   shared_readback[w]=readback_data;
  end
  @(negedge clk);shared_cs=0;@(posedge clk);#1;release_shared_loader;
  for(i=0;i<OUTPUT_COUNT;i++)if(shared_readback[i]!==expected[i])begin
   if(mismatches<8)$display("GLS_MISMATCH idx=%0d got=%h exp=%h",i,shared_readback[i],expected[i]);
   mismatches++;
  end
  for(i=0;i<input_words;i++)if(shared_readback[65536+i]!==source_image[i])$fatal(1,"GLS source region corrupt idx=%0d",i);
  if(mismatches!=0)$fatal(1,"GLS output mismatches=%0d",mismatches);
  if(dump_requested)begin
   dump_fd=$fopen(output_dump_path,"w");
   for(i=0;i<OUTPUT_COUNT;i++)$fdisplay(dump_fd,"%08x",shared_readback[i]);
   $fclose(dump_fd);
  end
  $display("PASS Q12_GLS_COMPLETE full_window_cycles=%0d dma_reads=%0d dma_writes=%0d output_words=%0d mismatches=0",
           last_ack-full_start+1,dma_reads,dma_writes,OUTPUT_COUNT);
  $finish;
 end
endmodule
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--cand', type=Path, required=True)
    ap.add_argument('--sram-models', type=Path, default=Path('/storage1/admin_public_dir/SRAM_Lib_2025'))
    a = ap.parse_args()
    desk = Path.home() / 'Desktop'
    std_v = desk / 'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/verilog/scc40nll_vhsc40_rvt.v'
    std_db = desk / 'smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db'
    sram_dbs = [desk / 'qingyu_sram_corners' / ('%s_tt_1p10v_1p10v_25c.db' % m) for m in ['RAMSP128X16', 'RAMSP1024X16', 'RAMSP4096X16']]
    sram_vs = [a.sram_models / m / 'verilog' / (m + '.v') for m in ['RAMSP128X16', 'RAMSP1024X16', 'RAMSP4096X16']]
    netlist = (a.run / 'synth/mapped.v').resolve()
    sdc = (a.run / 'synth/mapped.sdc').resolve()
    wdir = (a.run / 'gls').resolve()
    wdir.mkdir(parents=True, exist_ok=True)
    rep = {'passed': False, 'phase': 'sdf'}
    save = lambda: (wdir / 'result.json').write_text(json.dumps(rep, indent=2) + '\n')
    save()
    try:
        sdf = wdir / 'mapped_tt.sdf'
        pt_tcl = wdir / 'write_sdf.tcl'
        pt_tcl.write_text('\n'.join([
            'set link_path [list * %s]' % ' '.join(str(p.resolve()) for p in [std_db] + sram_dbs),
            'read_verilog {%s}' % str(netlist),
            'current_design qingyu_e203_soc_top',
            'link_design qingyu_e203_soc_top',
            'read_sdc {%s}' % str(sdc),
            'update_timing',
            'write_sdf -version 3.0 -context verilog {%s}' % str(sdf),
            'exit',
        ]) + '\n')
        pt = shutil.which('pt_shell') or 'pt_shell'
        with (wdir / 'pt_sdf.log').open('w') as f:
            rc = subprocess.call([pt, '-f', str(pt_tcl)], cwd=str(wdir), stdout=f, stderr=subprocess.STDOUT)
        rep['sdf_bytes'] = sdf.stat().st_size if sdf.is_file() else 0
        if rc != 0 or rep['sdf_bytes'] < 100000:
            raise RuntimeError('PT write_sdf failed rc=%d' % rc)
        rep['phase'] = 'compile'; save()
        (wdir / 'tb_gls.sv').write_text(TB_GLS)
        vcs = shutil.which('vcs') or 'vcs'
        simv = wdir / 'simv_gls'
        cmd_comp = [vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '+define+ARM_UD_MODEL',
                    '-v', str(std_v.resolve()), *[str(x.resolve()) for x in sram_vs],
                    str(netlist), str(wdir / 'tb_gls.sv'),
                    '-sdf', 'typ:tb_gls.dut:' + str(sdf), '+neg_tchk', '+notimingcheck',
                    '+warn=noSDFCOM_UHICD,noSDFCOM_ANICD',
                    '-top', 'tb_gls', '-Mdir=' + str(wdir / 'csrc'), '-o', str(simv)]
        with (wdir / 'compile.log').open('w') as f:
            rc = subprocess.call(cmd_comp, cwd=str(wdir), stdout=f, stderr=subprocess.STDOUT)
        if rc != 0 or not simv.is_file():
            raise RuntimeError('VCS GLS compile failed rc=%d' % rc)
        rep['phase'] = 'simulate'; save()
        manifest = json.loads((a.cand / 'vendor/manifest.json').read_text())
        t0 = manifest['tasks'][0]
        case_src = a.cand / 'vendor/tasks' / t0['directory']
        for n in ['input.hex', 'expected.hex', 'dense.hex']:
            shutil.copy2(str(case_src / n), str(wdir / n))
        shutil.copy2(str(a.cand / 'vendor/firmware64.hex'), str(wdir / 'firmware64.hex'))
        cmd_run = [str(simv), '+FIRMWARE=firmware64.hex', '+INPUT=input.hex', '+EXPECTED=expected.hex',
                   '+OUTPUT_DUMP=observed_gls.hex', '+INPUT_WORDS=' + str(t0['input_words']), '+OUTPUT_WORDS=12690']
        with (wdir / 'sim_gls.log').open('w') as f:
            rc = subprocess.call(cmd_run, cwd=str(wdir), stdout=f, stderr=subprocess.STDOUT)
        sim_txt = (wdir / 'sim_gls.log').read_text(errors='replace')
        if sdf.is_file():
            sdf.unlink()
        if simv.is_file():
            simv.unlink()
        shutil.rmtree(str(wdir / 'csrc'), ignore_errors=True)
        shutil.rmtree(str(wdir / 'simv_gls.daidir'), ignore_errors=True)
        m = re.search(r'^PASS Q12_GLS_COMPLETE full_window_cycles=(\d+) dma_reads=(\d+) dma_writes=(\d+) output_words=(\d+) mismatches=0\b', sim_txt, re.M)
        sdf_done = 'Doing SDF annotation ...... Done' in sim_txt
        if rc != 0 or not m or not sdf_done or re.search(r'(?im)^\s*(?:Fatal:|Error:|Error-\[)|\$fatal', sim_txt):
            raise RuntimeError('GLS simulation did not pass cleanly; see sim_gls.log')
        rep.update(passed=True, phase='complete', sdf_annotated=sdf_done,
                   task=t0['task'], full_window_cycles=int(m.group(1)),
                   dma_reads=int(m.group(2)), dma_writes=int(m.group(3)),
                   output_words=int(m.group(4)), mismatches=0)
        save()
        print('Q12_GLS_OK cycles=%d sdf_bytes=%d' % (rep['full_window_cycles'], rep['sdf_bytes']), flush=True)
    except BaseException as e:
        for p in [wdir / 'mapped_tt.sdf', wdir / 'simv_gls']:
            if p.is_file(): p.unlink()
        shutil.rmtree(str(wdir / 'csrc'), ignore_errors=True)
        shutil.rmtree(str(wdir / 'simv_gls.daidir'), ignore_errors=True)
        rep.update(passed=False, error=repr(e)); save()
        print('Q12_GLS_FAILED ' + repr(e), flush=True)
        raise


if __name__ == '__main__':
    main()
