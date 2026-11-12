`timescale 1ns/1ps
`default_nettype none
// Verification substitute only. Same synchronous single-port read latency;
// Q becomes unknown on a write edge so stale/illegal read reuse cannot hide.
module qingyu_sram16 #(parameter DEPTH=128,parameter ADDR_W=7)(
    input wire clk,en,we,input wire [ADDR_W-1:0] addr,input wire [15:0] wdata,output reg [15:0] rdata
);
    reg [15:0] mem [0:DEPTH-1];
    always @(posedge clk) if(en) begin
        if(we) begin mem[addr]<=wdata;rdata<=16'hxxxx;end
        else rdata<=mem[addr];
    end
endmodule
`default_nettype wire
