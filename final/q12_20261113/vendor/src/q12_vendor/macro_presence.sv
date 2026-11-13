`timescale 1ns/1ps
module q12_macro_presence #(parameter integer DEPTH=128)();
 initial begin
  #1;
  case(DEPTH)
   128:tb_q12soc.macro128_count=tb_q12soc.macro128_count+1;
   1024:tb_q12soc.macro1024_count=tb_q12soc.macro1024_count+1;
   4096:tb_q12soc.macro4096_count=tb_q12soc.macro4096_count+1;
   default:$fatal(1,"unsupported macro presence depth");
  endcase
 end
endmodule
bind RAMSP128X16 q12_macro_presence #(.DEPTH(128)) q12_presence();
bind RAMSP1024X16 q12_macro_presence #(.DEPTH(1024)) q12_presence();
bind RAMSP4096X16 q12_macro_presence #(.DEPTH(4096)) q12_presence();
