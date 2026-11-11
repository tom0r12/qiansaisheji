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
 // Output write-back (block copy) occupancy counters.
 integer copy_cycles=0, pop_copy=0, wr_cmd_cycles=0, wr_rsp_cycles=0, rsp_wait_copy=0;
 integer chain_ok=0, starve_data=0, batches=0, issue_copy=0, fifo_sum_copy=0;
 integer fifo_hist0=0, fifo_hist1=0, fifo_hist2=0, fifo_hist3=0, fifo_hist4=0, fifo_histN=0;
 integer gap_total=0, dur_total=0, last_copy_end=-1, batch_start_tick=-1;
 integer first_word_wait=0, block_pop_valid0=0;
 integer weight_commands=0, weight_reads=0, weight_writes=0;
 integer out_copy_cycles=0, out_batches=0, ob_start=-1, out_batch_dur=0;
 integer tile_busy_start=-1, tile_pops=0, prev_fall=-1, last_pop=-1, busy_prev=0;
 integer idle_total=0, idle_max=0, idle_events=0;
 integer status_reads=0, accel_cmds=0, gap_n=0, trace_cmds=0;
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
      !fixture.dut.u_fio.icb_cmd_read &&
      (fixture.dut.u_fio.icb_cmd_addr==32'hf0000038 || fixture.dut.u_fio.icb_cmd_addr==32'hf0000084)) begin
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
   // --- output copy engine ---
   if (fixture.dut.u_fio.pending && fixture.dut.u_fio.owner_block) begin
    copy_cycles++;
    if (fixture.dut.u_fio.batch_block) out_copy_cycles++;
    if (fixture.dut.u_fio.phase==3) wr_cmd_cycles++;
    if (fixture.dut.u_fio.phase==4) begin
     wr_rsp_cycles++;
     if (!fixture.dut.u_fio.blk_rsp) rsp_wait_copy++;
    end
    if (fixture.dut.u_fio.phase==3 && !fixture.dut.u_fio.block_valid) first_word_wait++;
    fifo_sum_copy += fixture.dut.u_fio.u_accel.fifo_count;
    case (fixture.dut.u_fio.u_accel.fifo_count)
      0: fifo_hist0++;
      1: fifo_hist1++;
      2: fifo_hist2++;
      3: fifo_hist3++;
      4: fifo_hist4++;
      default: fifo_histN++;
    endcase
    if (fixture.dut.u_fio.u_accel.issue_stream) issue_copy++;
   end
   if (fixture.dut.u_fio.block_pop) begin
    pop_copy++; tile_pops++; last_pop=ticks;
   end
   if (fixture.dut.u_fio.block_pop && fixture.dut.u_fio.u_accel.block_valid!==1'b1) block_pop_valid0++;
   if (fixture.dut.u_fio.output_write_next) chain_ok++;
   if (fixture.dut.u_fio.phase==4 && fixture.dut.u_fio.blk_rsp &&
       fixture.dut.u_fio.word_number!=fixture.dut.u_fio.transfer_words-1 &&
       !fixture.dut.u_fio.block_next_valid) starve_data++;
   if (fixture.dut.u_fio.take_block && fixture.dut.u_fio.batch_cmd) begin
    out_batches++; ob_start = ticks;
   end
   if (fixture.dut.u_fio.phase==4 && fixture.dut.u_fio.blk_rsp &&
       fixture.dut.u_fio.word_number==fixture.dut.u_fio.transfer_words-1 &&
       fixture.dut.u_fio.batch_block) out_batch_dur += ticks-ob_start+1;
   if (fixture.dut.u_fio.take_block && fixture.dut.u_fio.block_cmd && !fixture.dut.u_fio.weight_cmd) begin
    batches++;
    if (last_copy_end>=0) gap_total += ticks-last_copy_end;
    batch_start_tick = ticks;
   end
   if (fixture.dut.u_fio.phase==4 && fixture.dut.u_fio.blk_rsp &&
       fixture.dut.u_fio.word_number==fixture.dut.u_fio.transfer_words-1) begin
    last_copy_end = ticks;
    if (batch_start_tick>=0) dur_total += ticks-batch_start_tick+1;
   end
   if (fixture.dut.u_fio.u_accel.busy != busy_prev) begin
    busy_prev = fixture.dut.u_fio.u_accel.busy;
    if (busy_prev) begin
     if (prev_fall>=0) begin idle_events++; idle_total += ticks-prev_fall;
      if (ticks-prev_fall>idle_max) idle_max=ticks-prev_fall; end
     $display("QINGYU_TL tick=%0d ACC_ON tile=%0d gap=%0d", ticks,
      fixture.dut.u_fio.u_accel.tile_col_base, prev_fall<0 ? -1 : ticks-prev_fall);
     tile_busy_start=ticks; tile_pops=0;
    end else begin
     $display("QINGYU_TL tick=%0d ACC_OFF busy_dur=%0d pops=%0d last_pop_ago=%0d",
      ticks, tile_busy_start<0 ? -1 : ticks-tile_busy_start, tile_pops, ticks-last_pop);
     prev_fall=ticks; gap_n=gap_n+1;
    end
   end
   // Diagnostic command trace: the input copy / tile-0 programming window and
   // the first two inter-tile gaps.
   if (fixture.dut.u_fio.icb_cmd_valid && fixture.dut.u_fio.icb_cmd_ready && trace_cmds<600 &&
       ((live_tick>0 && ticks-live_tick<14000) ||
        (gap_n<=2 && prev_fall>0 && ticks-prev_fall<1000))) begin
    trace_cmds=trace_cmds+1;
    $display("QINGYU_CMD tick=%0d rw=%0d addr=%h wd=%h blk=%0d wl=%0d ph=%0d",
     ticks, fixture.dut.u_fio.icb_cmd_read, fixture.dut.u_fio.icb_cmd_addr,
     fixture.dut.u_fio.icb_cmd_wdata, fixture.dut.u_fio.block_cmd,
     fixture.dut.u_fio.wl_busy, fixture.dut.u_fio.phase);
   end
   if (fixture.dut.u_fio.icb_cmd_valid && fixture.dut.u_fio.icb_cmd_ready &&
       fixture.dut.u_fio.icb_cmd_addr==32'hf0000008) status_reads++;
   if (fixture.dut.u_fio.icb_cmd_valid && fixture.dut.u_fio.icb_cmd_ready &&
       fixture.dut.u_fio.icb_cmd_addr[31:16]==16'hf000 && !fixture.dut.u_fio.block_cmd)
    accel_cmds++;
   // --- end ---
   if (fixture.dut.u_fio.take_block && fixture.dut.u_fio.weight_cmd) weight_commands++;
   if (`MEM.icb_cmd_valid && `MEM.icb_cmd_ready && `MEM.icb_cmd_read &&
       `MEM.icb_cmd_addr >= 32'ha0004000 && `MEM.icb_cmd_addr < 32'ha000c000) weight_reads++;
   if (fixture.dut.u_fio.weight_write) weight_writes++;
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
     if (weight_commands!=16 || weight_reads!=8192 || weight_writes!=8192)
      $fatal(1,"incomplete packed weight transfer commands=%0d reads=%0d writes=%0d",
             weight_commands,weight_reads,weight_writes);
     $display("QINGYU_WEIGHT_TRANSFER commands=%0d reads=%0d writes=%0d",
              weight_commands,weight_reads,weight_writes);
     $display("QINGYU_PERF_WINDOW cycles=%0d load_cycles=%0d live_cycles=%0d reads=%0d writes=%0d load_words=%0d outputs=%0d cmd_wait=%0d rsp_wait=%0d start_cycle=%0d end_cycle=%0d start_to_live=%0d accel_busy_cycles=%0d fio_cmd_wait=%0d fio_rsp_wait=%0d",
      end_tick-start_tick,load_end-start_tick, end_tick-live_tick, reads,writes,load_writes,outputs,cmd_wait,rsp_wait,start_tick,end_tick,live_tick-start_tick,accel_busy_cycles,fio_cmd_wait,fio_rsp_wait);
`ifdef QINGYU_DOUBLE_BUFFER
`ifdef QINGYU_READ_AHEAD
     if(prefetched!=25344 || consumed!=25344) $fatal(1,"incorrect prefetch or dequeue count");
     $display("QINGYU_READ_AHEAD issued=%0d consumed=%0d empty_wait=%0d",prefetched,consumed,empty_wait);
`endif
     $display("QINGYU_BATCH_WAIT full_wait=%0d cpu_wait=%0d",full_wait,cpu_wait);
     $display("QINGYU_COPY copy_cycles=%0d pops=%0d batches=%0d wr_cmd=%0d wr_rsp=%0d rsp_wait=%0d chain=%0d starve=%0d issue_copy=%0d first_word_wait=%0d pop_no_valid=%0d",
      copy_cycles,pop_copy,batches,wr_cmd_cycles,wr_rsp_cycles,rsp_wait_copy,chain_ok,starve_data,issue_copy,first_word_wait,block_pop_valid0);
     $display("QINGYU_COPY fifo_sum=%0d hist0=%0d hist1=%0d hist2=%0d hist3=%0d hist4=%0d histN=%0d gap_total=%0d dur_total=%0d",
      fifo_sum_copy,fifo_hist0,fifo_hist1,fifo_hist2,fifo_hist3,fifo_hist4,fifo_histN,gap_total,dur_total);
     $display("QINGYU_OUT out_copy=%0d out_batches=%0d out_dur=%0d idle_total=%0d idle_max=%0d idle_n=%0d status_reads=%0d accel_cmds=%0d",
      out_copy_cycles,out_batches,out_batch_dur,idle_total,idle_max,idle_events,status_reads,accel_cmds);
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
