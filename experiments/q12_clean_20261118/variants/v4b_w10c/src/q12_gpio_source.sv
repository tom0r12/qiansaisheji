`timescale 1ns/1ps
// External bounded-burst source. ONLY physical REQ/count/OE pins enter it.
// Data rate is an explicit independent time parameter, not an internal bus event.
// A burst has at most 16 actual 32-bit words; no shared memory side effects.
module q12_gpio_source #(parameter integer WORDS=8873)(
 input wire req,input wire[7:0]count,input wire[8:0]oe,
 output reg[31:0]data,output reg ready,
 output integer presented_words,requested_words,burst_requests,
 output reg[63:0]first_data_ps,last_data_ps
);
 reg[31:0]image[0:WORDS-1];reg[1023:0]input_path;
 integer input_words,k,n;reg previous_req,transmitting=0;
 real period_ns=26.664,access_ns=1.0;
 initial begin
  data=0;ready=0;presented_words=0;requested_words=0;burst_requests=0;first_data_ps=0;last_data_ps=0;
  if($value$plusargs("GPIO_PERIOD_NS=%f",period_ns))begin end
  if($value$plusargs("GPIO_ACCESS_NS=%f",access_ns))begin end
  if(!$value$plusargs("INPUT=%s",input_path))$fatal(1,"GPIO missing INPUT");
  if(!$value$plusargs("INPUT_WORDS=%d",input_words))$fatal(1,"GPIO missing INPUT_WORDS");
  if(input_words<1||input_words>WORDS)$fatal(1,"GPIO capacity exceeded");
  for(k=0;k<input_words;k++)image[k]=32'bx;
  $readmemh(input_path,image,0,input_words-1);
  for(k=0;k<input_words;k++)if(^image[k]===1'bx)$fatal(1,"GPIO incomplete image");
  wait(oe===9'h1ff);
  if(req!==0)$fatal(1,"GPIO request must start low");
  ready=1;
  forever begin
   @(req);
   n=int'(count);previous_req=req;
   if(n<1||n>255||requested_words+n>input_words||oe!==9'h1ff)$fatal(1,"GPIO invalid burst");
   requested_words+=n;burst_requests++;transmitting=1;
   for(k=0;k<n;k++)begin
    if(k==0)#(access_ns);else #(period_ns);
    if(req!==previous_req||count!==8'(n)||oe!==9'h1ff)$fatal(1,"GPIO changed burst while transmitting");
    data=image[presented_words];
    if(presented_words==0)first_data_ps=longint'($realtime*1000.0);
    presented_words++;last_data_ps=longint'($realtime*1000.0);
   end
   transmitting=0;
  end
 end
 always @(oe)if(presented_words!=0&&oe!==9'h1ff)$fatal(1,"GPIO output disabled mid-task");
 always @(req)if(transmitting&&req!==previous_req)$fatal(1,"GPIO burst overlap");
endmodule
