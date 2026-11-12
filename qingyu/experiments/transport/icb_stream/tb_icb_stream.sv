`timescale 1ns/1ps
module tb_icb_stream;
 parameter integer OUTSTANDING=4;
 parameter integer RESPONSE_QUEUE=0; // Test-only delayed return to fill all 8 engine credits.
 localparam integer READ_DEPTH=16;
 reg clk=0,rst_n=0,soft_abort=0,cache_clear=0;
 always #5 clk=~clk;
 reg rdesc_v=0,wdesc_v=0,rdready=0,wv=0,wl=0,rdrdy=0,wdrdy=0;
 wire rdesc_r,wdesc_r,rdv,rdlast,wrready,rdone,wdone,rderr,wderr,busy,draining;
 reg [31:0] rb=0,wb=0,rn=0,wn=0,wd=0;wire[31:0]rdata;
 wire cv,cq,cread,rv,rr,rerr;wire[31:0]ca,cd,rd;wire[3:0]cm;
 wire frv,frr,fre;wire[31:0]frd;
 wire sv,sq,sread,srv,srr,se;wire[31:0]sa,sd,sdata;wire[3:0]sm;
 reg response_allow=1,inject_error=0;
 integer error_at=-1;
 integer seed=17,random_state=17;
 reg active=0,random_stalls=0,expect_fail=0,seen_fault=0;
 integer case_id=0,cycle=0,local_cycle=0,tests=0,commands=0,responses=0,shared_commands=0,shared_responses=0;
 integer read_commands=0,write_commands=0,read_responses=0,write_responses=0,write_words=0,read_words=0;
 integer read_descriptors=0,write_descriptors=0,read_done_count=0,write_done_count=0;
 integer out_head=0,out_tail=0,cmd_wait=0,rsp_wait=0,peak=0,read_peak=0,held_checks=0;
 integer first_shared=-1,last_shared=-1,min_gap=1000000,max_gap=0,first_master=-1,last_master=-1;
 integer maximum_credit_seen=0,full_replacements=0;
 integer abort_events=0,error_events=0,fault_with_held_command=0,fault_with_held_read_output=0,hard_reset_events=0;
 integer response_pause=0,read_pause=0,done_pause=0,abort_after=-1;
 reg abort_held=0,aborted=0,hard_reset_case=0,boundary_case=0;
 integer wrong_last=0;
 reg [31:0] reference_mem[0:131071],cmd_addr[0:8191],cmd_data[0:8191],expected_response[0:8191];
 reg cmd_read[0:8191],cmd_last[0:8191];
 reg [31:0] output_data[0:8191];reg output_last[0:8191];
 reg old_command_stall=0,old_output_stall=0,old_fabric_response_stall=0,old_rd_done_stall=0,old_wr_done_stall=0;
 reg [68:0] held_command;reg [32:0] held_output,held_fabric_response;
 reg held_rd_error,held_wr_error;
 reg fault_this_edge;
 wire bad_input=wv&&wrready&&(wl!=(write_words==integer'(wn)-1));
 generate if(RESPONSE_QUEUE==0)begin:g_native_return
  assign rv=frv&&response_allow;
  assign frr=rr&&response_allow;
  assign rd=frd;
  assign rerr=fre||(inject_error&&responses==error_at);
 end else begin:g_delayed_return
  // Verification-only response delay FIFO; never included in throughput claims.
  // Every command still traverses the original fabric and real shared wrapper.
  reg [32:0] data[0:15];integer head=0,tail=0,count=0;
  assign rv=(count!=0)&&response_allow;
  assign frr=count<16;
  assign rd=data[head][31:0];
  assign rerr=data[head][32]||(inject_error&&responses==error_at);
  always @(posedge clk)begin
   if(!rst_n)begin head<=0;tail<=0;count<=0;end
   else begin
    if(frv&&frr)begin data[tail]<={fre,frd};tail<=(tail+1)%16;end
    if(rv&&rr)head<=(head+1)%16;
    case({frv&&frr,rv&&rr})
     2'b10:count<=count+1;
     2'b01:count<=count-1;
     default:begin end
    endcase
   end
  end
 end endgenerate
 qingyu_icb_stream #(.OUTSTANDING(OUTSTANDING),.READ_DEPTH(READ_DEPTH),.WRITE_DEPTH(8)) engine(
  .clk(clk),.rst_n(rst_n),.soft_abort(soft_abort),
  .rd_desc_valid(rdesc_v),.rd_desc_ready(rdesc_r),.rd_desc_base(rb),.rd_desc_count(rn),
  .rd_word_valid(rdv),.rd_word_ready(rdready),.rd_word_data(rdata),.rd_word_last(rdlast),
  .rd_done_valid(rdone),.rd_done_ready(rdrdy),.rd_done_error(rderr),
  .wr_desc_valid(wdesc_v),.wr_desc_ready(wdesc_r),.wr_desc_base(wb),.wr_desc_count(wn),
  .wr_word_valid(wv),.wr_word_ready(wrready),.wr_word_data(wd),.wr_word_last(wl),
  .wr_done_valid(wdone),.wr_done_ready(wdrdy),.wr_done_error(wderr),
  .busy(busy),.draining(draining),.icb_cmd_valid(cv),.icb_cmd_ready(cq),.icb_cmd_read(cread),
  .icb_cmd_addr(ca),.icb_cmd_wdata(cd),.icb_cmd_wmask(cm),
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
 qingyu_shared_sram shared(
  .clk(clk),.rst_n(rst_n),.cache_clear(cache_clear),.icb_cmd_valid(sv),.icb_cmd_ready(sq),
  .icb_cmd_addr(sa),.icb_cmd_read(sread),.icb_cmd_wdata(sd),.icb_cmd_wmask(sm),
  .icb_rsp_valid(srv),.icb_rsp_ready(srr),.icb_rsp_err(se),.icb_rsp_rdata(sdata));
 function automatic [31:0] pattern(input integer n);
  pattern=32'hc35a197b^(32'(n)*32'h9e3779b9)^32'(case_id*113);
 endfunction
 function automatic integer random_percent;
  begin random_state=(random_state*1103515245+12345)&32'h7fffffff;random_percent=(random_state>>8)%100;end
 endfunction
 always @(posedge clk)begin
  cycle=cycle+1;
  if(!rst_n)begin
   old_command_stall=0;old_output_stall=0;old_fabric_response_stall=0;
   old_rd_done_stall=0;old_wr_done_stall=0;
  end else if(active)begin
   local_cycle++;
   if(commands-responses==OUTSTANDING&&cv&&cq&&rv&&rr)full_replacements++;
   fault_this_edge=soft_abort||(wv&&wrready&&(wl!=(write_words==integer'(wn)-1)))||(rv&&rr&&rerr);
   if(soft_abort)abort_events++;
   if(rv&&rr&&rerr)error_events++;
   if(fault_this_edge&&old_command_stall)fault_with_held_command++;
   if(fault_this_edge&&old_output_stall)fault_with_held_read_output++;
   if(old_command_stall)begin held_checks++;if(!cv||{cread,ca,cd,cm}!==held_command)$fatal(1,"held master command changed case=%0d",case_id);end
   if(old_output_stall)begin held_checks++;if(!rdv||{rdlast,rdata}!==held_output)$fatal(1,"held read output changed case=%0d",case_id);end
   if(old_fabric_response_stall)begin held_checks++;if(!frv||{fre,frd}!==held_fabric_response)$fatal(1,"held official response changed");end
   if(old_rd_done_stall&&(!rdone||rderr!==held_rd_error))$fatal(1,"read completion changed");
   if(old_wr_done_stall&&(!wdone||wderr!==held_wr_error))$fatal(1,"write completion changed");
   old_command_stall=cv&&!cq;held_command={cread,ca,cd,cm};
   old_output_stall=rdv&&!rdready;held_output={rdlast,rdata};
   old_fabric_response_stall=frv&&!frr;held_fabric_response={fre,frd};
   old_rd_done_stall=rdone&&!rdrdy;held_rd_error=rderr;
   old_wr_done_stall=wdone&&!wdrdy;held_wr_error=wderr;
   if(rdesc_v&&rdesc_r)read_descriptors++;
   if(wdesc_v&&wdesc_r)write_descriptors++;
   if(wv&&wrready)write_words++;
   if(cv&&!cq)cmd_wait++;
   if(frv&&!frr)rsp_wait++;
   // Existing output words precede any response enqueued at this edge.
   if(rdv&&rdready)begin
    if(out_head>=out_tail||rdata!==output_data[out_head]||rdlast!==output_last[out_head])
     $fatal(1,"read stream mismatch case=%0d word=%0d data=%h expected=%h last=%b/%b",case_id,read_words,rdata,output_data[out_head],rdlast,output_last[out_head]);
    out_head++;read_words++;
   end
   if(cv&&cq)begin
    if(first_master<0)first_master=local_cycle;last_master=local_cycle;
    if(cm!==4'hf)$fatal(1,"write mask mismatch");
    cmd_addr[commands]=ca;cmd_data[commands]=cd;cmd_read[commands]=cread;
    if(cread)begin
     if(ca!==rb+32'(4*read_commands)||read_commands>=rn||cd!==0)$fatal(1,"read descriptor address/count mismatch");
     cmd_last[commands]=read_commands==rn-1;read_commands++;
    end else begin
     if(ca!==wb+32'(4*write_commands)||write_commands>=wn||cd!==pattern(write_commands))$fatal(1,"write descriptor data/count mismatch");
     cmd_last[commands]=write_commands==wn-1;write_commands++;
    end
    commands++;
   end
   // Same-edge shared command is recorded BEFORE a legal zero-ACK response.
   if(sv&&sq)begin
    if(shared_commands>=commands||{sread,sa,sd,sm}!=={cmd_read[shared_commands],cmd_addr[shared_commands],cmd_data[shared_commands],4'hf})$fatal(1,"official fabric dropped/reordered/changed command");
    if(sa[31:19]!=13'h1400||sa[1:0]!=0)$fatal(1,"invalid address reached shared");
    expected_response[shared_commands]=sread?reference_mem[sa[18:2]]:32'b0;
    if(!sread)reference_mem[sa[18:2]]=sd;
    if(first_shared<0)first_shared=local_cycle;
    if(last_shared>=0)begin
     if(local_cycle-last_shared<min_gap)min_gap=local_cycle-last_shared;
     if(local_cycle-last_shared>max_gap)max_gap=local_cycle-last_shared;
    end
    last_shared=local_cycle;shared_commands++;
   end
   if(srv&&srr)begin
    if(shared_responses>=shared_commands||se||sdata!==expected_response[shared_responses])$fatal(1,"shared response data mismatch");
    shared_responses++;
   end
   if(fault_this_edge)seen_fault=1;
   if(rv&&rr)begin
    if(responses>=commands||responses>=shared_responses||rd!==expected_response[responses])$fatal(1,"master response changed/reordered");
    if(cmd_read[responses])begin
     read_responses++;
     if(!seen_fault)begin output_data[out_tail]=rd;output_last[out_tail]=cmd_last[responses];out_tail++;end
    end else write_responses++;
    responses++;
   end
   if(commands-responses>peak)peak=commands-responses;
   if(commands-responses>maximum_credit_seen)maximum_credit_seen=commands-responses;
   if(commands-responses>OUTSTANDING)$fatal(1,"engine outstanding credit overflow");
   if(out_tail-out_head+read_commands-read_responses+(cv&&!cq&&cread)>READ_DEPTH)$fatal(1,"read FIFO reservation overflow");
   if(out_tail-out_head>read_peak)read_peak=out_tail-out_head;
   if(rdone&&rdrdy)begin
    if(rderr!==expect_fail||read_done_count!=0)$fatal(1,"read completion status/duplication case=%0d",case_id);
    if(!expect_fail&&(read_words!=rn||read_commands!=rn||read_responses!=rn))$fatal(1,"early successful read completion");
    if(expect_fail&&(commands!=responses||out_head!=out_tail))$fatal(1,"failed read completed before drain");
    read_done_count++;
   end
   if(wdone&&wdrdy)begin
    if(wderr!==expect_fail||write_done_count!=0)$fatal(1,"write completion status/duplication case=%0d",case_id);
    if(!expect_fail&&(write_commands!=wn||write_responses!=wn||write_words!=wn))$fatal(1,"write completed before real ACK");
    if(expect_fail&&(commands!=responses||out_head!=out_tail))$fatal(1,"failed write completed before drain");
    write_done_count++;
   end
  end
 end
 task automatic clear_scoreboard;
  begin
   commands=0;responses=0;shared_commands=0;shared_responses=0;read_commands=0;write_commands=0;
   read_responses=0;write_responses=0;write_words=0;read_words=0;read_descriptors=0;write_descriptors=0;
   read_done_count=0;write_done_count=0;out_head=0;out_tail=0;local_cycle=0;seen_fault=0;
   cmd_wait=0;rsp_wait=0;peak=0;read_peak=0;held_checks=0;first_shared=-1;last_shared=-1;min_gap=1000000;max_gap=0;
   first_master=-1;last_master=-1;old_command_stall=0;old_output_stall=0;old_fabric_response_stall=0;
   old_rd_done_stall=0;old_wr_done_stall=0;aborted=0;
  end
 endtask
 task automatic run_case(input integer nr,nw,randomize,input integer fault_index,abort_index,input bit want_held,input integer badlast,input bit hardreset);
  integer guard,j,producer_index;
  bit reset_done;
  begin
   @(negedge clk);active=0;rdesc_v=0;wdesc_v=0;wv=0;soft_abort=0;
   guard=0;producer_index=-1;
   while(!rdesc_r||!wdesc_r)begin @(negedge clk);guard++;if(guard>200)$fatal(1,"no clean descriptor restart");end
   clear_scoreboard();case_id++;rn=nr;wn=nw;
   rb=boundary_case?32'ha007fffc:32'ha0001000;wb=boundary_case?32'ha007fffc:32'ha0010000;
   random_stalls=randomize!=0;error_at=fault_index;inject_error=fault_index>=0;
   abort_after=abort_index;abort_held=want_held;wrong_last=badlast;hard_reset_case=hardreset;
   expect_fail=inject_error||abort_after>=0||wrong_last;
   read_pause=randomize?100:0;response_pause=want_held?40:0;done_pause=randomize?300:0;
   cache_clear=1;@(negedge clk);cache_clear=0;active=1;reset_done=0;
   guard=0;
   while((nr!=0&&read_done_count==0)||(nw!=0&&write_done_count==0)||busy)begin
    rdesc_v=nr!=0&&read_descriptors==0;wdesc_v=nw!=0&&write_descriptors==0;
    rdready=local_cycle>=read_pause&&(!random_stalls||random_percent()>35);
    response_allow=local_cycle>=response_pause&&(!random_stalls||random_percent()>20);
    rdrdy=local_cycle>=done_pause&&(!random_stalls||random_percent()>25);wdrdy=rdrdy;
    if(!wv||write_words>producer_index)begin
     wv=nw!=0&&write_descriptors!=0&&write_words<nw&&!seen_fault&&(!random_stalls||random_percent()>25);
     producer_index=write_words;wd=pattern(write_words);wl=write_words==nw-1;
     if((wrong_last==1&&write_words==3)||(wrong_last==2&&write_words==nw-1))wl=!wl;
    end
    if(seen_fault)wv=0;
    soft_abort=0;
    if(!aborted&&abort_after>=0&&(read_descriptors!=0||write_descriptors!=0)&&commands>=abort_after&&(!abort_held||(cv&&!cq)))begin soft_abort=1;aborted=1;end
    if(hard_reset_case&&!reset_done&&commands>=5&&commands>responses)begin
     hard_reset_events++;rst_n=0;active=0;rdesc_v=0;wdesc_v=0;wv=0;
     repeat(4)@(negedge clk);
     rst_n=1;reset_done=1;clear_scoreboard();nr=0;nw=0;rn=0;wn=0;
    end
    @(negedge clk);guard++;
    if(guard>50000)$fatal(1,"case timeout case=%0d cmd=%0d rsp=%0d rd=%0d/%0d wr=%0d/%0d busy=%b drain=%b",case_id,commands,responses,read_words,nr,write_words,nw,busy,draining);
   end
   rdesc_v=0;wdesc_v=0;wv=0;soft_abort=0;response_allow=1;rdready=1;rdrdy=1;wdrdy=1;
   if(commands!=responses||shared_commands!=commands||shared_responses!=commands||out_head!=out_tail)$fatal(1,"incomplete command/response/data drain");
   if(expect_fail&&!seen_fault)$fatal(1,"requested failure was never exercised");
   if(hardreset&&!reset_done)$fatal(1,"hard reset case never reset active traffic");
   for(j=0;j<write_commands;j++)if(shared.mem[(wb-32'ha0000000)/4+j]!==reference_mem[(wb-32'ha0000000)/4+j])$fatal(1,"physical SRAM write mismatch");
   $display("STREAM_CASE id=%0d reads=%0d writes=%0d random=%0d fault=%0d abort=%0d held_abort=%0d bad_last=%0d hard_reset=%0d cycles=%0d commands=%0d responses=%0d peak=%0d read_fifo_peak=%0d shared_span=%0d min_gap=%0d max_gap=%0d cmd_wait=%0d rsp_wait=%0d held_checks=%0d",case_id,nr,nw,randomize,fault_index,abort_index,want_held,badlast,hardreset,local_cycle,commands,responses,peak,read_peak,last_shared-first_shared,min_gap,max_gap,cmd_wait,rsp_wait,held_checks);
   active=0;tests++;repeat(5)@(negedge clk);
  end
 endtask
 task automatic invalid_descriptor(input [31:0] base,count,input bit write_side);
  integer guard;
  begin
   @(negedge clk);active=0;clear_scoreboard();case_id++;expect_fail=1;rn=0;wn=0;
   rb=base;wb=base;rdrdy=0;wdrdy=0;active=1;
   if(write_side)begin wn=count;wdesc_v=1;end else begin rn=count;rdesc_v=1;end
   @(negedge clk);rdesc_v=0;wdesc_v=0;
   repeat(8)@(negedge clk);
   if((write_side&&!wdone)||(!write_side&&!rdone)||commands!=0)$fatal(1,"invalid descriptor issued or failed to complete");
   rdrdy=1;wdrdy=1;@(negedge clk);active=0;
   if(write_side?write_done_count!=1:read_done_count!=1)$fatal(1,"invalid descriptor completion missing");
   tests++;repeat(3)@(negedge clk);
  end
 endtask
 initial begin
  if($value$plusargs("SEED=%d",seed))begin end random_state=seed;
  for(integer j=0;j<131072;j++)begin reference_mem[j]=32'h7a951c03^(32'(j)*32'h10203);shared.mem[j]=reference_mem[j];end
  repeat(5)@(negedge clk);rst_n=1;
  run_case(1024,0,0,-1,-1,0,0,0);
  run_case(0,1024,0,-1,-1,0,0,0);
  run_case(1024,1024,0,-1,-1,0,0,0);
  run_case(211,157,1,-1,-1,0,0,0);
  run_case(1,1,1,-1,-1,0,0,0);
  for(integer j=0;j<3;j++)begin
   run_case(64,0,1,j==0?0:j==1?31:63,-1,j==0,0,0);
   run_case(13,17,0,-1,-1,0,0,0);
   run_case(0,64,1,j==0?0:j==1?31:63,-1,j==0,0,0);
   run_case(13,17,0,-1,-1,0,0,0);
  end
  run_case(128,128,1,3,-1,1,0,0);run_case(99,101,0,-1,-1,0,0,0);
  run_case(128,128,1,-1,2,1,0,0);run_case(99,101,0,-1,-1,0,0,0);
  run_case(128,128,1,-1,12,0,0,0);run_case(99,101,0,-1,-1,0,0,0);
  run_case(32,32,0,-1,0,0,0,0);run_case(99,101,0,-1,-1,0,0,0);
  run_case(32,32,1,-1,-1,0,1,0);run_case(99,101,0,-1,-1,0,0,0);
  run_case(64,32,1,-1,-1,0,2,0);run_case(99,101,0,-1,-1,0,0,0);
  run_case(128,128,1,-1,-1,1,0,1);run_case(99,101,0,-1,-1,0,0,0);
  boundary_case=1;run_case(1,1,0,-1,-1,0,0,0);boundary_case=0;
  invalid_descriptor(32'ha0000001,4,0);invalid_descriptor(32'ha0000000,0,0);
  invalid_descriptor(32'ha007fffc,2,1);invalid_descriptor(32'hfffffff0,32'hffffffff,1);
  invalid_descriptor(32'h9ffffffc,2,0);
  if(RESPONSE_QUEUE!=0&&(maximum_credit_seen!=OUTSTANDING||full_replacements==0))$fatal(1,"full configured credit boundary was not exercised");
  if(abort_events!=3||error_events!=7||hard_reset_events!=1||fault_with_held_read_output==0)$fatal(1,"required fault/reset/output-hold scenario missing");
  $display("PASS icb_stream outstanding=%0d seed=%0d response_queue=%0d cases=%0d maximum_credit_seen=%0d full_replacements=%0d abort_events=%0d error_events=%0d fault_with_held_command=%0d fault_with_held_read_output=%0d hard_reset_events=%0d",OUTSTANDING,seed,RESPONSE_QUEUE,tests,maximum_credit_seen,full_replacements,abort_events,error_events,fault_with_held_command,fault_with_held_read_output,hard_reset_events);$finish;
 end
 initial begin #10000000;$fatal(1,"global stream timeout");end
endmodule
