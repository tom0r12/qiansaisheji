`timescale 1ns/1ps
// opt5 performance monitor for the 5-port shared SRAM.  Same window and checks
// as the single-port opt4 monitor, applied to every port:
//  - window opens at the first staging command (0x38/0x84) or the W staging
//    start (0xb0), and closes when the last of the 25,344 INT16 outputs
//    (12,672 packed words) has been written back;
//  - every live input/W/bias/shift word must be written inside the window
//    before any port reads it, and each staging word is read exactly once;
//  - packed weight transfer: 16 commands, 8,192 live W reads, 8,192 W writes.
module tb_qingyu_soc_performance;
 tb_qingyu_soc fixture();
`define MEM fixture.dut.u_shared
`define FIO fixture.dut.u_fio
`define DBACC fixture.dut.u_fio.u_accel
 localparam integer NP=6;
 localparam integer OUT_WORDS=12672, OUT_PER_WORD=2;
 integer prefetched=0, consumed=0, empty_wait=0, full_wait=0, cpu_wait=0;
 reg polling=0, poll_slot=0;
 integer state_count[0:15]; integer phase_count[0:7];
 integer snap_blocked=0, full_overlap_mac=0, wb_active=0, wb_launch=0;
 integer wb_no_request=0, wb_bus_wait=0, wb_prefetch_wait=0, ready_no_wb=0;
 integer idle_after_start=0, start_wait_weights=0;
 initial begin for(integer j=0;j<16;j++)state_count[j]=0; for(integer j=0;j<8;j++)phase_count[j]=0; end
 integer ticks=0, start_tick=-1, live_tick=-1, load_end=-1, end_tick=-1;
 integer reads=0, writes=0, load_reads=0, load_writes=0, outputs=0;
 integer cmd_wait=0, output_index, accel_busy_cycles=0, fio_cmd_wait=0, fio_rsp_wait=0;
 integer weight_commands=0, weight_reads=0, weight_writes=0;
 integer port_acc [0:NP-1];
 integer first_busy=-1, last_busy=-1, idle_cycles=0, st_end=-1, st_started=0;
 reg pending [0:NP-1];
 reg pending_read [0:NP-1];
 reg [31:0] pending_addr [0:NP-1];
 reg [3:0] pending_mask [0:NP-1];
 reg [25343:0] output_seen='0;
 reg [11935:0] live_written='0;
 reg active=0;
 integer p, live_index, any_fire;
 reg [31:0] a;
 reg [1023:0] activity_path;
 integer dump_enabled=0;
 initial begin
  for (p=0;p<NP;p=p+1) begin pending[p]=0; port_acc[p]=0; end
  if ($value$plusargs("ACTIVITY=%s",activity_path)) begin
   dump_enabled=1;
   $dumpfile(activity_path);
   $dumpvars(0,fixture.dut);
   $dumpoff;
  end
 end
 function automatic bit live_data(input reg [31:0] addr);
  live_data = (addr >= 32'ha0000000 && addr < 32'ha0003180) ||
              (addr >= 32'ha0004000 && addr < 32'ha000c900);
 endfunction
 function automatic integer live_slot(input reg [31:0] addr);
  live_slot = addr < 32'ha0003180 ? (addr-32'ha0000000)>>2 : 3168 + ((addr-32'ha0004000)>>2);
 endfunction
 always @(posedge fixture.dut.qingyu_bus_clk) begin
  ticks = ticks + 1;
  if (start_tick < 0 && `FIO.icb_cmd_valid && !`FIO.icb_cmd_read &&
      (`FIO.icb_cmd_addr==32'hf0000038 || `FIO.icb_cmd_addr==32'hf0000084 ||
       `FIO.icb_cmd_addr==32'hf00000b0 || `FIO.icb_cmd_addr==32'hf00000b4 ||
       `FIO.icb_cmd_addr==32'hf00000bc || `FIO.icb_cmd_addr==32'hf00000c8)) begin
   start_tick=ticks; active=1;
   $display("QINGYU_PERF_START cycle=%0d time_ps=%0t",ticks,$realtime);
   if(dump_enabled) $dumpon;
  end
  if (active) begin
   state_count[`DBACC.engine_state]++;
   phase_count[`FIO.phase]++;
   if (`DBACC.engine_state==8 && !`DBACC.snap_go) snap_blocked++;
   if (`DBACC.producer_stall && (`DBACC.engine_state==5 || `DBACC.engine_state==7)) full_overlap_mac++;
   if (`FIO.aw_active) begin
    wb_active++;
    if (!`FIO.mem_cmd_valid) wb_no_request++;
    if (`FIO.mem_cmd_valid && !`FIO.mem_cmd_ready) wb_bus_wait++;
    if (`FIO.phase==4 && `FIO.blk_rsp && !`FIO.block_next_valid) wb_prefetch_wait++;
   end
   if (`FIO.aw_go) wb_launch++;
   if (`FIO.block_has_row && !`FIO.aw_active) ready_no_wb++;
   if (first_busy>=0 && !`DBACC.busy) idle_after_start++;

   if (`DBACC.issue_stream) prefetched++;
   if (`DBACC.consume_stream) consumed++;
   if (`DBACC.icb_cmd_valid && `DBACC.stream_wait) empty_wait++;
   if (`DBACC.producer_stall) full_wait++;
   if (`DBACC.command_fire && `DBACC.icb_cmd_read &&
       (`DBACC.icb_cmd_addr==16'h20 || `DBACC.icb_cmd_addr==16'h24)) begin
    poll_slot=`DBACC.icb_cmd_addr[2]; polling=1;
   end
   if (polling && `DBACC.batch_ready[poll_slot]) polling=0;
   if (polling) cpu_wait++;
   if (`DBACC.busy) begin
    accel_busy_cycles++; last_busy=ticks;
    if (first_busy<0) first_busy=ticks;
   end
   if (`FIO.icb_cmd_valid && !`FIO.icb_cmd_ready) fio_cmd_wait++;
   if (`FIO.icb_rsp_valid && !`FIO.icb_rsp_ready) fio_rsp_wait++;
   if (`FIO.st_busy) st_started=1;
   if (st_started && st_end<0 && !`FIO.st_busy) st_end=ticks;
   if (`FIO.take_block && `FIO.weight_cmd && `FIO.icb_cmd_ready) weight_commands++;
   if (`FIO.weight_write) weight_writes++;
  end
  // responses first, so back-to-back commands on one port work
  for (p=0;p<NP;p=p+1) if (`MEM.rsp_valid[p] && `MEM.rsp_ready[p]) begin
   if(!pending[p]) $fatal(1,"port %0d: response without tracked request",p);
   if(`MEM.rsp_err[p]) $fatal(1,"port %0d: shared SRAM response error addr=%h",p,pending_addr[p]);
   if(active && !pending_read[p] && pending_addr[p] >= 32'ha0010000 && pending_addr[p] < 32'ha0010000+4*OUT_WORDS) begin
    output_index=(pending_addr[p]-32'ha0010000)>>2;
    if(pending_mask[p]!=4'hf || pending_addr[p][1:0]!=0 || output_seen[output_index])
     $fatal(1,"partial, unaligned or repeated output write");
    output_seen[output_index]=1'b1;
    outputs+=OUT_PER_WORD;
    if(outputs==25344) begin
     end_tick=ticks;
     if(load_reads!=11936 || load_writes!=11936 || !(&live_written))
      $fatal(1,"incomplete task loading: reads=%0d writes=%0d",load_reads,load_writes);
     if (weight_commands!=16 || weight_reads!=8192 || weight_writes!=8192)
      $fatal(1,"incomplete packed weight transfer commands=%0d reads=%0d writes=%0d",
             weight_commands,weight_reads,weight_writes);
     if(prefetched!=OUT_WORDS || consumed!=OUT_WORDS) $fatal(1,"incorrect prefetch or dequeue count");
     $display("QINGYU_WEIGHT_TRANSFER commands=%0d reads=%0d writes=%0d",weight_commands,weight_reads,weight_writes);
     $display("QINGYU_PERF_WINDOW cycles=%0d load_cycles=%0d live_cycles=%0d reads=%0d writes=%0d load_words=%0d outputs=%0d cmd_wait=%0d rsp_wait=0 start_cycle=%0d end_cycle=%0d start_to_live=%0d accel_busy_cycles=%0d fio_cmd_wait=%0d fio_rsp_wait=%0d",
      end_tick-start_tick,load_end-start_tick,end_tick-live_tick,reads,writes,load_writes,outputs,cmd_wait,
      start_tick,end_tick,live_tick-start_tick,accel_busy_cycles,fio_cmd_wait,fio_rsp_wait);
     $display("QINGYU_READ_AHEAD issued=%0d consumed=%0d empty_wait=%0d",prefetched,consumed,empty_wait);
     $display("QINGYU_BATCH_WAIT full_wait=%0d cpu_wait=%0d",full_wait,cpu_wait);
     $display("QINGYU_PROFILE first_start=%0d last_busy=%0d tail=%0d idle_all_ports=%0d st_end=%0d port_cw=%0d port_sw=%0d port_mem=%0d port_ld=%0d port_in=%0d port_sr=%0d",
      first_busy-start_tick,last_busy-start_tick,end_tick-last_busy,idle_cycles,
      st_end<0 ? -1 : st_end-start_tick,port_acc[0],port_acc[1],port_acc[2],port_acc[3],port_acc[4],port_acc[5]);
     for(integer j=0;j<16;j++) $display("PROFILE_STATE id=%0d cycles=%0d",j,state_count[j]);
     for(integer j=0;j<8;j++) $display("PROFILE_PHASE id=%0d cycles=%0d",j,phase_count[j]);
     $display("PROFILE_DETAIL snap_blocked=%0d full_overlap_mac=%0d wb_active=%0d wb_launch=%0d wb_no_request=%0d wb_bus_wait=%0d wb_prefetch_wait=%0d ready_no_wb=%0d idle_after_start=%0d",snap_blocked,full_overlap_mac,wb_active,wb_launch,wb_no_request,wb_bus_wait,wb_prefetch_wait,ready_no_wb,idle_after_start);
     $display("QINGYU_PERF_END time_ps=%0t",$realtime);
     active=0;
     if(dump_enabled) $dumpoff;
    end
   end
   pending[p]=0;
  end
  // read checks before this cycle's write marks (same-bank accesses never coincide)
  any_fire=0;
  for (p=0;p<NP;p=p+1) begin
   a = `MEM.cmd_addr[32*p+:32];
   if (`MEM.cmd_valid[p] && !`MEM.cmd_ready[p] && active) cmd_wait++;
   if (`MEM.cmd_valid[p] && `MEM.cmd_ready[p]) begin
    any_fire=1;
    if(pending[p]) $fatal(1,"port %0d: second outstanding request",p);
    pending[p]=1; pending_read[p]=`MEM.cmd_read[p]; pending_addr[p]=a; pending_mask[p]=`MEM.cmd_wmask[4*p+:4];
    if(active) begin
     port_acc[p]++;
     if(`MEM.cmd_read[p]) reads++; else writes++;
     if(`MEM.cmd_read[p] && a>=32'ha0040000 && a<32'ha0050000) load_reads++;
     if(`MEM.cmd_read[p] && a>=32'ha0004000 && a<32'ha000c000) weight_reads++;
     if(`MEM.cmd_read[p] && live_data(a)) begin
      if(live_tick<0) live_tick=ticks;
      if(!live_written[live_slot(a)]) $fatal(1,"live read before load: port=%0d addr=%h",p,a);
     end
    end
   end
  end
  for (p=0;p<NP;p=p+1) begin
   a = `MEM.cmd_addr[32*p+:32];
   if (active && `MEM.cmd_valid[p] && `MEM.cmd_ready[p] && !`MEM.cmd_read[p] && live_data(a)) begin
    if(live_written[live_slot(a)]) $fatal(1,"live word loaded twice: addr=%h",a);
    live_written[live_slot(a)]=1'b1; load_writes++; load_end=ticks;
   end
  end
  if (active && !any_fire) idle_cycles++;
 end
 always @(posedge fixture.clk) begin
  if(fixture.host_valid) begin
   if(end_tick<0 || outputs!=25344 || !(&output_seen[OUT_WORDS-1:0]))
    $fatal(1,"missing complete performance window");
   $display("QINGYU_PERF_FIRMWARE outer_cycles=%0d driver_cycles=%0d compute_cycles=%0d",
    {`MEM.mem[49155],`MEM.mem[49154]}, {`MEM.mem[49153],`MEM.mem[49152]}, `MEM.mem[49156]);
  end
 end
`undef DBACC
`undef FIO
`undef MEM
endmodule
