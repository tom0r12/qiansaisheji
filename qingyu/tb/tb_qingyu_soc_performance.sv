`timescale 1ns/1ps
// Reuse the independent full output checker and reset/boot harness.
module tb_qingyu_soc_performance;
 tb_qingyu_soc fixture();
`define MEM fixture.dut.u_shared
`ifdef QINGYU_DOUBLE_BUFFER
 `define DBACC fixture.dut.u_fio.u_accel
`ifdef QINGYU_READ_AHEAD
 integer prefetched=0, consumed=0, empty_wait=0;
`endif
 integer full_wait=0, cpu_wait=0;
 reg polling=0, poll_slot=0;
`endif
 integer ticks=0, start_tick=-1, live_tick=-1, load_end=-1, end_tick=-1;
 integer reads=0, writes=0, load_reads=0, load_writes=0, outputs=0;
 integer cmd_wait=0, rsp_wait=0, output_index;
 integer accel_busy_cycles=0, fio_cmd_wait=0, fio_rsp_wait=0;
 reg pending=0, pending_read=0;
 reg [31:0] pending_addr;
 reg [3:0] pending_mask;
 reg [25343:0] output_seen='0;
 reg active=0;
 reg [1023:0] activity_path;
 integer dump_enabled=0;
 initial begin
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
 always @(posedge fixture.dut.qingyu_bus_clk) begin
  ticks = ticks + 1;
  // Begin at request assertion (not acceptance), retaining initial bus waits.
`ifdef QINGYU_BLOCK_COPY
  if (start_tick < 0 && fixture.dut.u_fio.icb_cmd_valid &&
      !fixture.dut.u_fio.icb_cmd_read && fixture.dut.u_fio.icb_cmd_addr==32'hf0000038) begin
`else
  if (start_tick < 0 && `MEM.icb_cmd_valid && `MEM.icb_cmd_read &&
      `MEM.icb_cmd_addr == 32'ha0040000) begin
`endif
   start_tick=ticks; active=1;
   $display("QINGYU_PERF_START cycle=%0d time_ps=%0t",ticks,$realtime);
   if(dump_enabled) $dumpon;
  end
  if (active) begin
`ifdef QINGYU_DOUBLE_BUFFER
`ifdef QINGYU_READ_AHEAD
   if (`DBACC.issue_stream) prefetched++;
   if (`DBACC.consume_stream) consumed++;
   if (`DBACC.icb_cmd_valid && `DBACC.stream_wait) empty_wait++;
`endif
   if (`DBACC.producer_stall) full_wait++;
   if (`DBACC.command_fire && `DBACC.icb_cmd_read &&
       (`DBACC.icb_cmd_addr==16'h20 || `DBACC.icb_cmd_addr==16'h24)) begin
    poll_slot=`DBACC.icb_cmd_addr[2];
    polling=1;
   end
   if (polling && `DBACC.batch_ready[poll_slot]) polling=0;
   if (polling) cpu_wait++;
`endif
   if(fixture.dut.u_fio.u_accel.busy) accel_busy_cycles++;
   if(fixture.dut.u_fio.icb_cmd_valid && !fixture.dut.u_fio.icb_cmd_ready) fio_cmd_wait++;
   if(fixture.dut.u_fio.icb_rsp_valid && !fixture.dut.u_fio.icb_rsp_ready) fio_rsp_wait++;
   if (`MEM.icb_cmd_valid && !`MEM.icb_cmd_ready) cmd_wait++;
   if (`MEM.icb_rsp_valid && !`MEM.icb_rsp_ready) rsp_wait++;
   if(live_tick<0 && `MEM.icb_cmd_valid && `MEM.icb_cmd_read && live_data(`MEM.icb_cmd_addr))
    live_tick=ticks;
  end
  // Response bookkeeping precedes acceptance so back-to-back commands work.
  if (`MEM.icb_rsp_valid && `MEM.icb_rsp_ready) begin
   if(!pending) $fatal(1,"response without tracked request");
   if(`MEM.icb_rsp_err) $fatal(1,"shared SRAM response error");
   if(active && !pending_read && live_data(pending_addr)) begin
    load_writes++; load_end=ticks;
   end
   if(active && !pending_read && pending_addr >= 32'ha0010000 && pending_addr < 32'ha0028c00) begin
    output_index=(pending_addr-32'ha0010000)>>2;
    if(pending_mask!=4'hf || pending_addr[1:0]!=0 || output_seen[output_index])
     $fatal(1,"partial, unaligned or repeated output write");
    output_seen[output_index]=1'b1;
    outputs++;
    if(outputs==25344) begin
     end_tick=ticks;
     if(load_reads!=11936 || load_writes!=11936 || live_tick<load_end)
      $fatal(1,"incomplete task loading: reads=%0d writes=%0d",load_reads,load_writes);
     $display("QINGYU_PERF_WINDOW cycles=%0d load_cycles=%0d live_cycles=%0d reads=%0d writes=%0d load_words=%0d outputs=%0d cmd_wait=%0d rsp_wait=%0d start_cycle=%0d end_cycle=%0d start_to_live=%0d accel_busy_cycles=%0d fio_cmd_wait=%0d fio_rsp_wait=%0d",
      end_tick-start_tick,load_end-start_tick, end_tick-live_tick, reads,writes,load_writes,outputs,cmd_wait,rsp_wait,start_tick,end_tick,live_tick-start_tick,accel_busy_cycles,fio_cmd_wait,fio_rsp_wait);
`ifdef QINGYU_DOUBLE_BUFFER
`ifdef QINGYU_READ_AHEAD
     if(prefetched!=25344 || consumed!=25344) $fatal(1,"incorrect prefetch or dequeue count");
     $display("QINGYU_READ_AHEAD issued=%0d consumed=%0d empty_wait=%0d",prefetched,consumed,empty_wait);
`endif
     $display("QINGYU_BATCH_WAIT full_wait=%0d cpu_wait=%0d",full_wait,cpu_wait);
`endif
     $display("QINGYU_PERF_END time_ps=%0t",$realtime);
     active=0;
     if(dump_enabled) $dumpoff;
    end
   end
   pending=0;
  end
  if (`MEM.icb_cmd_valid && `MEM.icb_cmd_ready) begin
   if(pending) $fatal(1,"monitor requires at most one shared SRAM outstanding request");
   pending=1; pending_read=`MEM.icb_cmd_read; pending_addr=`MEM.icb_cmd_addr; pending_mask=`MEM.icb_cmd_wmask;
   if(active) begin
    if(pending_read) reads++; else writes++;
    if(pending_read && pending_addr>=32'ha0040000 && pending_addr<32'ha0050000) load_reads++;
   end
  end
 end
 always @(posedge fixture.clk) begin
  if(fixture.host_valid) begin
   if(end_tick<0 || outputs!=25344 || output_seen!={25344{1'b1}})
    $fatal(1,"missing complete performance window");
   $display("QINGYU_PERF_FIRMWARE outer_cycles=%0d driver_cycles=%0d compute_cycles=%0d",
    {`MEM.mem[49155],`MEM.mem[49154]}, {`MEM.mem[49153],`MEM.mem[49152]}, `MEM.mem[49156]);
  end
 end
`ifdef QINGYU_DOUBLE_BUFFER
`undef DBACC
`endif
`undef MEM
endmodule
