`timescale 1ns/1ps
`default_nettype none
`ifndef QINGYU_X_VALID_WORDS
`define QINGYU_X_VALID_WORDS 352
`endif
// Optional private-X physical mapping. Compile instead of the original wrapper.
// There is no reset port or initialization; task epochs belong to the core.
module qingyu_sram16 #(
    parameter integer DEPTH = 128,
    parameter integer ADDR_W = $clog2(DEPTH),
    parameter integer X_VALID_WORDS = `QINGYU_X_VALID_WORDS
) (
    input wire clk, en, we,
    input wire [ADDR_W-1:0] addr,
    input wire [15:0] wdata,
    output wire [15:0] rdata
);
    wire gwen_n = ~we;
    wire [15:0] wen_n = {16{~we}};
    generate
        if (DEPTH == 128 && ADDR_W == 7) begin: g128
            RAMSP128X16 macro_ram (
                .CLK(clk), .CEN(~en), .GWEN(gwen_n), .WEN(wen_n),
                .A(addr), .D(wdata), .Q(rdata),
                .EMA(3'b010), .EMAW(2'b00), .RET1N(1'b1)
            );
        end else if (DEPTH == 1024 && ADDR_W == 10 &&
                     (X_VALID_WORDS == 352 || X_VALID_WORDS == 416)) begin: g_compact
            localparam integer PAGES = (X_VALID_WORDS+127)/128;
            wire legal_address = addr < 10'(X_VALID_WORDS);
            wire [15:0] page_data [0:PAGES-1];
            reg [2:0] selected_page_q;
            reg [15:0] selected_data;
            // Capture both read and write identity: write-Q behavior belongs
            // to the selected real macro and must not expose a previous page.
            always @(posedge clk) begin
                if(en) selected_page_q <= legal_address ? addr[9:7] : 3'd7;
            end
            for(genvar p=0;p<PAGES;p=p+1) begin: pages
                wire selected = en && legal_address && addr[9:7] == 3'(p);
                RAMSP128X16 macro_ram (
                    .CLK(clk), .CEN(~selected), .GWEN(gwen_n), .WEN(wen_n),
                    .A(addr[6:0]), .D(wdata), .Q(page_data[p]),
                    .EMA(3'b010), .EMAW(2'b00), .RET1N(1'b1)
                );
            end
            always @* begin
                selected_data = 16'b0;
                for(integer p=0;p<PAGES;p=p+1)
                    if(selected_page_q == 3'(p)) selected_data = page_data[p];
            end
            assign rdata = selected_data;
        end else if (DEPTH == 4096 && ADDR_W == 12) begin: g4096
            RAMSP4096X16 macro_ram (
                .CLK(clk), .CEN(~en), .GWEN(gwen_n), .WEN(wen_n),
                .A(addr), .D(wdata), .Q(rdata),
                .EMA(3'b010), .EMAW(2'b00), .RET1N(1'b1)
            );
        end else begin: g_invalid
            QINGYU_UNSUPPORTED_COMPACT_SRAM_CONFIGURATION invalid_configuration();
        end
    endgenerate
endmodule
`default_nettype wire
