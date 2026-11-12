`timescale 1ns/1ps
module tb_icb_merge;
 localparam NP=6;
 reg clk=0,rst_n=0;always #5 clk=~clk;
 reg [NP-1:0] sv=0,sr=0,sready=0;
 wire [NP-1:0] sc,srv,se;
 reg [32*NP-1:0] sa=0,sd=0;reg [4*NP-1:0] sm=0;
 wire [32*NP-1:0] rd;
 wire mv,mr,mrr;reg mc=0,mrv=0,me=0;wire [31:0] ma,md;wire [3:0] mm;reg [31:0] mrd=0;
 qingyu_icb_merge #(.NP(NP)) dut(.clk(clk),.rst_n(rst_n),
  .s_cmd_valid(sv),.s_cmd_ready(sc),.s_cmd_read(sr),.s_cmd_addr(sa),.s_cmd_wdata(sd),.s_cmd_wmask(sm),
  .s_rsp_valid(srv),.s_rsp_ready(sready),.s_rsp_err(se),.s_rsp_rdata(rd),
  .m_cmd_valid(mv),.m_cmd_ready(mc),.m_cmd_read(mr),.m_cmd_addr(ma),.m_cmd_wdata(md),.m_cmd_wmask(mm),
  .m_rsp_valid(mrv),.m_rsp_ready(mrr),.m_rsp_err(me),.m_rsp_rdata(mrd));
 integer state[0:NP-1],sequence_id[0:NP-1],received[0:NP-1],age[0:NP-1];
 reg [31:0] expected[0:NP-1];reg expected_err[0:NP-1];
 reg target_pending=0;integer latency=0;
 reg [31:0] target_data;reg target_err;
 integer cycle=0,total=0,errors=0,stalls=0,rsp_stalls=0,resets=0;
 integer i,j,chosen,count,seed,rng_seed,unused;
 reg running=0;
 reg held=0;reg [68:0] held_payload;
 reg rsp_held=0;reg [32:0] held_response;
 function automatic [31:0] response(input [31:0] a,input [31:0] d,input r,input [3:0] mask);
  response=(a^32'h7ac91e03)+(r ? 32'h12345678 : d^{28'b0,mask});
 endfunction
 task clear_epoch;
  begin
   sv=0;sr=0;sready=0;sa=0;sd=0;sm=0;mc=0;mrv=0;me=0;mrd=0;
   target_pending=0;latency=0;held=0;rsp_held=0;
   for(j=0;j<NP;j=j+1)begin state[j]=0;sequence_id[j]=0;received[j]=0;age[j]=0;end
  end
 endtask
 initial begin
  if(!$value$plusargs("SEED=%d",seed))seed=17;
  rng_seed=seed;unused=$urandom(rng_seed);clear_epoch();
  repeat(4)@(negedge clk);rst_n=1;running=1;
  // Reset with a held command, then with a response under backpressure.
  @(negedge clk);running=0;mc=0;sv=6'b100000;sa[160+:32]=32'h120;sd[160+:32]=32'h321;sm[20+:4]=15;
  repeat(4)@(negedge clk);
  rst_n=0;clear_epoch();resets++;
  repeat(3)@(negedge clk);
  if(mv||(|srv))$fatal(1,"command/response leaked across reset");
  rst_n=1;mc=1;sv=1;sa[0+:32]=32'h40;sm[0+:4]=15;
  @(posedge clk);while(!(mv&&mc))@(posedge clk);
  @(negedge clk);sv=0;mrv=1;mrd=32'h1234;me=1;sready=0;
  repeat(3)@(negedge clk);
  if(srv!=1||!se[0]||rd[0+:32]!=32'h1234)$fatal(1,"directed response routing failed");
  rst_n=0;clear_epoch();resets++;
  repeat(3)@(negedge clk);rst_n=1;running=1;
  wait(total>=1200);
  @(negedge clk);running=0;
  // Let all accepted/held transactions complete without new requests.
  repeat(200)begin
   @(negedge clk);mc=1;sready='1;
   for(i=0;i<NP;i=i+1)if(state[i]!=1)sv[i]=0;
  end
  for(i=0;i<NP;i=i+1)if(received[i]<80)$fatal(1,"starved master %0d received=%0d",i,received[i]);
  if(errors<50||stalls==0||rsp_stalls==0||resets!=2)$fatal(1,"missing stress coverage");
  $display("PASS ICB merge seed=%0d responses=%0d errors=%0d command_stalls=%0d response_stalls=%0d reset_cases=%0d",seed,total,errors,stalls,rsp_stalls,resets);
  $finish;
 end
 always @(negedge clk)if(rst_n&&running)begin
  mc=($urandom_range(0,3)!=0);
  for(i=0;i<NP;i=i+1)begin
   sready[i]=($urandom_range(0,3)!=0);
   if(state[i]==0&&$urandom_range(0,3)!=0)begin
    sequence_id[i]++;state[i]=1;
    sa[32*i+:32]=32'h10000+i*32'h1000+sequence_id[i]*4;
    sd[32*i+:32]=32'hbadd0000^(i<<16)^sequence_id[i];
    sm[4*i+:4]=$urandom_range(1,15);sr[i]=$urandom_range(0,1);sv[i]=1;
   end else if(state[i]!=1)sv[i]=0;
  end
 end
 always @(posedge clk)begin
  cycle++;
  if(cycle>50000)$fatal(1,"merge regression timeout");
  if(rst_n&&running)begin
   if(held&&(!mv||{mr,ma,md,mm}!==held_payload))$fatal(1,"command changed while downstream stalled");
   held=mv&&!mc;held_payload={mr,ma,md,mm};
   if(held)stalls++;
   if(rsp_held&&(!mrv||{me,mrd}!==held_response))$fatal(1,"target response changed under stall");
   rsp_held=mrv&&!mrr;held_response={me,mrd};
   if(rsp_held)rsp_stalls++;
  end
  if(rst_n&&(running||total>=1200))begin
   for(i=0;i<NP;i=i+1)if(srv[i]&&sready[i])begin
    if(state[i]!=2)$fatal(1,"response to master without pending request %0d",i);
    if(rd[32*i+:32]!==expected[i]||se[i]!==expected_err[i])$fatal(1,"response data/error corrupted for master %0d",i);
    received[i]++;total++;if(se[i])errors++;state[i]=0;
   end
   if(mrv&&mrr)begin target_pending=0;mrv<=0;end
   if(mv&&mc)begin
    if(target_pending)$fatal(1,"multiple outstanding downstream requests");
    count=0;chosen=-1;
    for(i=0;i<NP;i=i+1)if(sv[i]&&sc[i])begin count++;chosen=i;end
    if(count!=1)$fatal(1,"downstream command has ambiguous owner");
    if(state[chosen]!=1||{mr,ma,md,mm}!=={sr[chosen],sa[32*chosen+:32],sd[32*chosen+:32],sm[4*chosen+:4]})$fatal(1,"command corrupted or duplicated");
    expected[chosen]=response(ma,md,mr,mm);expected_err[chosen]=ma[4];state[chosen]=2;
    for(i=0;i<NP;i=i+1)begin
     if(i==chosen)age[i]=0;
     else if(state[i]==1)begin age[i]++;if(age[i]>NP+1)$fatal(1,"unfair arbitration master %0d",i);end
    end
    target_pending=1;target_data=response(ma,md,mr,mm);target_err=ma[4];latency=$urandom_range(1,5);
   end else if(target_pending&&!mrv)begin
    if(latency==0)begin mrv<=1;mrd<=target_data;me<=target_err;end
    else latency--;
   end
  end
 end
endmodule
