`timescale 1ns/1ps
`default_nettype none
// Row-pair stage reduced to a checked pass-through: the host already supplies
// core order, so no 64x48 reorder buffer is needed. Same port contract as the
// frozen q12_rowpair_pack (index/last/error semantics preserved).
module q12_rowpair_pack (
    input wire clk, rst_n,
    input wire start_valid, output wire start_ready,
    input wire start_mode_w,
    input wire in_valid, output wire in_ready,
    input wire [47:0] in_data,
    input wire [2:0] in_count,
    input wire in_last, upstream_error,
    output wire out_valid, input wire out_ready,
    output wire [47:0] out_data,
    output wire out_last,
    output reg [10:0] out_word_index,
    output reg busy, done, error,
    output reg [2:0] error_code,
    output reg [31:0] total_cycles
);
    reg mode_w_q;
    wire [10:0] last_index = mode_w_q ? 11'd511 : 11'd1599;
    assign start_ready = rst_n && !busy;
    assign out_valid = rst_n && busy && !error && in_valid;
    assign in_ready = rst_n && busy && (error || out_ready);
    assign out_data = in_data;
    assign out_last = out_word_index == last_index;
    wire fire = in_valid && in_ready;
    wire bad = fire && !error && (in_count != 3'd4 || in_last != out_last);
    always @(posedge clk) begin
        if (!rst_n) begin
            busy<=0; done<=0; error<=0; error_code<=0; total_cycles<=0; mode_w_q<=0; out_word_index<=0;
        end else begin
            done<=0;
            if (start_valid && start_ready) begin
                busy<=1; error<=0; error_code<=0; total_cycles<=0; mode_w_q<=start_mode_w; out_word_index<=0;
            end else if (busy) begin
                if (!error && (upstream_error || bad)) begin
                    error<=1; error_code<=upstream_error ? 3'd4 : (in_count!=3'd4 ? 3'd1 : 3'd2);
                    if (upstream_error || (fire && in_last)) begin busy<=0; done<=1; end
                end else if (error) begin
                    if (upstream_error || (fire && in_last)) begin busy<=0; done<=1; end
                end else if (fire) begin
                    if (out_last) begin busy<=0; done<=1; end
                    else out_word_index<=out_word_index+1'b1;
                end
            end
        end
    end
endmodule
`default_nettype wire
