`timescale 1ns/1ps
// Traffic-only benchmark of the unchanged official E203 memory subsystem.
// A one-cycle, pipelined single-port slave models the response contract, not
// SRAM power/timing. No accelerator or firmware optimization is implied.
module tb_official_memfab_bandwidth;
 reg clk=0,rst_n=0;always #5 clk=~clk;
 integer mode=0,mixed=0,stall=0,rsp_stall=0,zero_write=0,sent=0,received=0,cycle=0,start_cycle=-1;
 integer first_shared=-1,last_shared=-1,min_gap=999999,max_gap=0;
 integer first_latency=-1,accept_cycle[0:1023],latency_sum=0,shared_count=0;
 integer cmd_wait=0,rsp_wait=0,shared_wait=0,inflight_peak=0,read_words=0,write_words=0;
 integer same_edge_write_acks=0;
 localparam integer WORDS=1024;
 wire cv,cr,cq,rv,rr,re;wire[31:0] ca,cd,rd;wire[3:0] cm;
 wire sv,sread,sq,srv,srr,se;wire[31:0] sa,sd,sdata;wire[3:0] sm;
 reg slave_valid=0;reg[31:0] slave_data=0;
 wire zero_write_offer=zero_write&&!slave_valid&&sv&&sq&&!sread;
 reg held_src_cmd=0,held_slave_cmd=0,held_src_rsp=0,held_slave_rsp=0;
 reg [68:0] src_command_q,slave_command_q;
 reg [32:0] src_response_q,slave_response_q;
 integer held_checks=0,slave_rsp_wait=0;
 function automatic bit read_for(input integer n);
  read_for=mixed==2||(mixed==1&&n[0]);
 endfunction
 function automatic [31:0] answer(input [31:0] addr,input [31:0] data,input bit read_op,input [3:0] mask);
  answer=(addr^32'h5a5aa5a5)+(read_op ? 32'h78c39d12 : data^{28'b0,mask});
 endfunction
 // Six consecutive blocked clocks exceed the official two-entry response
 // buffer and exercise the target's retained-response path.
 assign rr=!rsp_stall||cycle%17>=6;
 assign cv=rst_n&&sent<WORDS&&(mode==0||sent==received||(rv&&rr));
 assign cr=read_for(sent);assign ca=32'ha0000000+32'(sent*4);
 assign cd=32'(sent)^32'h12345678;assign cm=4'hf;
 assign sq=(!slave_valid||srr)&&(!stall||cycle%5!=0);
 // A write can complete at its actual accepting edge. If its response is
 // stalled, retain the committed write's response in the ordinary elastic
 // response register. Reads always use that synchronous register.
 assign srv=slave_valid||zero_write_offer;
 assign sdata=slave_valid ? slave_data : answer(sa,sd,sread,sm);assign se=0;
 e203_subsys_mems dut(
  .clk(clk),.rst_n(rst_n),.bus_rst_n(rst_n),
  .mem_icb_cmd_valid(cv),.mem_icb_cmd_ready(cq),.mem_icb_cmd_addr(ca),.mem_icb_cmd_read(cr),
  .mem_icb_cmd_wdata(cd),.mem_icb_cmd_wmask(cm),.mem_icb_rsp_valid(rv),.mem_icb_rsp_ready(rr),
  .mem_icb_rsp_err(re),.mem_icb_rsp_rdata(rd),
  .sysmem_icb_cmd_valid(sv),.sysmem_icb_cmd_ready(sq),.sysmem_icb_cmd_addr(sa),.sysmem_icb_cmd_read(sread),
  .sysmem_icb_cmd_wdata(sd),.sysmem_icb_cmd_wmask(sm),.sysmem_icb_rsp_valid(srv),.sysmem_icb_rsp_ready(srr),
  .sysmem_icb_rsp_err(se),.sysmem_icb_rsp_rdata(sdata),
  .qspi0_ro_icb_cmd_valid(),.qspi0_ro_icb_cmd_ready(1'b1),.qspi0_ro_icb_cmd_addr(),.qspi0_ro_icb_cmd_read(),.qspi0_ro_icb_cmd_wdata(),
  .qspi0_ro_icb_rsp_valid(1'b0),.qspi0_ro_icb_rsp_ready(),.qspi0_ro_icb_rsp_err(1'b0),.qspi0_ro_icb_rsp_rdata(32'b0),
  .dm_icb_cmd_valid(),.dm_icb_cmd_ready(1'b1),.dm_icb_cmd_addr(),.dm_icb_cmd_read(),.dm_icb_cmd_wdata(),
  .dm_icb_rsp_valid(1'b0),.dm_icb_rsp_ready(),.dm_icb_rsp_rdata(32'b0));
 always @(posedge clk)begin
  cycle<=cycle+1;
  if(!rst_n)begin slave_valid<=0;slave_data<=0;held_src_cmd<=0;held_slave_cmd<=0;held_src_rsp<=0;held_slave_rsp<=0;end
  else begin
   if(held_src_cmd)begin held_checks++;if(!cv||{cr,ca,cd,cm}!==src_command_q)$fatal(1,"source command changed while blocked");end
   if(held_slave_cmd)begin held_checks++;if(!sv||{sread,sa,sd,sm}!==slave_command_q)$fatal(1,"fabric command changed while blocked");end
   if(held_src_rsp)begin held_checks++;if(!rv||{re,rd}!==src_response_q)$fatal(1,"fabric response changed while blocked");end
   if(held_slave_rsp)begin held_checks++;if(!srv||{se,sdata}!==slave_response_q)$fatal(1,"slave response changed while blocked");end
   held_src_cmd<=cv&&!cq;src_command_q<={cr,ca,cd,cm};
   held_slave_cmd<=sv&&!sq;slave_command_q<={sread,sa,sd,sm};
   held_src_rsp<=rv&&!rr;src_response_q<={re,rd};
   held_slave_rsp<=srv&&!srr;slave_response_q<={se,sdata};
   if($test$plusargs("DEBUG")&&cycle<30)$display("DEBUG cycle=%0d sent=%0d received=%0d cmd=%b/%b shared=%b/%b rsp=%b/%b slave=%b/%b addr=%h",cycle,sent,received,cv,cq,sv,sq,rv,rr,srv,srr,sa);
   if(cv&&!cq)cmd_wait++;
   if(rv&&!rr)rsp_wait++;
   if(srv&&!srr)slave_rsp_wait++;
   if(sv&&!sq)shared_wait++;
   if(sent-received>inflight_peak)inflight_peak=sent-received;
   if(srv&&srr)slave_valid<=0;
   if(sv&&sq)begin
    slave_valid<=!(zero_write_offer&&srr);slave_data<=answer(sa,sd,sread,sm);
    if(zero_write_offer&&srr)same_edge_write_acks++;
    if(sa!==32'ha0000000+32'(shared_count*4)||sd!==(32'(shared_count)^32'h12345678)||sm!=4'hf||sread!==read_for(shared_count))
     $fatal(1,"fabric command order/data mismatch");
    if(sread)read_words++;else write_words++;
    if(first_shared<0)first_shared=cycle;
    if(last_shared>=0)begin
     if(cycle-last_shared<min_gap)min_gap=cycle-last_shared;
     if(cycle-last_shared>max_gap)max_gap=cycle-last_shared;
    end
    last_shared=cycle;shared_count++;
   end
   if(cv&&start_cycle<0)start_cycle=cycle;
   if(cv&&cq)begin accept_cycle[sent]=cycle;sent<=sent+1;end
   if(rv&&rr)begin
    if(received>=sent||re||rd!==answer(32'ha0000000+32'(received*4),32'(received)^32'h12345678,read_for(received),4'hf))$fatal(1,"fabric response mismatch");
    if(first_latency<0)first_latency=cycle-accept_cycle[received];
    latency_sum=latency_sum+cycle-accept_cycle[received];received<=received+1;
    if(received==WORDS-1)begin
     if(shared_count!=WORDS||sent!=WORDS)$fatal(1,"lost or duplicated fabric request");
     $display("PASS official_memfab mode=%0d mixed=%0d stall=%0d rsp_stall=%0d zero_write=%0d words=%0d cycles=%0d shared_span=%0d min_gap=%0d max_gap=%0d first_latency=%0d latency_sum=%0d peak_inflight=%0d reads=%0d writes=%0d command_wait=%0d response_wait=%0d slave_wait=%0d same_edge_write_acks=%0d slave_response_wait=%0d held_checks=%0d",
       mode,mixed,stall,rsp_stall,zero_write,WORDS,cycle-start_cycle,last_shared-first_shared,min_gap,max_gap,first_latency,latency_sum,inflight_peak,read_words,write_words,cmd_wait,rsp_wait,shared_wait,same_edge_write_acks,slave_rsp_wait,held_checks);
     $finish;
    end
   end
  end
 end
 initial begin
  if($value$plusargs("MODE=%d",mode))begin end
  if($value$plusargs("MIXED=%d",mixed))begin end
  if($value$plusargs("STALL=%d",stall))begin end
  if($value$plusargs("RSP_STALL=%d",rsp_stall))begin end
  if($value$plusargs("ZERO_WRITE=%d",zero_write))begin end
  if(mode<0||mode>1||mixed<0||mixed>2||stall<0||stall>1||rsp_stall<0||rsp_stall>1||zero_write<0||zero_write>1)$fatal(1,"invalid benchmark options");
  repeat(5)@(negedge clk);rst_n=1;
 end
 initial begin #1000000;$fatal(1,"fabric bandwidth timeout");end
endmodule
