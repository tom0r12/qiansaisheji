// Interface-only declarations for structural logic inventory.
// No storage behavior, timing, physical area or power is modeled here.
(* blackbox *) module RAMSP128X16 (
 input CLK,CEN,GWEN, input [15:0] WEN, input [6:0] A,
 input [15:0] D, output [15:0] Q, input [2:0] EMA,
 input [1:0] EMAW, input RET1N
); endmodule
(* blackbox *) module RAMSP1024X16 (
 input CLK,CEN,GWEN, input [15:0] WEN, input [9:0] A,
 input [15:0] D, output [15:0] Q, input [2:0] EMA,
 input [1:0] EMAW, input RET1N
); endmodule
(* blackbox *) module RAMSP4096X16 (
 input CLK,CEN,GWEN, input [15:0] WEN, input [11:0] A,
 input [15:0] D, output [15:0] Q, input [2:0] EMA,
 input [1:0] EMAW, input RET1N
); endmodule
