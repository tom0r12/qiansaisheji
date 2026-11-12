`timescale 1ns/1ps
// Independent transaction-level scoreboard. The target returns in order;
// sources contend in arbitrary order and may queue new work behind old work.
module tb_icb_merge_queue;
 parameter integer NP=6, DEPTH=4;
 parameter [NP-1:0] MASK={NP{1'b1}};
 reg clk=0, rst_n=0;
 always #5 clk=~clk;
 reg [NP-1:0] sv=0, sr=0, ready=0;
 wire [NP-1:0] sc, rv, err;
 reg [32*NP-1:0] addr=0, data=0;
 reg [4*NP-1:0] mask=0;
 wire [32*NP-1:0] rdata;
 wire mv,mr,mrr;
 reg mc=0,mrv=0,me=0;
 wire [31:0] ma,md;
 wire [3:0] mm;
 reg [31:0] mrd=0;
 qingyu_icb_merge #(.NP(NP),.OUTSTANDING(DEPTH),.ONE_PER_PORT(MASK)) dut(
  .clk(clk),.rst_n(rst_n),
  .s_cmd_valid(sv),.s_cmd_ready(sc),.s_cmd_read(sr),.s_cmd_addr(addr),
  .s_cmd_wdata(data),.s_cmd_wmask(mask),.s_rsp_valid(rv),.s_rsp_ready(ready),
  .s_rsp_err(err),.s_rsp_rdata(rdata),
  .m_cmd_valid(mv),.m_cmd_ready(mc),.m_cmd_read(mr),.m_cmd_addr(ma),
  .m_cmd_wdata(md),.m_cmd_wmask(mm),.m_rsp_valid(mrv),.m_rsp_ready(mrr),
  .m_rsp_err(me),.m_rsp_rdata(mrd));
 integer pending[0:NP-1], sequence_id[0:NP-1], received[0:NP-1], age[0:NP-1];
 integer owner[0:4095];
 reg [31:0] expected[0:4095], target[0:4095];
 reg expected_err[0:4095], target_err[0:4095];
 integer head=0,tail=0,count=0,mode=0,cycles=0,total=0,errors=0;
 integer stalls=0,rsp_stalls=0,full_cycles=0,replacements=0,resets=0,max_count=0;
 integer i,j,chosen,accepted,old_count,seed,rng_seed,unused;
 reg [NP-1:0] accepted_last=0;
 reg response_last=0, held=0;
 reg [68:0] held_payload;
 function automatic [31:0] answer(input [31:0] a,input [31:0] d,input r,input [3:0] w);
  answer=(a^32'h73d1ab90)+(r ? 32'h12345678 : d^{28'b0,w});
 endfunction
 task clear_epoch;
  begin
   sv=0;sr=0;ready=0;addr=0;data=0;mask=0;mc=0;mrv=0;me=0;mrd=0;
   head=0;tail=0;count=0;held=0;accepted_last=0;response_last=0;
   for(j=0;j<NP;j=j+1)begin pending[j]=0;sequence_id[j]=0;age[j]=0;end
  end
 endtask
 task reset_epoch;
  begin
   @(negedge clk);mode=0;rst_n=0;clear_epoch();resets++;
   repeat(3)@(negedge clk);
   if(mv||(|rv)||mrr||(|sc))$fatal(1,"handshake leaked through reset");
   rst_n=1;
  end
 endtask
 initial begin
  if(!$value$plusargs("SEED=%d",seed))seed=17;
  rng_seed=seed;unused=$urandom(rng_seed);clear_epoch();
  for(j=0;j<NP;j=j+1)received[j]=0;
  repeat(3)@(negedge clk);rst_n=1;
  // A command which is presented but never accepted must be discarded by reset.
  sv[NP-1]=1;addr[32*(NP-1)+:32]=32'habc0;mask[4*(NP-1)+:4]=15;mc=0;
  repeat(4)@(negedge clk);
  if(!mv)$fatal(1,"directed command did not reach output");
  reset_epoch();
  // Reset with a full owner FIFO and a held error/data response.
  mode=1;wait(count==DEPTH);
  @(negedge clk);mode=2;
  repeat(5)@(negedge clk);
  if(!mrv||mrr||!(|rv))$fatal(1,"held response case missing");
  reset_epoch();
  // Full+pop+push must work on the same edge, including same-source replacement.
  mode=1;wait(count==DEPTH);
  @(negedge clk);mode=5;
  wait(replacements!=0);
  @(negedge clk);mode=3;
  wait(total>=1500);
  @(negedge clk);mode=4;
  wait(count==0 && sv==0 && !mrv);
  repeat(4)@(negedge clk);
  for(i=0;i<NP;i=i+1)
   if(received[i]<50)$fatal(1,"master starved %0d received=%0d",i,received[i]);
  if(errors<50||stalls==0||rsp_stalls==0||full_cycles==0||replacements==0||resets!=2||max_count!=DEPTH)
   $fatal(1,"missing stress coverage");
  $display("PASS queue NP=%0d DEPTH=%0d MASK=%0h seed=%0d responses=%0d errors=%0d command_stalls=%0d response_stalls=%0d full_cycles=%0d replacements=%0d resets=%0d max_depth=%0d",
   NP,DEPTH,MASK,seed,total,errors,stalls,rsp_stalls,full_cycles,replacements,resets,max_count);
  $finish;
 end
 always @(negedge clk) if(rst_n && mode!=0) begin
  mc=(mode==2) ? 0 : mode==3 ? ($urandom_range(0,3)!=0) : 1;
  for(i=0;i<NP;i=i+1)begin
   ready[i]=(mode==2) ? 0 : mode==3 ? ($urandom_range(0,3)!=0) : 1;
   if(!sv[i] || accepted_last[i]) begin
    sv[i]=0;
    if(mode!=4 && (mode!=3 || $urandom_range(0,3)!=0)) begin
     sequence_id[i]++;
     sv[i]=1;sr[i]=$urandom_range(0,1);
     addr[32*i+:32]=32'h100000+(i<<16)+sequence_id[i]*4;
     data[32*i+:32]=32'hab000000^(i<<20)^sequence_id[i];
     mask[4*i+:4]=$urandom_range(1,15);
    end
   end
  end
  accepted_last=0;
  if(response_last) mrv=0;
  response_last=0;
  if(mode==1) mrv=0;
  else if(!mrv && count!=0 && (mode!=3 || $urandom_range(0,3)!=0)) begin
   mrv=1;mrd=target[head];me=target_err[head];
  end
 end
 always @(posedge clk) begin
  cycles++;
  if(cycles>60000)$fatal(1,"queue timeout mode=%0d count=%0d",mode,count);
  if(rst_n && mode!=0) begin
   old_count=count;
   if(held && (!mv || {mr,ma,md,mm}!==held_payload))$fatal(1,"blocked command changed");
   held=mv&&!mc;held_payload={mr,ma,md,mm};
   if(held)stalls++;
   if(mrv&&!mrr)rsp_stalls++;
   if(count==DEPTH)full_cycles++;
   if(mrv) begin
    if(count==0)$fatal(1,"target responded without request");
    if(rv!==( {{(NP-1){1'b0}},1'b1} << owner[head]))$fatal(1,"response routed to wrong source");
    if(rdata[32*owner[head]+:32]!==expected[head] || err[owner[head]]!==expected_err[head])
     $fatal(1,"response data/error mismatch");
    if(mrr!==ready[owner[head]])$fatal(1,"wrong response ready owner");
   end else if(|rv)$fatal(1,"unsolicited source response");
   if(mrv&&mrr)begin
    pending[owner[head]]--;received[owner[head]]++;total++;if(me)errors++;
    head++;count--;response_last=1;
   end
   accepted=0;chosen=-1;
   for(i=0;i<NP;i=i+1)if(sv[i]&&sc[i])begin accepted++;chosen=i;end
   if((mv&&mc)!==(accepted!=0) || accepted>1)$fatal(1,"accept handshake mismatch");
   if(mv&&mc)begin
    if({mr,ma,md,mm}!=={sr[chosen],addr[32*chosen+:32],data[32*chosen+:32],mask[4*chosen+:4]})
     $fatal(1,"command payload mismatch");
    if(MASK[chosen] && pending[chosen]!=0)$fatal(1,"one-per-source credit exceeded");
    owner[tail]=chosen;
    expected[tail]=answer(addr[32*chosen+:32],data[32*chosen+:32],sr[chosen],mask[4*chosen+:4]);
    expected_err[tail]=addr[32*chosen+4];
    target[tail]=answer(ma,md,mr,mm);target_err[tail]=ma[4];
    tail++;count++;pending[chosen]++;accepted_last[chosen]=1;
    if(old_count==DEPTH && mrv&&mrr)replacements++;
    for(i=0;i<NP;i=i+1)begin
     if(i==chosen || !sv[i] || (MASK[i]&&pending[i]!=0)) age[i]=0;
     else begin age[i]++;if(age[i]>NP+1)$fatal(1,"round-robin unfair for source %0d",i);end
    end
   end
   if(count>DEPTH||count<0)$fatal(1,"owner queue capacity exceeded");
   if(count>max_count)max_count=count;
  end
 end
endmodule
