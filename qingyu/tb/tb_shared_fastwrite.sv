`timescale 1ns/1ps
module tb_shared_fastwrite;
 reg clk=0;
 always #5 clk=~clk;
 reg rst_n=0, cv=0, cr=0, rr=0;
 reg [31:0] ca=0,cw=0;
 reg [3:0] cm=0;
 wire cy,rv,re;
 wire [31:0] rd;
 qingyu_shared_sram dut(clk,rst_n,cv,cy,cr,ca,cw,cm,rv,rr,rd,re);
 reg [31:0] reference [0:131071];
 reg [31:0] expected_data [0:32767];
 reg expected_error [0:32767];
 integer head=0,tail=0,commands=0,responses=0,writes=0,reads=0,errors=0;
 integer zero_writes=0,stalled=0,resets=0,byte_index,addr_index;
 reg held=0,held_err;
 reg [31:0] held_data;
 wire good=ca[31:19]==13'h1400;
 always @(posedge clk) begin
  if (!rst_n) begin
   if(cy || rv) $fatal(1,"handshake while reset");
   head=0;tail=0;held=0;
  end else begin
   if(held && (!rv || rd!==held_data || re!==held_err))
    $fatal(1,"response changed while stalled");
   if(cv && cy) begin
    addr_index=ca[18:2];
    expected_error[tail]=!good;
    expected_data[tail]=(cr && good)?reference[addr_index]:32'b0;
    tail=tail+1; commands=commands+1;
    if(tail>=32768) $fatal(1,"scoreboard capacity");
    if(cr) reads=reads+1;
    else begin
     writes=writes+1;
     if(rv && rr) zero_writes=zero_writes+1;
     else $fatal(1,"write accepted without same-edge response");
     if(good) for(byte_index=0;byte_index<4;byte_index=byte_index+1)
      if(cm[byte_index]) reference[addr_index][byte_index*8+:8]=cw[byte_index*8+:8];
    end
   end
   if(rv && rr) begin
    if(head>=tail) $fatal(1,"response without accepted command");
    if(re!==expected_error[head] || rd!==expected_data[head])
     $fatal(1,"response mismatch at %0d got %h/%b expected %h/%b",head,rd,re,expected_data[head],expected_error[head]);
    errors=errors+int'(re); head=head+1; responses=responses+1;
   end
   held=rv && !rr;
   if(held) begin held_data=rd;held_err=re;stalled=stalled+1;end
  end
 end
 function automatic [31:0] address(input integer i);
  address=32'ha0000000+((i%32)*4096+(i/32)*32)*4;
 endfunction
 task automatic transaction(input bit read_cmd,input [31:0] a,input [31:0] data,input [3:0] mask,input integer delay_cycles);
  integer n;
  reg accepted,done;
  begin
   @(negedge clk);cv=1;cr=read_cmd;ca=a;cw=data;cm=mask;rr=0;
   accepted=0;done=0;n=0;
   while(!done) begin
    rr=n>=delay_cycles;
    @(posedge clk);
    if(cv && cy) accepted=1;
    if(rv && rr) begin
     if(!accepted) $fatal(1,"early response in driver");
     done=1;
    end
    @(negedge clk);
    if(accepted)cv=0;
    n=n+1;
    if(n>100) $fatal(1,"transaction timeout");
   end
   cv=0;rr=0;
  end
 endtask
 task automatic reset_protocol;
  begin
   @(negedge clk);rst_n=0;cv=0;rr=0;
   repeat(2)@(negedge clk);
   rst_n=1;resets=resets+1;
  end
 endtask
 integer i,j,seed=1717,dummy,before_writes;
 reg [31:0] value;
 initial begin
  dummy=$value$plusargs("SEED=%d",seed);dummy=$urandom(seed);
  reset_protocol();
  // Cover every physical bank, boundary offsets, and all four byte lanes.
  for(i=0;i<128;i=i+1)transaction(0,address(i),32'hace00000^i,15,0);
  for(j=0;j<16;j=j+1)for(i=0;i<128;i=i+1)begin
   value=$urandom;
   transaction(0,address(i),value,4'(j),$urandom_range(0,7));
   transaction(1,address(i),0,0,$urandom_range(0,7));
  end
  for(i=0;i<64;i=i+1)begin
   transaction(0,32'hb0000000+i*4,$urandom,15,$urandom_range(0,5));
   transaction(1,32'hb0000000+i*4,0,0,$urandom_range(0,5));
  end
  // Held write followed by reset must never modify its SRAM word.
  @(negedge clk);cv=1;cr=0;ca=address(7);cw=32'hdeadbeef;cm=15;rr=0;
  repeat(8)begin @(posedge clk);if(cy)$fatal(1,"stalled write accepted");end
  reset_protocol();transaction(1,address(7),0,0,3);
  // Accepted read can be discarded only by reset; SRAM contents survive.
  @(negedge clk);cv=1;cr=1;ca=address(9);rr=0;
  @(posedge clk);if(!cy)$fatal(1,"read was not accepted");
  @(negedge clk);cv=0;
  repeat(8)@(posedge clk);
  reset_protocol();transaction(1,address(9),0,0,0);
  // 1024 consecutive writes must be accepted one per edge at the slave.
  before_writes=writes;
  for(i=0;i<1024;i=i+1)begin
   @(negedge clk);cv=1;cr=0;ca=address(i%128);cw=32'h67000000^i;cm=15;rr=1;
   @(posedge clk);if(!cy || !rv)$fatal(1,"write burst bubble");
  end
  @(negedge clk);cv=0;rr=0;
  if(writes-before_writes!=1024)$fatal(1,"burst count");
  for(i=0;i<128;i=i+1)transaction(1,address(i),0,0,$urandom_range(0,5));
  if(head!=tail || zero_writes!=writes || errors!=128 || stalled==0 || resets!=3)
   $fatal(1,"coverage/count mismatch");
  $display("PASS shared_fastwrite commands=%0d responses=%0d writes=%0d reads=%0d errors=%0d zero_writes=%0d stalled=%0d resets=%0d",commands,responses,writes,reads,errors,zero_writes,stalled,resets);
  $finish;
 end
 initial begin #3000000;$fatal(1,"global timeout");end
endmodule
