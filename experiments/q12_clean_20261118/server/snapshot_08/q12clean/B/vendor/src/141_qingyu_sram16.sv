`timescale 1ns/1ps
// Behavioral single-port synchronous SRAM. Replace this wrapper's internals
// with the contest macro for final ASIC mapping; this is not a foundry macro.
module qingyu_sram16 #(
    parameter integer DEPTH = 128,
    parameter integer ADDR_W = $clog2(DEPTH)
) (
    input  wire                  clk,
    input  wire                  en,
    input  wire                  we,
    input  wire [ADDR_W-1:0]     addr,
    input  wire [15:0]          wdata,
    output reg  [15:0]          rdata
);
    reg [15:0] mem [0:DEPTH-1];
    always @(posedge clk) begin
        if (en) begin
            if (we) mem[addr] <= wdata;
            else rdata <= mem[addr];
        end
    end
endmodule
