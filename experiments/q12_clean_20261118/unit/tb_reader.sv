`timescale 1ns/1ps
// Unit test: q12_fixed12_reader (X signed12 + W signed10 modes), random input
// gaps and output backpressure, bad length/last error paths.
module tb_reader;
 reg clk=0; always #5 clk=~clk;
 reg rst_n=0, sv=0, iv=0, il=0, ordy=1; reg [15:0] ssym=0; reg [31:0] sbits=0, idata=0; reg [5:0] ibits=32;
 wire srdy, irdy, ov, olast, busy, done, error; wire [47:0] od; wire [2:0] oc; wire [31:0] tc, cb;
 q12_fixed12_reader dut(.clk(clk),.rst_n(rst_n),.start_valid(sv),.start_ready(srdy),.start_symbols(ssym),.start_encoded_bits(sbits),
  .in_valid(iv),.in_ready(irdy),.in_data(idata),.in_valid_bits(ibits),.in_last(il),.out_valid(ov),.out_ready(ordy),.out_data(od),
  .out_count(oc),.out_last(olast),.busy(busy),.done(done),.error(error),.total_cycles(tc),.consumed_bits(cb));
 integer seed=1, nwords, nsym, width, i, got, k;
 reg [31:0] words [0:4095]; integer vals [0:8191];
 task automatic make(input integer n, input integer w);
  reg [63:0] acc; integer bits, wi, v;
  begin
   nsym=n; width=w; acc=0; bits=0; wi=0;
   for(i=0;i<n;i=i+1)begin
    v=$random(seed) % (1<<(w-1)); vals[i]=v;
    acc=acc|((64'(v)&((64'd1<<w)-1))<<bits); bits=bits+w;
    if(bits>=32)begin words[wi]=acc[31:0]; wi=wi+1; acc=acc>>32; bits=bits-32; end
   end
   nwords=wi; if(bits!=0) $fatal(1,"not word aligned");
  end
 endtask
 task automatic run_segment(input integer n, input integer w);
  integer sent;
  begin
   make(n,w);
   @(negedge clk); sv=1; ssym=16'(n); sbits=32'(n*w); @(posedge clk); while(!srdy) @(posedge clk); @(negedge clk); sv=0;
   sent=0; got=0;
   fork
    begin
     while(sent<nwords)begin
      @(negedge clk); iv=($random(seed)%4)!=0; idata=words[sent]; il=(sent==nwords-1); ibits=32;
      @(posedge clk); if(iv&&irdy) sent=sent+1;
     end
     @(negedge clk); iv=0; il=0;
    end
    begin
     while(got<n)begin
      @(negedge clk); ordy=($random(seed)%3)!=0;
      @(posedge clk);
      if(ov&&ordy)begin
       if(oc!=2) $fatal(1,"count");
       for(k=0;k<2;k=k+1) if($signed(od[12*k+:12])!==vals[got+k]) $fatal(1,"value mismatch at %0d w=%0d got=%0d exp=%0d",got+k,w,$signed(od[12*k+:12]),vals[got+k]);
       if(od[47:24]!=0) $fatal(1,"high bits");
       if(olast!==(got+2==n)) $fatal(1,"last flag");
       got=got+2;
      end
     end
    end
   join
   repeat(3) @(posedge clk); if(busy||error) $fatal(1,"not done cleanly");
  end
 endtask
 initial begin
  repeat(3) @(posedge clk); rst_n=1;
  run_segment(6336,12); run_segment(2048,10); run_segment(2048,10); run_segment(6336,12);
  // bad configuration -> immediate error/done
  @(negedge clk); sv=1; ssym=2048; sbits=24576; @(posedge clk); @(negedge clk); sv=0; @(posedge clk); #1;
  if(!error || busy) $fatal(1,"bad start not rejected");
  // early last -> error
  make(2048,10);
  @(negedge clk); sv=1; ssym=2048; sbits=20480; @(posedge clk); @(negedge clk); sv=0;
  @(negedge clk); iv=1; idata=words[0]; il=1; @(posedge clk); @(negedge clk); iv=0; il=0; @(posedge clk); #1;
  if(!error || busy) $fatal(1,"early last not rejected");
  $display("PASS FIXED_READER x12 w10 random_gaps backpressure last_flags bad_start early_last");
  $finish;
 end
 initial begin #50000000; $fatal(1,"timeout"); end
endmodule
