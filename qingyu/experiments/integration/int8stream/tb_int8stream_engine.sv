`timescale 1ns/1ps
module tb_int8stream_engine;
 localparam [31:0] SOURCE=32'ha0040000,OUTPUT=32'ha0000000,POISON=32'hcccccccc,MAGIC=32'h31593851;
 localparam integer SOURCE_WORD=65536,OUTPUT_WORDS=6385,QUEUE_SIZE=16384;
 reg clk=0,rst_n=0,start_valid=0;
 always #5 clk=~clk;
 reg [31:0] start_source=SOURCE,start_output=OUTPUT;
 wire start_ready,busy,done,error,cache_clear;
 wire [7:0] error_code;
 wire [31:0] task_cycles,core_cycles,core_load,core_factor,core_cache,core_compute,core_store;
 wire cv,cq,cread,rv,rr,rerr;wire[31:0]ca,cd,rd;wire[3:0]cm;
 wire frv,frr,fre;wire[31:0]frd;
 wire sv,sq,sread,srv,srr,se;wire[31:0]sa,sd,sdata;wire[3:0]sm;
 reg response_allow=1,active=0;
 integer fault_mode=0,random_stalls=0,random_state=3719;
 integer ticks=0,case_id=0,successes=0,failures=0,hard_resets=0,guard;
 integer input_words=0,written_words=0,input_words0=0,written_words0=0,input_words1=0,written_words1=0;
 integer mcmd=0,mrsp=0,scmd=0,srsp=0,reads=0,writes=0,read_acks=0,write_acks=0;
 integer invalidations=0,invalidation_acks=0,magic_commands=0,magic_acks=0,error_responses=0;
 integer clear_count=0,begin_count=0,physical_reads=0,physical_writes=0,cmd_wait=0,rsp_wait=0,peak=0;
 integer start_tick=-1,first_read_tick=-1,magic_tick=-1,finish_tick=-1;
 reg [31:0] input_image[0:8191],expected[0:6384],expected_dense[0:6335];
 reg [31:0] reference_mem[0:131071],cmd_addr[0:QUEUE_SIZE-1],cmd_data[0:QUEUE_SIZE-1],expected_rsp[0:QUEUE_SIZE-1];
 reg cmd_read[0:QUEUE_SIZE-1],cmd_invalidation[0:QUEUE_SIZE-1];
 integer source_seen[0:8191],out_seen[0:6384],out_acked[0:6384];
 reg output_required[0:6384];
 reg old_cmd_stall=0,old_rsp_stall=0,clear_pending=0;
 reg [68:0] held_cmd;reg[32:0]held_rsp;
 string input0_path,expected0_path,input1_path,expected1_path;
 integer fault_checks=0,seed=3719;
 assign rv=frv&&response_allow;
 assign frr=rr&&response_allow;
 assign rd=frd;
 assign rerr=fre||(fault_mode==1&&mrsp==20);
 qingyu_int8stream_engine dut(
  .clk(clk),.rst_n(rst_n),.start_valid(start_valid),.start_ready(start_ready),.start_source(start_source),.start_output(start_output),
  .busy(busy),.done(done),.error(error),.error_code(error_code),.shared_cache_clear(cache_clear),.task_cycles(task_cycles),
  .core_cycles(core_cycles),.core_load_cycles(core_load),.core_factor_cycles(core_factor),.core_cache_cycles(core_cache),
  .core_compute_cycles(core_compute),.core_store_cycles(core_store),
  .icb_cmd_valid(cv),.icb_cmd_ready(cq),.icb_cmd_read(cread),.icb_cmd_addr(ca),.icb_cmd_wdata(cd),.icb_cmd_wmask(cm),
  .icb_rsp_valid(rv),.icb_rsp_ready(rr),.icb_rsp_rdata(rd),.icb_rsp_err(rerr));
 e203_subsys_mems fabric(
  .clk(clk),.rst_n(rst_n),.bus_rst_n(rst_n),
  .mem_icb_cmd_valid(cv),.mem_icb_cmd_ready(cq),.mem_icb_cmd_addr(ca),.mem_icb_cmd_read(cread),
  .mem_icb_cmd_wdata(cd),.mem_icb_cmd_wmask(cm),.mem_icb_rsp_valid(frv),.mem_icb_rsp_ready(frr),
  .mem_icb_rsp_err(fre),.mem_icb_rsp_rdata(frd),
  .sysmem_icb_cmd_valid(sv),.sysmem_icb_cmd_ready(sq),.sysmem_icb_cmd_addr(sa),.sysmem_icb_cmd_read(sread),
  .sysmem_icb_cmd_wdata(sd),.sysmem_icb_cmd_wmask(sm),.sysmem_icb_rsp_valid(srv),.sysmem_icb_rsp_ready(srr),
  .sysmem_icb_rsp_err(se),.sysmem_icb_rsp_rdata(sdata),
  .qspi0_ro_icb_cmd_valid(),.qspi0_ro_icb_cmd_ready(1'b1),.qspi0_ro_icb_cmd_addr(),.qspi0_ro_icb_cmd_read(),.qspi0_ro_icb_cmd_wdata(),
  .qspi0_ro_icb_rsp_valid(1'b0),.qspi0_ro_icb_rsp_ready(),.qspi0_ro_icb_rsp_err(1'b0),.qspi0_ro_icb_rsp_rdata(32'b0),
  .dm_icb_cmd_valid(),.dm_icb_cmd_ready(1'b1),.dm_icb_cmd_addr(),.dm_icb_cmd_read(),.dm_icb_cmd_wdata(),
  .dm_icb_rsp_valid(1'b0),.dm_icb_rsp_ready(),.dm_icb_rsp_rdata(32'b0));
 qingyu_shared_sram shared(.clk(clk),.rst_n(rst_n),.cache_clear(cache_clear),
  .icb_cmd_valid(sv),.icb_cmd_ready(sq),.icb_cmd_addr(sa),.icb_cmd_read(sread),.icb_cmd_wdata(sd),.icb_cmd_wmask(sm),
  .icb_rsp_valid(srv),.icb_rsp_ready(srr),.icb_rsp_err(se),.icb_rsp_rdata(sdata));
 function automatic integer random_percent;
  begin random_state=(random_state*1103515245+12345)&32'h7fffffff;random_percent=(random_state>>8)%100;end
 endfunction
 integer offset,t,slot,j;
 always @(posedge clk)begin
  ticks=ticks+1;
  if(!rst_n)begin old_cmd_stall=0;old_rsp_stall=0;clear_pending=0;end
  else if(active)begin
   if(start_valid&&start_ready)begin
    if(start_tick!=-1)$fatal(1,"second START accepted while task active");start_tick=ticks;
   end
   if(cache_clear)begin clear_count++;clear_pending=1;if(mcmd!=0)$fatal(1,"cache invalidation after task traffic began");end
   if(dut.compute.begin_fire)begin_count++;
   if(old_cmd_stall&&(!cv||{cread,ca,cd,cm}!==held_cmd))$fatal(1,"engine held request changed");
   if(old_rsp_stall&&(!frv||{fre,frd}!==held_rsp))$fatal(1,"official fabric held response changed");
   old_cmd_stall=cv&&!cq;held_cmd={cread,ca,cd,cm};
   old_rsp_stall=frv&&!frr;held_rsp={fre,frd};
   if(cv&&!cq)cmd_wait++;
   if(frv&&!frr)rsp_wait++;
   if(shared.ram_cs)begin
    if(shared.ram_we)begin
     physical_writes++;
     if(!(sv&&sq&&!sread)||shared.ram_addr!==sa[18:2])$fatal(1,"SRAM write bypassed official bus");
    end else physical_reads++;
   end
   if(cv&&cq)begin
    if(start_tick<0||clear_count!=1||mcmd>=QUEUE_SIZE)$fatal(1,"request outside cold START or queue capacity");
    if(cm!==4'hf||ca[1:0]!=0)$fatal(1,"unaligned or partial packet transaction");
    cmd_addr[mcmd]=ca;cmd_data[mcmd]=cd;cmd_read[mcmd]=cread;cmd_invalidation[mcmd]=0;
    if(cread)begin
     if(first_read_tick<0)first_read_tick=ticks;
     if(ca<SOURCE||ca>=SOURCE+32'(input_words*4))$fatal(1,"read outside serialized input");
     offset=integer'((ca-SOURCE)>>2);
     if(source_seen[offset]!=0)$fatal(1,"source word fetched more than once index=%0d",offset);
     if(offset>=10&&invalidation_acks!=1)$fatal(1,"payload/metadata read before marker invalidation ACK");
     source_seen[offset]++;reads++;
    end else begin
     if(ca<OUTPUT||ca>=OUTPUT+32'(OUTPUT_WORDS*4))$fatal(1,"write outside output allocation");
     offset=integer'((ca-OUTPUT)>>2);
     if(offset==0&&cd==0)begin
      if(invalidations!=0||magic_commands!=0||writes!=0)$fatal(1,"duplicate/late invalidation write");
      invalidations++;cmd_invalidation[mcmd]=1;
     end else begin
      if(invalidation_acks!=1||!output_required[offset]||out_seen[offset]!=0||cd!==expected[offset])
       $fatal(1,"output command mismatch offset=%0d data=%h expected=%h",offset,cd,expected[offset]);
      if(offset==0)begin
       for(j=1;j<OUTPUT_WORDS;j++)if(output_required[j]&&out_acked[j]!=1)$fatal(1,"magic offered before payload/header ACK");
       if(read_acks!=input_words)$fatal(1,"magic offered before all source read responses");magic_commands++;
      end else if(offset<=16)begin
       t=offset-1;slot=17+398*t;
       for(j=0;j<integer'((expected[offset]+31)>>5);j++)if(out_acked[slot+j]!=1)$fatal(1,"length header precedes payload ACK");
      end
      out_seen[offset]++;
     end
     writes++;
    end
    mcmd++;
   end
   // Retain original accepted order and handle legal shared zero-ACK at this edge.
   if(sv&&sq)begin
    if(scmd>=mcmd||{sread,sa,sd,sm}!=={cmd_read[scmd],cmd_addr[scmd],cmd_data[scmd],4'hf})$fatal(1,"official path changed/duplicated request");
    expected_rsp[scmd]=sread?reference_mem[sa[18:2]]:32'b0;
    if(!sread)reference_mem[sa[18:2]]=sd;
    scmd++;
   end
   if(srv&&srr)begin
    if(srsp>=scmd||se||sdata!==expected_rsp[srsp])$fatal(1,"shared response ownership/data mismatch");srsp++;
   end
   if(rv&&rr)begin
    if(mrsp>=mcmd||mrsp>=srsp||rd!==expected_rsp[mrsp])$fatal(1,"originating response ownership/data mismatch");
    if(rerr)error_responses++;
    if(cmd_read[mrsp])read_acks++;
    else begin
     write_acks++;
     if(cmd_invalidation[mrsp])invalidation_acks++;
     else begin
      offset=integer'((cmd_addr[mrsp]-OUTPUT)>>2);out_acked[offset]++;
      if(offset==0)begin
       if(rerr)$fatal(1,"normal completion marker returned an error");
       magic_acks++;magic_tick=ticks;
      end
     end
    end
    mrsp++;
   end
   if(mcmd-mrsp>peak)peak=mcmd-mrsp;
   if(mcmd-mrsp>8)$fatal(1,"engine credit overflow");
   if(done)finish_tick=ticks;
   if(ticks%20000==0)$display("PROGRESS case=%0d state=%0d cmd=%0d rsp=%0d core=%0d",case_id,dut.state,mcmd,mrsp,core_cycles);
  end
 end
 always @(negedge clk)if(active&&rst_n&&clear_pending)begin
  if(shared.u_cache.cache_valid||shared.u_cache.look_valid)$fatal(1,"START failed to clear shared read cache");clear_pending=0;
 end
 task automatic prepare_case(input bit use_next,input integer mode,input bit stalls);
  integer n,need;
  reg[31:0] old_magic;
  begin
   @(negedge clk);active=0;start_valid=0;response_allow=1;
   guard=0;while(!start_ready)begin @(negedge clk);guard++;if(guard>200)$fatal(1,"engine did not recover start_ready");end
   if(use_next)begin
    input_words=input_words1;written_words=written_words1;
    $readmemh(input1_path,input_image,0,input_words1-1);$readmemh(expected1_path,expected);
   end else begin
    input_words=input_words0;written_words=written_words0;
    $readmemh(input0_path,input_image,0,input_words0-1);$readmemh(expected0_path,expected);
   end
   if(mode==2)input_image[0]=input_image[0]^1;
   if(mode==4)input_image[1]=1;
   if(mode==5)input_image[138]=32'h30303030;
   old_magic=shared.mem[0];
   for(n=0;n<131072;n++)begin shared.mem[n]=POISON;reference_mem[n]=POISON;end
   shared.mem[0]=old_magic;reference_mem[0]=old_magic;
   for(n=0;n<input_words;n++)begin shared.mem[SOURCE_WORD+n]=input_image[n];reference_mem[SOURCE_WORD+n]=input_image[n];end
   for(n=0;n<8192;n++)source_seen[n]=0;
   for(n=0;n<OUTPUT_WORDS;n++)begin out_seen[n]=0;out_acked[n]=0;output_required[n]=n<17;end
   need=17;
   for(n=0;n<16;n++)begin
    if(expected[n+1]==0||expected[n+1]>12722)$fatal(1,"bad golden length");
    for(integer k=0;k<integer'((expected[n+1]+31)>>5);k++)begin output_required[17+398*n+k]=1;need++;end
   end
   if(need!=written_words)$fatal(1,"golden output write count mismatch");
   mcmd=0;mrsp=0;scmd=0;srsp=0;reads=0;writes=0;read_acks=0;write_acks=0;
   invalidations=0;invalidation_acks=0;magic_commands=0;magic_acks=0;error_responses=0;
   clear_count=0;begin_count=0;physical_reads=0;physical_writes=0;cmd_wait=0;rsp_wait=0;peak=0;
   start_tick=-1;first_read_tick=-1;magic_tick=-1;finish_tick=-1;
   old_cmd_stall=0;old_rsp_stall=0;clear_pending=0;case_id++;
   fault_mode=mode;random_stalls=stalls;start_source=SOURCE;start_output=mode==3?SOURCE:OUTPUT;
   active=1;start_valid=1;
   @(negedge clk);start_valid=0;
  end
 endtask
 task automatic execute_case(input bit next_packet,input integer mode,input bit stalls);
  integer n;
  begin
   prepare_case(next_packet,mode,stalls);
   guard=0;
   while(!done)begin
    response_allow=!random_stalls||random_percent()>30;
    @(negedge clk);guard++;
    if(mode==6&&mcmd>=32&&mcmd>mrsp)begin
     active=0;rst_n=0;start_valid=0;repeat(4)@(negedge clk);rst_n=1;
     hard_resets++;$display("ENGINE_RESET case=%0d outstanding=%0d",case_id,mcmd-mrsp);
     for(n=0;n<input_words;n++)if(shared.mem[SOURCE_WORD+n]!==input_image[n])$fatal(1,"reset corrupted input");
     return;
    end
    if(guard>2100000)$fatal(1,"engine task timeout case=%0d state=%0d cmd=%0d rsp=%0d",case_id,dut.state,mcmd,mrsp);
   end
   // done is sampled on the next rising edge, after its registered assertion.
   @(negedge clk);response_allow=1;
   if(mcmd!=mrsp||scmd!=mcmd||srsp!=mcmd||physical_writes!=writes)$fatal(1,"done before complete real bus drain");
   if(clear_count!=1||begin_count!=1)$fatal(1,"missing cold cache/core begin");
   for(n=0;n<input_words;n++)if(shared.mem[SOURCE_WORD+n]!==input_image[n])$fatal(1,"source packet changed");
   if(mode==0)begin
    if(error||magic_acks!=1||magic_commands!=1||invalidations!=1||invalidation_acks!=1||magic_tick<0||finish_tick<magic_tick)$fatal(1,"bad successful final ACK/done status code=%h",error_code);
    if(reads!=input_words||writes!=written_words+1)$fatal(1,"task traffic count mismatch read=%0d/%0d write=%0d/%0d",reads,input_words,writes,written_words+1);
    for(n=0;n<input_words;n++)if(source_seen[n]!=1)$fatal(1,"missing source word");
    for(n=0;n<OUTPUT_WORDS;n++)begin
     if(shared.mem[n]!==expected[n])$fatal(1,"complete output/poison mismatch word=%0d actual=%h expected=%h",n,shared.mem[n],expected[n]);
     if(out_seen[n]!=(output_required[n]?1:0)||out_acked[n]!=(output_required[n]?1:0))$fatal(1,"output write/ACK mask mismatch");
    end
    $writememh($sformatf("case%0d_output.hex",case_id),shared.mem,0,OUTPUT_WORDS-1);
    successes++;
   end else begin
    if(!error||magic_commands!=0||magic_acks!=0)$fatal(1,"fault incorrectly completed successfully");
    if(mode==2||mode==3)begin
     if(writes!=0)$fatal(1,"malformed header/range wrote destination");
     for(n=0;n<OUTPUT_WORDS;n++)if(shared.mem[n]!==reference_mem[n])$fatal(1,"invalid task changed target");
    end else if(shared.mem[0]!==0||invalidation_acks!=1)$fatal(1,"failed payload retained old success marker");
    if(mode==1&&error_responses!=1)$fatal(1,"response error injection missing");
    failures++;
   end
   $display("ENGINE_CASE id=%0d next=%0d fault=%0d stalls=%0d start_to_magic_ack=%0d first_read_to_magic_ack=%0d done_cycles=%0d engine_cycles=%0d reads=%0d writes=%0d commands=%0d responses=%0d physical_reads=%0d physical_writes=%0d peak=%0d cmd_wait=%0d rsp_wait=%0d cold_clears=%0d core_begin=%0d error=%0d error_code=%0d core_cycles=%0d core_load=%0d core_factor=%0d core_cache=%0d core_compute=%0d core_store=%0d",case_id,next_packet,mode,stalls,magic_tick<0?-1:magic_tick-start_tick,magic_tick<0?-1:magic_tick-first_read_tick,finish_tick-start_tick,task_cycles,reads,writes,mcmd,mrsp,physical_reads,physical_writes,peak,cmd_wait,rsp_wait,clear_count,begin_count,error,error_code,core_cycles,core_load,core_factor,core_cache,core_compute,core_store);
   active=0;repeat(5)@(negedge clk);
  end
 endtask
 initial begin
  if(!$value$plusargs("INPUT=%s",input0_path)||!$value$plusargs("EXPECTED=%s",expected0_path)||
     !$value$plusargs("NEXT_INPUT=%s",input1_path)||!$value$plusargs("NEXT_EXPECTED=%s",expected1_path)||
     !$value$plusargs("INPUT_WORDS=%d",input_words0)||!$value$plusargs("WRITTEN_WORDS=%d",written_words0)||
     !$value$plusargs("NEXT_INPUT_WORDS=%d",input_words1)||!$value$plusargs("NEXT_WRITTEN_WORDS=%d",written_words1))$fatal(1,"missing packet arguments");
  if($value$plusargs("FAULT_CHECKS=%d",fault_checks))begin end
  if($value$plusargs("SEED=%d",seed))begin end random_state=seed;
  shared.mem[0]=POISON;
  repeat(5)@(negedge clk);rst_n=1;
  execute_case(0,0,0);execute_case(1,0,0);
  if(fault_checks!=0)begin
   execute_case(0,1,1);execute_case(0,0,1);
   execute_case(0,2,0);execute_case(0,0,0);
   execute_case(0,3,0);execute_case(0,0,0);
   execute_case(0,4,1);execute_case(0,0,0);
   execute_case(0,5,1);execute_case(0,0,0);
   execute_case(0,6,1);execute_case(0,0,0);
  end
  if(successes!=(fault_checks?8:2)||failures!=(fault_checks?5:0)||hard_resets!=(fault_checks?1:0))$fatal(1,"incomplete engine suite");
  $display("PASS int8stream successes=%0d failures=%0d hard_resets=%0d seed=%0d",successes,failures,hard_resets,seed);$finish;
 end
endmodule
