`timescale 1ns/1ps
`default_nettype none
module tb_shared_readcache_wrapper;
 reg clk=0; always #5 clk=~clk;
 reg rst_n=0,cache_clear=0,icb_cmd_valid=0,icb_cmd_read=1,icb_rsp_ready=0;
 reg [31:0] icb_cmd_addr=0,icb_cmd_wdata=0;
 reg [3:0] icb_cmd_wmask=0;
 wire icb_cmd_ready,icb_rsp_valid,icb_rsp_err;
 wire [31:0] icb_rsp_rdata;
 qingyu_shared_sram dut(.*);
 reg [31:0] golden[0:131071];
 reg initialized[0:131071];
 reg pending=0,expected_error=0,held=0;
 reg [31:0] expected_data=0;
 reg [32:0] held_payload;
 integer commands=0,responses=0,aborted=0,reads=0,writes=0,invalids=0;
 integer held_cycles=0,clears=0,cycles=0,ram_reads=0,ram_writes=0;
 integer masks_seen=0,offsets_seen=0;
 reg [31:0] banks_seen=0,rng=1;
 integer seed=17,b;
 reg good,accept;
 function automatic [31:0] random32;
  reg [31:0] v;
  begin v=rng;v=v^(v<<13);v=v^(v>>17);v=v^(v<<5);rng=v;random32=v;end
 endfunction
 always @(posedge clk) begin
  cycles=cycles+1;
  if(cycles>200000)$fatal(1,"watchdog");
  good=icb_cmd_addr>=32'ha0000000 && icb_cmd_addr<=32'ha007ffff;
  accept=icb_cmd_valid && icb_cmd_ready;
  if(dut.ram_cs)begin
   if(!rst_n || cache_clear)$fatal(1,"RAM activity on clear/reset");
   if(dut.ram_we)begin
    ram_writes=ram_writes+1;
    if(!accept || icb_cmd_read || !good || dut.ram_addr!==icb_cmd_addr[18:2] ||
       dut.ram_wdata!==icb_cmd_wdata || dut.ram_wmask!==icb_cmd_wmask)
     $fatal(1,"unowned/mismatched macro write");
   end else ram_reads=ram_reads+1;
  end
  if(!rst_n)begin
   if(icb_cmd_ready || icb_rsp_valid)$fatal(1,"handshake during reset");
   if(pending)aborted=aborted+1;
   pending=0;held=0;
  end else begin
   if(cache_clear)begin clears=clears+1;if(icb_cmd_ready)$fatal(1,"accepted on clear");end
   if(held)begin
    held_cycles=held_cycles+1;
    if(!icb_rsp_valid || {icb_rsp_err,icb_rsp_rdata}!==held_payload)
     $fatal(1,"held response changed");
   end
   if(accept)begin
    if(pending)$fatal(1,"overlapping pending command");
    commands=commands+1;pending=1;expected_error=!good;expected_data=0;
    if(good)begin
     banks_seen[icb_cmd_addr[18:14]]=1;
     offsets_seen=offsets_seen|(1<<icb_cmd_addr[1:0]);
     if(icb_cmd_read)begin
      if(!initialized[icb_cmd_addr[18:2]])$fatal(1,"TB read uninitialized word");
      expected_data=golden[icb_cmd_addr[18:2]];reads=reads+1;
     end else begin
      if(!(dut.ram_cs && dut.ram_we))$fatal(1,"write not committed at acceptance");
      if(!initialized[icb_cmd_addr[18:2]] && icb_cmd_wmask!=15)$fatal(1,"partial initial write");
      initialized[icb_cmd_addr[18:2]]=1;writes=writes+1;
      masks_seen=masks_seen|(1<<icb_cmd_wmask);
      for(b=0;b<4;b=b+1)if(icb_cmd_wmask[b])golden[icb_cmd_addr[18:2]][8*b+:8]=icb_cmd_wdata[8*b+:8];
     end
    end else begin invalids=invalids+1;if(dut.ram_cs)$fatal(1,"invalid accessed macro");end
   end
   if(icb_rsp_valid)begin
    if(!pending)$fatal(1,"unsolicited response");
    if(icb_rsp_err!==expected_error || icb_rsp_rdata!==expected_data)
     $fatal(1,"response mismatch cmd=%0d addr=%h got=%h/%b expected=%h/%b",commands,icb_cmd_addr,icb_rsp_rdata,icb_rsp_err,expected_data,expected_error);
    if(icb_rsp_ready)begin pending=0;responses=responses+1;end
   end
   held=icb_rsp_valid&&!icb_rsp_ready;held_payload={icb_rsp_err,icb_rsp_rdata};
  end
 end
 task automatic clear_cache;
  begin @(negedge clk);cache_clear=1;@(negedge clk);cache_clear=0;end
 endtask
 task automatic transfer(input reg rd,input reg[31:0]a,d,input reg[3:0]m,input integer stalls,clear_at);
  integer wanted,j,t;
  reg taken;
  begin
   wanted=responses+1;t=0;taken=0;
   @(negedge clk);icb_cmd_valid=1;icb_cmd_read=rd;icb_cmd_addr=a;icb_cmd_wdata=d;
   icb_cmd_wmask=m;icb_rsp_ready=stalls==0;cache_clear=0;
   while(!taken)begin @(posedge clk);taken=icb_cmd_ready;#1;t=t+1;if(t>16)$fatal(1,"cmd timeout");end
   @(negedge clk);icb_cmd_valid=0;
   for(j=0;j<stalls;j=j+1)begin cache_clear=j==clear_at;@(negedge clk);end
   cache_clear=0;icb_rsp_ready=1;t=0;
   while(responses<wanted)begin @(posedge clk);#1;t=t+1;if(t>16)$fatal(1,"rsp timeout");end
   @(negedge clk);
  end
 endtask
 task automatic stream;
  integer sent,wanted,t,last_tick;
  reg taken;
  begin
   clear_cache();sent=0;wanted=responses+1024;t=0;last_tick=-1;
   @(negedge clk);icb_cmd_valid=1;icb_cmd_read=1;icb_cmd_addr=32'ha003f800;icb_rsp_ready=1;
   while(sent<1024)begin
    @(posedge clk);taken=icb_cmd_ready;#1;t=t+1;
    if(taken)begin
     if(sent>=2 && t-last_tick!=1)$fatal(1,"sequential II across bank boundary");
     sent=sent+1;last_tick=t;
    end
    if(t>1100)$fatal(1,"stream timeout");
    @(negedge clk);icb_cmd_addr=32'ha003f800+4*sent+(sent%4);icb_cmd_valid=sent<1024;
   end
   while(responses<wanted)begin @(posedge clk);#1;end
  end
 endtask
 integer i,j,k,idx;
 reg[31:0]v,a;
 initial begin
  if(!$value$plusargs("SEED=%d",seed))seed=17;
  rng=seed==0?1:seed;
  for(i=0;i<131072;i=i+1)initialized[i]=0;
  repeat(3)@(negedge clk);rst_n=1;icb_rsp_ready=1;
  // Initialize through real commands only: first/last 16 words of every bank.
  for(i=0;i<32;i=i+1)for(j=0;j<32;j=j+1)begin
   idx=i*4096+(j<16?j:4096-32+j);
   transfer(0,32'ha0000000+4*idx,32'h7139ab42^(idx*32'h10204081),15,0,-1);
  end
  for(i=0;i<1025;i=i+1)transfer(0,32'ha003f800+4*i,random32(),15,0,-1);
  // Every mask, byte address alias and bank; writes poison local macro Q.
  for(i=0;i<32;i=i+1)for(j=0;j<16;j=j+1)begin
   a=32'ha0000000+16384*i+4*j+(j%4);
   transfer(1,a,0,0,0,-1);
   transfer(0,a,random32(),j,6,j%6);
   transfer(1,a,0,0,6,2);
  end
  stream();
  transfer(1,32'h9fffffff,0,0,8,1);
  transfer(0,32'ha0080003,32'hdeadbeef,15,8,1);
  for(i=0;i<4;i=i+1)transfer(1,32'ha007fffc+i,0,0,0,-1);
  // Reset an accepted write with its response held; committed bytes survive.
  clear_cache();
  @(negedge clk);icb_cmd_valid=1;icb_cmd_read=0;icb_cmd_addr=32'ha0000003;
  icb_cmd_wdata=32'hdead1234;icb_cmd_wmask=5;icb_rsp_ready=0;
  @(posedge clk);if(!icb_cmd_ready)$fatal(1,"reset setup");#1;
  @(negedge clk);rst_n=0;icb_cmd_valid=0;repeat(2)@(negedge clk);rst_n=1;icb_rsp_ready=1;
  transfer(1,32'ha0000000,0,0,0,-1);
  for(i=0;i<1600;i=i+1)begin
   v=random32();idx=(v[4:0]*4096)+(v[9:5]<16?v[9:5]:4096-32+v[9:5]);
   a=32'ha0000000+4*idx+v[11:10];
   transfer(v[12],a,random32(),v[16:13],v[20:17],v[24:21]);
  end
  // Cold readback via bus checks every touched word, including zero masks.
  clear_cache();
  for(i=0;i<131072;i=i+1)if(initialized[i])transfer(1,32'ha0000000+4*i,0,0,0,-1);
  if(pending || commands!=responses+aborted || aborted!=1)$fatal(1,"final response accounting");
  if(banks_seen!==32'hffffffff || masks_seen!=65535 || offsets_seen!=15)$fatal(1,"coverage missing");
  if(writes!=ram_writes)$fatal(1,"physical write accounting");
  $display("PASS shared_readcache_wrapper seed=%0d commands=%0d responses=%0d aborted=%0d reads=%0d writes=%0d invalid=%0d ram_reads=%0d ram_writes=%0d held_cycles=%0d clears=%0d banks=32 masks=16 offsets=4",seed,commands,responses,aborted,reads,writes,invalids,ram_reads,ram_writes,held_cycles,clears);
  $finish;
 end
endmodule
`default_nettype wire
