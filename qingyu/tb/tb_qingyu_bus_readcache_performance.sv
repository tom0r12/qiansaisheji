`timescale 1ns/1ps
// Passive FIFO scoreboard for ordered, queued official-fabric transactions.
// Acceptance order and externally supplied source data define the expectations.
// Expected data come from the externally supplied shared.hex source image.
module tb_qingyu_bus_readcache_performance;
 tb_qingyu_bus_soc fixture();
`define DUT fixture.dut
`define MAIN fixture.dut.u_e203_subsys_top.u_e203_subsys_main
`define FAB `MAIN.u_e203_subsys_mems
`define MERGE `MAIN.u_mem_merge
`define DMA `DUT.u_dma_merge
`define MEM `DUT.u_shared
`define FIO `DUT.u_fio
`define ACC `FIO.u_accel
`ifndef QINGYU_EXPECT_LIVE_READS
`define QINGYU_EXPECT_LIVE_READS 11936
`endif
 integer ticks=0, task_start=-1, stage_start=-1, task_end=-1, sram_end=-1;
 integer cache_clears=0,cache_hits=0,cache_misses=0,cache_ram_reads=0,cache_ram_writes=0,cache_prefetch_reads=0;

 integer shared_cmds=0, shared_rsps=0, fabric_cmds=0, fabric_rsps=0;
 integer dma_cmds=0,dma_rsps=0,cpu_cmds=0;
 integer shared_wait=0,fabric_wait=0,dma_wait=0,shared_rsp_wait=0,fabric_rsp_wait=0;
 integer source_reads=0, validation_reads=0, load_reads=0,live_reads=0,live_writes=0,output_writes=0;
 integer busy_cycles=0, first_busy=-1,last_busy=-1;
 integer private_inputs=0,private_weights=0;
 integer d_cmd[0:5],d_rsp[0:5];
 localparam integer D_DEPTH=8;
 integer d_count[0:5],d_head[0:5],d_tail[0:5];
 reg d_tag[0:5][0:D_DEPTH-1],d_read[0:5][0:D_DEPTH-1];
 reg [31:0] d_addr[0:5][0:D_DEPTH-1];
 integer output_peak=0,output_multi_cycles=0,output_accepted=0,output_returned=0;
 integer output_last_cycle=-2,output_burst=0,output_max_burst=0;
 reg [25343:0] output_seen='0;
 reg [11935:0] source_seen='0,live_seen='0;
 reg [3167:0] input_seen='0;
 localparam integer MONITOR_DEPTH=32;
 reg q_valid[0:MONITOR_DEPTH-1],q_tag[0:MONITOR_DEPTH-1],q_shared[0:MONITOR_DEPTH-1];
 reg q_seen[0:MONITOR_DEPTH-1],q_response_seen[0:MONITOR_DEPTH-1],q_read[0:MONITOR_DEPTH-1];
 reg [31:0] q_addr[0:MONITOR_DEPTH-1],q_data[0:MONITOR_DEPTH-1],q_rsp_data[0:MONITOR_DEPTH-1];
 reg [3:0] q_mask[0:MONITOR_DEPTH-1];
 reg q_rsp_err[0:MONITOR_DEPTH-1];
 integer q_owner[0:MONITOR_DEPTH-1],q_dma_owner[0:MONITOR_DEPTH-1];
 integer q_head=0,q_tail=0,q_count=0,q_peak=0,q_multi_cycles=0,q_integral=0;
 integer q_scan,q_slot,s_slot=-1,dma_owner;
 reg f_tag,f_read; reg [31:0] f_addr,f_data;reg [3:0] f_mask;
 reg s_pending=0,s_tag=0,s_read;reg [31:0] s_addr;reg [3:0] s_mask;
 integer p,n,idx,selected,valid_count,wtile,wk,wpair;
 reg window_open;
 function automatic bit live_data(input [31:0] a);
  live_data=(a>=32'ha0000000&&a<32'ha0003180)||(a>=32'ha0004000&&a<32'ha000c900);
 endfunction
 function automatic bit source_data(input [31:0] a);
  source_data=(a>=32'ha0040000&&a<32'ha0043180)||(a>=32'ha0044000&&a<32'ha004c900);
 endfunction
 function automatic integer live_slot(input [31:0] a);
  live_slot=a<32'ha0003180 ? (a-32'ha0000000)>>2 : 3168+((a-32'ha0004000)>>2);
 endfunction
 initial for(p=0;p<6;p=p+1) begin d_cmd[p]=0;d_rsp[p]=0;d_count[p]=0;d_head[p]=0;d_tail[p]=0;end

 always @(posedge `DUT.qingyu_bus_clk) begin
  ticks=ticks+1;
  if(!`DUT.qingyu_bus_rst_n) begin
   q_head=0;q_tail=0;q_count=0;s_pending=0;s_slot=-1;
   for(q_scan=0;q_scan<MONITOR_DEPTH;q_scan=q_scan+1)q_valid[q_scan]=0;
   for(p=0;p<6;p=p+1)begin d_count[p]=0;d_head[p]=0;d_tail[p]=0;end
  end else begin
   // Include arbitration before the first source parameter request is accepted.
   for(p=0;p<2;p=p+1)
    if(task_start<0&&`MERGE.s_cmd_valid[p]&&`MERGE.s_cmd_read[p]&&source_data(`MERGE.s_cmd_addr[32*p+:32])) task_start=ticks;
   if(stage_start<0&&`FIO.icb_cmd_valid&&!`FIO.icb_cmd_read&&
      (`FIO.icb_cmd_addr==32'hf00000b4||`FIO.icb_cmd_addr==32'hf00000b0||
       `FIO.icb_cmd_addr==32'hf0000038||`FIO.icb_cmd_addr==32'hf0000084||
       `FIO.icb_cmd_addr==32'hf00000bc||`FIO.icb_cmd_addr==32'hf00000c8))stage_start=ticks;
   window_open=task_start>=0&&task_end<0;
   if(`MEM.cache_clear)begin
    cache_clears++;
    if(`MEM.ram_cs)$fatal(1,"RAM activity during cache clear");
   end
   if(task_start==ticks)begin
    if(cache_clears==0 || `MEM.u_cache.cache_valid || `MEM.u_cache.look_valid)
     $fatal(1,"task source access did not start with explicitly cold cache");
   end
   if(window_open)begin
    if(`MEM.icb_cmd_valid && `MEM.icb_cmd_ready && `MEM.icb_cmd_read)begin
     if(`MEM.u_cache.read_hit)cache_hits++;else cache_misses++;
    end
    if(`MEM.ram_cs)begin
     if(`MEM.ram_we)cache_ram_writes++;else cache_ram_reads++;
     if(`MEM.u_cache.speculative_read)cache_prefetch_reads++;
    end
   end

   if(window_open) begin
    if(d_count[2]>1)output_multi_cycles++;
    q_integral=q_integral+q_count;if(q_count>1)q_multi_cycles++;
    if(`MEM.icb_cmd_valid&&!`MEM.icb_cmd_ready)shared_wait++;
    if(`FAB.mem_icb_cmd_valid&&!`FAB.mem_icb_cmd_ready)fabric_wait++;
    if(`DMA.m_cmd_valid&&!`DMA.m_cmd_ready)dma_wait++;
    if(`MEM.icb_rsp_valid&&!`MEM.icb_rsp_ready)shared_rsp_wait++;
    if(`FAB.mem_icb_rsp_valid&&!`FAB.mem_icb_rsp_ready)fabric_rsp_wait++;
    if(`ACC.busy)begin busy_cycles++;last_busy=ticks;if(first_busy<0)first_busy=ticks;end
   end
   // Every private-memory commit must agree with the immutable source image.
   if(window_open&&`ACC.input_write) begin
    if(!`ACC.input_pair||`ACC.input_elem[0])$fatal(1,"input transfer is not a packed aligned pair");
    idx=`ACC.input_elem>>1;
    if(idx>=3168||input_seen[idx])$fatal(1,"duplicate/out-of-range private input");
    if({`ACC.input_data_hi,`ACC.input_data}!==`MEM.mem[65536+idx])$fatal(1,"private X source mismatch idx=%0d",idx);
    input_seen[idx]=1;private_inputs++;
   end
   if(window_open&&`ACC.weight_write) begin
    wtile=private_weights/512;wk=(private_weights%512)/8;wpair=private_weights%8;
    if(wtile>=16||`ACC.weight_k!=wk||`ACC.weight_pair!=wpair)$fatal(1,"private W address/order mismatch");
    if(`ACC.weight_word!==`MEM.mem[69632+wk*128+wtile*8+wpair])$fatal(1,"private W source mismatch tile=%0d k=%0d pair=%0d",wtile,wk,wpair);
    private_weights++;
   end

   // Match commands before zero-cycle responses at the same edge. The original
   // fabric permits only one outstanding slave transaction; its source FIFO
   // still records every originating command before any shared completion.
   // Each accepted official-fabric command enters an independent FIFO.
   if(`FAB.mem_icb_cmd_valid&&`FAB.mem_icb_cmd_ready)begin
    if(q_count==MONITOR_DEPTH||q_valid[q_tail])$fatal(1,"monitor command FIFO overflow");
    valid_count=0;selected=-1;
    for(p=0;p<2;p=p+1)if(`MERGE.s_cmd_valid[p]&&`MERGE.s_cmd_ready[p])begin valid_count++;selected=p;end
    if(valid_count!=1)$fatal(1,"fabric command without exactly one originating master");
    if(`FAB.mem_icb_cmd_addr!==`MERGE.s_cmd_addr[32*selected+:32]||
       `FAB.mem_icb_cmd_read!==`MERGE.s_cmd_read[selected]||
       `FAB.mem_icb_cmd_wdata!==`MERGE.s_cmd_wdata[32*selected+:32]||
       `FAB.mem_icb_cmd_wmask!==`MERGE.s_cmd_wmask[4*selected+:4])$fatal(1,"master-to-fabric command corruption");
    q_valid[q_tail]=1;q_seen[q_tail]=0;q_response_seen[q_tail]=0;
    q_addr[q_tail]=`FAB.mem_icb_cmd_addr;q_read[q_tail]=`FAB.mem_icb_cmd_read;
    q_data[q_tail]=`FAB.mem_icb_cmd_wdata;q_mask[q_tail]=`FAB.mem_icb_cmd_wmask;
    q_shared[q_tail]=q_addr[q_tail][31:19]==(32'ha0000000>>19);
    q_tag[q_tail]=window_open&&q_shared[q_tail];q_owner[q_tail]=selected;q_dma_owner[q_tail]=-1;
    if(selected==1)begin
     valid_count=0;
     for(p=0;p<6;p=p+1)if(`DMA.s_cmd_valid[p]&&`DMA.s_cmd_ready[p])begin valid_count++;q_dma_owner[q_tail]=p;end
     if(valid_count!=1)$fatal(1,"DMA fabric command has no unique original owner");
    end
    if(q_tag[q_tail])begin fabric_cmds++;if(selected==0)cpu_cmds++;end
    q_tail=(q_tail+1)%MONITOR_DEPTH;q_count++;if(q_count>q_peak)q_peak=q_count;
   end
   if(`MEM.icb_cmd_valid&&`MEM.icb_cmd_ready)begin
    q_slot=-1;
    for(q_scan=0;q_scan<q_count;q_scan=q_scan+1)begin
     idx=(q_head+q_scan)%MONITOR_DEPTH;
     if(q_slot<0&&q_valid[idx]&&q_shared[idx]&&!q_seen[idx])q_slot=idx;
    end
    if(q_slot<0||s_pending)$fatal(1,"SRAM command bypassed official fabric");
    f_addr=q_addr[q_slot];f_read=q_read[q_slot];f_data=q_data[q_slot];f_mask=q_mask[q_slot];f_tag=q_tag[q_slot];
    if(`MEM.icb_cmd_addr!==f_addr||`MEM.icb_cmd_read!==f_read||`MEM.icb_cmd_wdata!==f_data||`MEM.icb_cmd_wmask!==f_mask)$fatal(1,"fabric-to-SRAM command corruption/order");
    q_seen[q_slot]=1;s_pending=1;s_slot=q_slot;s_tag=f_tag;s_read=f_read;s_addr=f_addr;s_mask=f_mask;
    if(f_tag)begin
     shared_cmds++;
     if(source_data(f_addr)&&f_read)begin
      source_reads++;
      if(stage_start<0)validation_reads++;
      else begin
       idx=live_slot(f_addr-32'h40000);
       if(source_seen[idx])$fatal(1,"source loading duplicated");
       source_seen[idx]=1;load_reads++;
      end
     end else if(live_data(f_addr))begin
      idx=live_slot(f_addr);
      if(f_read)begin
       if(!live_seen[idx])$fatal(1,"live read before cold load");
       live_reads++;
      end else begin
       if(live_seen[idx]||f_mask!=4'hf||f_addr[1:0]!=0)$fatal(1,"invalid live loading write");
       if(f_data!==`MEM.mem[((f_addr-32'ha0000000)>>2)+65536])$fatal(1,"cold loading data differs from source");
       live_seen[idx]=1;live_writes++;
      end
     end else if(!(f_addr>=32'ha0010000&&f_addr<32'ha001c600&&!f_read))
      $fatal(1,"unexpected complete-window shared access %h",f_addr);
    end
   end
   // SRAM completion happens before fabric completion; retain its response.
   if(`MEM.icb_rsp_valid&&`MEM.icb_rsp_ready)begin
    if(!s_pending||s_slot<0||!q_valid[s_slot]||!q_seen[s_slot])$fatal(1,"shared response without a routed command");
    if(`MEM.icb_rsp_err)$fatal(1,"unexpected shared SRAM error");
    q_response_seen[s_slot]=1;q_rsp_data[s_slot]=`MEM.icb_rsp_rdata;q_rsp_err[s_slot]=`MEM.icb_rsp_err;
    if(s_tag)begin
     shared_rsps++;
     if(!s_read&&s_addr>=32'ha0010000&&s_addr<32'ha001c600)begin
      idx=(s_addr-32'ha0010000)>>2;
      if(s_mask!=4'hf||s_addr[1:0]!=0||output_seen[idx])$fatal(1,"invalid output write");
      output_seen[idx]=1;output_writes++;
      if(output_writes==12672)sram_end=ticks;
     end
    end
    s_pending=0;
   end
   if(`FAB.mem_icb_rsp_valid&&`FAB.mem_icb_rsp_ready)begin
    if(q_count==0||!q_valid[q_head])$fatal(1,"fabric response without queued request");
    if(q_shared[q_head])begin
     if(!q_response_seen[q_head]||`FAB.mem_icb_rsp_err!==q_rsp_err[q_head]||
        (q_read[q_head]&&`FAB.mem_icb_rsp_rdata!==q_rsp_data[q_head]))$fatal(1,"fabric response bypass/corruption");
     if(q_tag[q_head])fabric_rsps++;
    end
    selected=q_owner[q_head];
    if(!`MERGE.s_rsp_valid[selected]||!`MERGE.s_rsp_ready[selected]||
       `MERGE.s_rsp_err[selected]!==`FAB.mem_icb_rsp_err||
       `MERGE.s_rsp_rdata[32*selected+:32]!==`FAB.mem_icb_rsp_rdata)
     $fatal(1,"CPU/DMA merge response owner/data mismatch");
    if(`MERGE.s_rsp_valid[1-selected])$fatal(1,"CPU/DMA merge duplicated response");
    if(selected==1)begin
     dma_owner=q_dma_owner[q_head];
     if(dma_owner<0||!`DMA.s_rsp_valid[dma_owner]||!`DMA.s_rsp_ready[dma_owner]||
        `DMA.s_rsp_err[dma_owner]!==`FAB.mem_icb_rsp_err||
        `DMA.s_rsp_rdata[32*dma_owner+:32]!==`FAB.mem_icb_rsp_rdata)
      $fatal(1,"DMA response differs from ordered fabric owner/data");
     for(p=0;p<6;p=p+1)if(p!=dma_owner&&`DMA.s_rsp_valid[p])$fatal(1,"DMA duplicated response");
    end
    q_valid[q_head]=0;q_head=(q_head+1)%MONITOR_DEPTH;q_count--;
   end
   // Record all six DMA response routes, including the last response after end_tick.
   for(p=0;p<6;p=p+1)begin
    if(`DMA.s_rsp_valid[p]&&`DMA.s_rsp_ready[p])begin
     if(d_count[p]==0)$fatal(1,"DMA response to wrong/no owner");
     if(`DMA.s_rsp_err[p])$fatal(1,"unexpected DMA error");
     if(d_tag[p][d_head[p]])begin
      d_rsp[p]++;dma_rsps++;
      if(p==2&&!d_read[p][d_head[p]]&&d_addr[p][d_head[p]]>=32'ha0010000&&d_addr[p][d_head[p]]<32'ha001c600&&output_returned==12671)begin
       if(sram_end<0||task_end>=0||output_writes!=12672)$fatal(1,"invalid final DMA completion");
       task_end=ticks;
      end
     end
     if(p==2&&!d_read[p][d_head[p]]&&d_addr[p][d_head[p]]>=32'ha0010000&&d_addr[p][d_head[p]]<32'ha001c600)output_returned++;
     d_count[p]--;d_head[p]=(d_head[p]+1)%D_DEPTH;
    end
    if(`DMA.s_cmd_valid[p]&&`DMA.s_cmd_ready[p])begin
     if((p!=2&&d_count[p]!=0)||d_count[p]>=4)$fatal(1,"DMA source exceeded allowed outstanding count");
     if(!(`DMA.m_cmd_valid&&`DMA.m_cmd_ready))$fatal(1,"DMA accepted without upstream acceptance");
     if(`DMA.m_cmd_addr!==`DMA.s_cmd_addr[32*p+:32]||`DMA.m_cmd_read!==`DMA.s_cmd_read[p]||
        `DMA.m_cmd_wdata!==`DMA.s_cmd_wdata[32*p+:32]||`DMA.m_cmd_wmask!==`DMA.s_cmd_wmask[4*p+:4])$fatal(1,"DMA merge payload corruption");
     d_tag[p][d_tail[p]]=window_open;d_read[p][d_tail[p]]=`DMA.s_cmd_read[p];d_addr[p][d_tail[p]]=`DMA.s_cmd_addr[32*p+:32];
     if(p==2&&!d_read[p][d_tail[p]]&&d_addr[p][d_tail[p]]>=32'ha0010000&&d_addr[p][d_tail[p]]<32'ha001c600)begin
      output_accepted++;
      output_burst=(output_last_cycle==ticks-1)?output_burst+1:1;
      output_last_cycle=ticks;if(output_burst>output_max_burst)output_max_burst=output_burst;
     end
     d_count[p]++;d_tail[p]=(d_tail[p]+1)%D_DEPTH;
     if(p==2&&d_count[p]>output_peak)output_peak=d_count[p];
     if(window_open)begin d_cmd[p]++;dma_cmds++;end
    end
   end
  end
 end

 always @(posedge fixture.clk)if(fixture.host_valid)begin
  if(task_start<0||task_end<0||output_writes!=12672||!(&output_seen[12671:0]))$fatal(1,"missing complete task outputs");
  if(load_reads!=11936||live_writes!=11936||live_reads!=`QINGYU_EXPECT_LIVE_READS||!(&source_seen)||!(&live_seen))
   $fatal(1,"incomplete cold loading reads=%0d writes=%0d live_reads=%0d",load_reads,live_writes,live_reads);
  if(private_inputs!=3168||private_weights!=8192||!(&input_seen))$fatal(1,"missing private X/W commits");
  if(shared_cmds!=shared_rsps||shared_cmds!=fabric_cmds||fabric_cmds!=fabric_rsps||fabric_cmds!=cpu_cmds+dma_cmds||dma_cmds!=dma_rsps)
   $fatal(1,"route counts differ shared=%0d/%0d fabric=%0d/%0d cpu=%0d dma=%0d/%0d",shared_cmds,shared_rsps,fabric_cmds,fabric_rsps,cpu_cmds,dma_cmds,dma_rsps);
  for(n=0;n<6;n=n+1)if(d_cmd[n]!=d_rsp[n])$fatal(1,"DMA port %0d lost response",n);
  $display("QINGYU_BUS_TASK cycles=%0d validation_and_setup_cycles=%0d busy_cycles=%0d first_busy=%0d tail=%0d sram_complete_cycles=%0d final_response_return_cycles=%0d",task_end-task_start,stage_start-task_start,busy_cycles,first_busy-task_start,task_end-last_busy,sram_end-task_start,task_end-sram_end);
  $display("QINGYU_BUS_COUNTS shared_cmds=%0d shared_rsps=%0d fabric_cmds=%0d fabric_rsps=%0d cpu_cmds=%0d dma_cmds=%0d dma_rsps=%0d shared_wait=%0d fabric_wait=%0d dma_wait=%0d shared_rsp_wait=%0d fabric_rsp_wait=%0d",shared_cmds,shared_rsps,fabric_cmds,fabric_rsps,cpu_cmds,dma_cmds,dma_rsps,shared_wait,fabric_wait,dma_wait,shared_rsp_wait,fabric_rsp_wait);
  $display("QINGYU_BUS_CLASSES source_reads=%0d validation_reads=%0d load_reads=%0d live_reads=%0d live_writes=%0d output_writes=%0d private_inputs=%0d private_weights=%0d",source_reads,validation_reads,load_reads,live_reads,live_writes,output_writes,private_inputs,private_weights);
  $display("QINGYU_BUS_DMA cw=%0d sw=%0d mem=%0d ld=%0d in=%0d sr=%0d",d_cmd[0],d_cmd[1],d_cmd[2],d_cmd[3],d_cmd[4],d_cmd[5]);
  $display("QINGYU_BUS_QUEUE max_outstanding=%0d multiple_outstanding_cycles=%0d outstanding_cycle_sum=%0d",q_peak,q_multi_cycles,q_integral);
  if(output_accepted!=12672||output_returned!=12672||d_count[2]!=0)$fatal(1,"output queue completion count mismatch");
  $display("QINGYU_OUTPUT_QUEUE max_outstanding=%0d multiple_outstanding_cycles=%0d accepted=%0d returned=%0d max_accept_burst=%0d",output_peak,output_multi_cycles,output_accepted,output_returned,output_max_burst);
  if(cache_clears<2 || cache_hits+cache_misses!=source_reads+live_reads || cache_ram_writes!=live_writes+output_writes)
   $fatal(1,"cache activity accounting mismatch");
  $display("QINGYU_READCACHE clears=%0d hits=%0d misses=%0d ram_reads=%0d ram_writes=%0d prefetch_reads=%0d",cache_clears,cache_hits,cache_misses,cache_ram_reads,cache_ram_writes,cache_prefetch_reads);
  $display("PASS official fabric path: every shared transaction routed and acknowledged");
 end
`undef DUT
`undef MAIN
`undef FAB
`undef MERGE
`undef DMA
`undef MEM
`undef FIO
`undef ACC
endmodule
