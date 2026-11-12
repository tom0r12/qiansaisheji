`timescale 1ns/1ps
// Passive performance instrumentation. The frozen independent route/data
// checker remains instantiated; this module never drives DUT inputs.
// Detailed MAC accounting is deliberately limited to the current four-row RTL.
module tb_qingyu_bus_profile;
 tb_qingyu_bus_queue_performance checked();
`define DUT checked.fixture.dut
`define FIO `DUT.u_fio
`define ACC `FIO.u_accel
`define DMA `DUT.u_dma_merge
`define MAIN `DUT.u_e203_subsys_top.u_e203_subsys_main
`define MERGE `MAIN.u_mem_merge
`define FAB `MAIN.u_e203_subsys_mems
`define MEM `DUT.u_shared
 integer tick=0,start_tick=-1,end_tick=-1,stage_tick=-1,first_busy=-1,last_busy=-1;
 integer phase_cycles[0:3],phase_reads[0:3],phase_writes[0:3],phase_idle[0:3];
 integer ncmd[0:5],nrsp[0:5],nread[0:5],nwrite[0:5],wait_cmd[0:5],wait_rsp[0:5];
 integer latency_sum[0:5],latency_max[0:5],offered_tick[0:5],accepted_tick[0:5];
 integer offer_delay_sum[0:5],pending_cycles[0:5],response_to_next_cmd_sum[0:5],last_rsp[0:5];
 reg pending[0:5],is_output[0:5];
 integer csr_cmd[0:63],csr_reads[0:63],csr_wait[0:63];
 integer output_gap[0:31],last_output_cmd=-1,output_commands=0,output_responses=0;
 integer output_credit_blocked=0,output_descriptor_idle_ready=0,output_no_data=0;
 integer output_latency_sum=0,output_latency_max=0,output_cmd_wait=0,output_cmd_with_rsp=0;
 integer tile_first_busy[0:15],tile_last_busy[0:15],tile_busy[0:15];
 integer tile_first_output[0:15],tile_last_output_rsp[0:15],tile_wfirst[0:15],tile_wlast[0:15];
 integer tile_output_accept[0:15],tile_output_rsp[0:15],pending_output_tile[0:5];
 integer active_tile=-1,writes_w=0,private_x=0;
 integer engine_state_cycles[0:15],mac_product_cycles=0,scalar_macs=0,producer_stall_cycles=0;
 integer source_staging_cmds=0,live_cmds=0,output_shared_cmds=0;
 integer fabric_accepts=0,fabric_responses=0,fabric_inflight=0,fabric_max_inflight=0;
 integer fabric_backpressure=0,fabric_no_offer=0,sram_idle_outstanding=0,sram_idle_empty=0;
 integer fabric_gaps[0:31],sram_gaps[0:31],last_fabric_accept=-1,last_sram_accept=-1;
 integer busy_overlap_rw=0,cpu_control_cycles=0,cpu_control_wait_cycles=0;
 integer p,idx,ph,delta,tile,rows;
 reg was_busy=0,window_active,output_active,final_response;
 function automatic bit source_addr(input [31:0] a);
  source_addr=(a>=32'ha0040000&&a<32'ha0043180)||(a>=32'ha0044000&&a<32'ha004c900);
 endfunction
 function automatic bit output_addr(input [31:0] a);
  output_addr=a>=32'ha0010000&&a<32'ha001c600;
 endfunction
 initial begin
  for(p=0;p<6;p=p+1)begin
   ncmd[p]=0;nrsp[p]=0;nread[p]=0;nwrite[p]=0;wait_cmd[p]=0;wait_rsp[p]=0;
   latency_sum[p]=0;latency_max[p]=0;offered_tick[p]=-1;accepted_tick[p]=-1;
   offer_delay_sum[p]=0;pending_cycles[p]=0;response_to_next_cmd_sum[p]=0;last_rsp[p]=-1;
   pending[p]=0;is_output[p]=0;pending_output_tile[p]=-1;
  end
  for(p=0;p<4;p=p+1)begin phase_cycles[p]=0;phase_reads[p]=0;phase_writes[p]=0;phase_idle[p]=0;end
  for(p=0;p<64;p=p+1)begin csr_cmd[p]=0;csr_reads[p]=0;csr_wait[p]=0;end
  for(p=0;p<32;p=p+1)begin output_gap[p]=0;fabric_gaps[p]=0;sram_gaps[p]=0;end
  for(p=0;p<16;p=p+1)begin
   tile_first_busy[p]=-1;tile_last_busy[p]=-1;tile_busy[p]=0;tile_first_output[p]=-1;
   tile_last_output_rsp[p]=-1;tile_wfirst[p]=-1;tile_wlast[p]=-1;
   tile_output_accept[p]=0;tile_output_rsp[p]=0;engine_state_cycles[p]=0;
  end
 end
 always @(posedge `DUT.qingyu_bus_clk)begin
  tick++;
  if(`DUT.qingyu_bus_rst_n)begin
   if(start_tick<0)for(p=0;p<2;p=p+1)
    if(`MERGE.s_cmd_valid[p]&&`MERGE.s_cmd_read[p]&&source_addr(`MERGE.s_cmd_addr[32*p+:32]))start_tick=tick;
   final_response=pending[2]&&is_output[2]&&`DMA.s_rsp_valid[2]&&`DMA.s_rsp_ready[2]&&output_responses==12671;
   if(final_response)end_tick=tick;
   window_active=start_tick>=0&&end_tick<0;
   if(window_active)begin
    if(stage_tick<0&&`FIO.icb_cmd_valid&&!`FIO.icb_cmd_read&&`FIO.icb_cmd_addr==32'hf0000084)stage_tick=tick;
    if(`ACC.busy&&!was_busy)begin active_tile++;if(active_tile>15)$fatal(1,"too many compute tiles");tile_first_busy[active_tile]=tick;end
    if(`ACC.busy)begin
     if(first_busy<0)first_busy=tick;
     last_busy=tick;tile_last_busy[active_tile]=tick;tile_busy[active_tile]++;
     engine_state_cycles[`ACC.engine_state]++;
     if(`ACC.producer_stall)producer_stall_cycles++;
     if(`ACC.product_valid&&(`ACC.engine_state==`ACC.E_MAC_CAP||`ACC.engine_state==`ACC.E_DRAIN))begin
      mac_product_cycles++;rows=99-`ACC.row_index;if(rows>4)rows=4;
      scalar_macs=scalar_macs+rows*16;
     end
    end
    was_busy=`ACC.busy;
    ph=stage_tick<0 ? 0 : first_busy<0 ? 1 : `ACC.busy ? 2 : 3;
    phase_cycles[ph]++;
    if(`ACC.input_write)private_x++;
    if(`ACC.weight_write)begin
     tile=writes_w/512;if(tile_wfirst[tile]<0)tile_wfirst[tile]=tick;
     tile_wlast[tile]=tick;writes_w++;
    end
    if(`FIO.icb_cmd_valid)begin
     cpu_control_cycles++;
     if(!`FIO.icb_cmd_ready)cpu_control_wait_cycles++;
     if(`FIO.icb_cmd_addr[31:8]==24'hf00000)begin
      idx=`FIO.icb_cmd_addr[7:2];
      if(!`FIO.icb_cmd_ready)csr_wait[idx]++;
      else begin csr_cmd[idx]++;if(`FIO.icb_cmd_read)csr_reads[idx]++;end
     end
    end
    if(`FAB.mem_icb_cmd_valid&&!`FAB.mem_icb_cmd_ready)fabric_backpressure++;
    if(!`FAB.mem_icb_cmd_valid)fabric_no_offer++;
    if(`FAB.mem_icb_cmd_valid&&`FAB.mem_icb_cmd_ready)begin
     fabric_accepts++;
     if(last_fabric_accept>=0)begin delta=tick-last_fabric_accept;if(delta>31)delta=31;fabric_gaps[delta]++;end
     last_fabric_accept=tick;
    end
    if(`MEM.icb_cmd_valid&&`MEM.icb_cmd_ready)begin
     if(`MEM.icb_cmd_read)phase_reads[ph]++;else phase_writes[ph]++;
     if(`ACC.busy)busy_overlap_rw++;
     if(source_addr(`MEM.icb_cmd_addr))source_staging_cmds++;
     else if(output_addr(`MEM.icb_cmd_addr))output_shared_cmds++;
     else live_cmds++;
     if(last_sram_accept>=0)begin delta=tick-last_sram_accept;if(delta>31)delta=31;sram_gaps[delta]++;end
     last_sram_accept=tick;
    end else begin
     phase_idle[ph]++;
     if(fabric_inflight!=0)sram_idle_outstanding++;else sram_idle_empty++;
    end
    output_active=!`FIO.load_block&&(`FIO.phase==`FIO.WRITE_CMD||`FIO.phase==`FIO.WRITE_RSP);
    if(pending[2]&&is_output[2]&&!(`DMA.s_rsp_valid[2]&&`DMA.s_rsp_ready[2])&&`FIO.block_next_valid)output_credit_blocked++;
    if(`FIO.block_valid&&!output_active&&first_busy>=0)output_descriptor_idle_ready++;
    if(output_active&&!pending[2]&&!`FIO.block_valid)output_no_data++;
    if(`DMA.s_cmd_valid[2]&&!`DMA.s_cmd_ready[2]&&!`DMA.s_cmd_read[2]&&output_addr(`DMA.s_cmd_addr[64+:32]))output_cmd_wait++;
    for(p=0;p<6;p=p+1)begin
     if(pending[p])pending_cycles[p]++;
     if(`DMA.s_cmd_valid[p]&&offered_tick[p]<0)offered_tick[p]=tick;
     if(`DMA.s_cmd_valid[p]&&!`DMA.s_cmd_ready[p])wait_cmd[p]++;
     if(`DMA.s_rsp_valid[p]&&!`DMA.s_rsp_ready[p])wait_rsp[p]++;
    end
   end
   // Include final response in transaction accounting, but not the half-open
   // [first request, final ACK) elapsed-cycle partition above.
   if(start_tick>=0&&(window_active||final_response))begin
    if(`FAB.mem_icb_rsp_valid&&`FAB.mem_icb_rsp_ready)begin fabric_responses++;fabric_inflight--;end
    if(`FAB.mem_icb_cmd_valid&&`FAB.mem_icb_cmd_ready)fabric_inflight++;
    if(fabric_inflight>fabric_max_inflight)fabric_max_inflight=fabric_inflight;
    for(p=0;p<6;p=p+1)begin
     if(`DMA.s_rsp_valid[p]&&`DMA.s_rsp_ready[p])begin
      if(!pending[p])$fatal(1,"profile response without pending owner");
      delta=tick-accepted_tick[p];latency_sum[p]+=delta;if(delta>latency_max[p])latency_max[p]=delta;
      nrsp[p]++;last_rsp[p]=tick;
      if(is_output[p])begin
       output_responses++;output_latency_sum+=delta;if(delta>output_latency_max)output_latency_max=delta;
       tile=pending_output_tile[p];tile_output_rsp[tile]++;tile_last_output_rsp[tile]=tick;
      end
      pending[p]=0;
     end
     if(window_active&&`DMA.s_cmd_valid[p]&&`DMA.s_cmd_ready[p])begin
      if(pending[p])$fatal(1,"profile assumes one pending request per DMA source");
      ncmd[p]++;if(`DMA.s_cmd_read[p])nread[p]++;else nwrite[p]++;
      if(offered_tick[p]>=0)offer_delay_sum[p]+=tick-offered_tick[p];offered_tick[p]=-1;
      if(last_rsp[p]>=0)response_to_next_cmd_sum[p]+=tick-last_rsp[p];
      accepted_tick[p]=tick;pending[p]=1;
      is_output[p]=!`DMA.s_cmd_read[p]&&output_addr(`DMA.s_cmd_addr[32*p+:32]);
      if(is_output[p])begin
       output_commands++;tile=((`DMA.s_cmd_addr[32*p+:32]-32'ha0010000)>>2)%128/8;
       pending_output_tile[p]=tile;tile_output_accept[tile]++;if(tile_first_output[tile]<0)tile_first_output[tile]=tick;
       if(`DMA.s_rsp_valid[p]&&`DMA.s_rsp_ready[p])output_cmd_with_rsp++;
       if(last_output_cmd>=0)begin delta=tick-last_output_cmd;if(delta>31)delta=31;output_gap[delta]++;end
       last_output_cmd=tick;
      end
     end
    end
   end
  end
 end
 always @(posedge checked.fixture.clk)if(checked.fixture.host_valid)begin
  if(end_tick-start_tick!=phase_cycles[0]+phase_cycles[1]+phase_cycles[2]+phase_cycles[3])$fatal(1,"profile cycle partition mismatch");
  if(scalar_macs!=99*64*256||mac_product_cycles!=25*64*16)$fatal(1,"unexpected four-row MAC issue count %0d %0d",scalar_macs,mac_product_cycles);
  if(fabric_accepts!=37440||fabric_responses!=37440||output_commands!=12672||output_responses!=12672)$fatal(1,"profile transaction accounting mismatch");
  $display("PROFILE_SUMMARY elapsed=%0d validation=%0d precompute=%0d busy=%0d idle_after_first_busy=%0d final_idle_tail=%0d intertile_idle=%0d mac_product_cycles=%0d scalar_macs=%0d producer_stall=%0d cpu_control_valid=%0d cpu_control_wait=%0d busy_sram_overlap=%0d",end_tick-start_tick,phase_cycles[0],phase_cycles[1],phase_cycles[2],phase_cycles[3],end_tick-last_busy-1,phase_cycles[3]-(end_tick-last_busy-1),mac_product_cycles,scalar_macs,producer_stall_cycles,cpu_control_cycles,cpu_control_wait_cycles,busy_overlap_rw);
  $display("PROFILE_BUS fabric_accepts=%0d fabric_responses=%0d fabric_peak=%0d fabric_backpressure=%0d fabric_no_offer=%0d sram_idle_outstanding=%0d sram_idle_empty=%0d source_requests=%0d live_requests=%0d output_requests=%0d",fabric_accepts,fabric_responses,fabric_max_inflight,fabric_backpressure,fabric_no_offer,sram_idle_outstanding,sram_idle_empty,source_staging_cmds,live_cmds,output_shared_cmds);
  $display("PROFILE_OUTPUT commands=%0d responses=%0d latency_sum=%0d latency_max=%0d credit_blocked_next_ready=%0d descriptor_idle_data_ready=%0d active_no_data=%0d command_backpressure=%0d same_edge_response_next_command=%0d",output_commands,output_responses,output_latency_sum,output_latency_max,output_credit_blocked,output_descriptor_idle_ready,output_no_data,output_cmd_wait,output_cmd_with_rsp);
  for(p=0;p<4;p=p+1)$display("PROFILE_PHASE phase=%0d cycles=%0d reads=%0d writes=%0d idle=%0d",p,phase_cycles[p],phase_reads[p],phase_writes[p],phase_idle[p]);
  for(p=0;p<6;p=p+1)$display("PROFILE_PORT port=%0d commands=%0d responses=%0d reads=%0d writes=%0d command_wait=%0d response_wait=%0d latency_sum=%0d latency_max=%0d offer_delay_sum=%0d pending_cycles=%0d response_to_next_accept_sum=%0d",p,ncmd[p],nrsp[p],nread[p],nwrite[p],wait_cmd[p],wait_rsp[p],latency_sum[p],latency_max[p],offer_delay_sum[p],pending_cycles[p],response_to_next_cmd_sum[p]);
  for(p=0;p<16;p=p+1)begin
   $display("PROFILE_TILE tile=%0d first_busy=%0d last_busy=%0d busy_cycles=%0d first_output=%0d last_output_ack=%0d output_commands=%0d output_responses=%0d first_weight_commit=%0d last_weight_commit=%0d",p,tile_first_busy[p]-start_tick,tile_last_busy[p]-start_tick,tile_busy[p],tile_first_output[p]-start_tick,tile_last_output_rsp[p]-start_tick,tile_output_accept[p],tile_output_rsp[p],tile_wfirst[p]-start_tick,tile_wlast[p]-start_tick);
   if(engine_state_cycles[p]!=0)$display("PROFILE_ENGINE state=%0d cycles=%0d",p,engine_state_cycles[p]);
  end
  for(p=0;p<64;p=p+1)if(csr_cmd[p]!=0||csr_wait[p]!=0)$display("PROFILE_CSR address=%0d commands=%0d reads=%0d wait_cycles=%0d",4*p,csr_cmd[p],csr_reads[p],csr_wait[p]);
  for(p=0;p<32;p=p+1)if(output_gap[p]+fabric_gaps[p]+sram_gaps[p]!=0)$display("PROFILE_GAP cycles_capped_31=%0d output=%0d fabric=%0d sram=%0d",p,output_gap[p],fabric_gaps[p],sram_gaps[p]);
 end
`undef DUT
`undef FIO
`undef ACC
`undef DMA
`undef MAIN
`undef MERGE
`undef FAB
`undef MEM
endmodule
