`timescale 1ns/1ps
// Alternative to rtl/qingyu_sram16.sv: compile exactly one implementation.
// SRAM_Lib_2025 ports and TT margin settings verified from server metadata.
module qingyu_sram16 #(
    parameter integer DEPTH = 128,
    parameter integer ADDR_W = $clog2(DEPTH)
) (
    input wire clk, en, we,
    input wire [ADDR_W-1:0] addr,
    input wire [15:0] wdata,
    output wire [15:0] rdata
);
    wire cen_n = ~en;
    wire gwen_n = ~we;
    wire [15:0] wen_n = {16{~we}};
    generate
        if (DEPTH == 128 && ADDR_W == 7) begin: g128
            RAMSP128X16 macro_ram (
                .CLK(clk), .CEN(cen_n), .GWEN(gwen_n), .WEN(wen_n),
                .A(addr), .D(wdata), .Q(rdata),
                .EMA(3'b010), .EMAW(2'b00), .RET1N(1'b1)
            );
        end else if (DEPTH == 1024 && ADDR_W == 10) begin: g1024
            RAMSP1024X16 macro_ram (
                .CLK(clk), .CEN(cen_n), .GWEN(gwen_n), .WEN(wen_n),
                .A(addr), .D(wdata), .Q(rdata),
                .EMA(3'b010), .EMAW(2'b00), .RET1N(1'b1)
            );
        end else if (DEPTH == 4096 && ADDR_W == 12) begin: g4096
            RAMSP4096X16 macro_ram (
                .CLK(clk), .CEN(cen_n), .GWEN(gwen_n), .WEN(wen_n),
                .A(addr), .D(wdata), .Q(rdata),
                .EMA(3'b010), .EMAW(2'b00), .RET1N(1'b1)
            );
        end else begin: g_invalid
            QINGYU_UNSUPPORTED_SRAM_CONFIGURATION invalid_configuration();
        end
    endgenerate
endmodule
