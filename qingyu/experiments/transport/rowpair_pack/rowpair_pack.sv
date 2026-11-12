`timescale 1ns/1ps
`default_nettype none
module rowpair_pack (
    input wire clk, rst_n,
    input wire start_valid, output wire start_ready,
    input wire start_mode_w,
    input wire in_valid, output wire in_ready,
    input wire [31:0] in_data,
    input wire [2:0] in_count,
    input wire in_last, upstream_error,
    output wire out_valid, input wire out_ready,
    output wire [31:0] out_data,
    output wire out_last,
    output reg [10:0] out_word_index,
    output reg busy, done, error,
    output reg [2:0] error_code,
    output reg [31:0] total_cycles
);
    // Exactly 256 bytes of data storage. Neither reset nor START clears it.
    // Epoch/ready bits keep old and uninitialized contents inaccessible.
    reg [31:0] data_mem [0:63];
    reg mode_w_q, fill_slot_q, read_slot_q;
    reg [1:0] slot_ready_q, slot_tail_q;
    reg [4:0] fill_pos_q, read_pos_q;
    reg [5:0] fill_pair_q;
    reg [10:0] received_q;
    reg input_end_q, error_hold_q;
    wire [10:0] input_last_index = mode_w_q ? 11'd511 : 11'd1583;
    wire [10:0] output_last_index = mode_w_q ? 11'd511 : 11'd1599;
    wire tail_pair = !mode_w_q && fill_pair_q == 6'd49;
    wire [4:0] fill_last = (mode_w_q || tail_pair) ? 5'd15 : 5'd31;
    wire [4:0] read_last = mode_w_q ? 5'd15 : 5'd31;
    wire [5:0] even_address = {read_slot_q,5'b0} + {2'b0,read_pos_q[4:1]};
    wire [5:0] odd_address = even_address + (mode_w_q ? 6'd8 : 6'd16);
    wire [15:0] even_half = read_pos_q[0] ? data_mem[even_address][31:16] : data_mem[even_address][15:0];
    wire [15:0] odd_half = slot_tail_q[read_slot_q] ? 16'b0 :
                         (read_pos_q[0] ? data_mem[odd_address][31:16] : data_mem[odd_address][15:0]);
    assign start_ready = rst_n && !busy;
    assign in_ready = rst_n && busy && !input_end_q &&
                      (error || upstream_error || !slot_ready_q[fill_slot_q]);
    assign out_valid = rst_n && busy && slot_ready_q[read_slot_q] && (!error || error_hold_q);
    assign out_data = mode_w_q ? {odd_half[15:8],even_half[15:8],odd_half[7:0],even_half[7:0]} :
                                {odd_half,even_half};
    assign out_last = out_word_index == output_last_index;
    wire in_fire = in_valid && in_ready;
    wire out_fire = out_valid && out_ready;
    wire bad_count = in_fire && in_count != 3'd4;
    wire bad_last = in_fire && in_last != (received_q == input_last_index);
    wire fault_now = upstream_error || bad_count || bad_last;
    always @(posedge clk) begin
        if (!rst_n) begin
            busy<=0; done<=0; error<=0; error_code<=0; total_cycles<=0;
            mode_w_q<=0; fill_slot_q<=0; read_slot_q<=0; slot_ready_q<=0; slot_tail_q<=0;
            fill_pos_q<=0; read_pos_q<=0; fill_pair_q<=0; received_q<=0;
            input_end_q<=0; error_hold_q<=0; out_word_index<=0;
        end else begin
            done<=0;
            if (start_valid && start_ready) begin
                busy<=1; error<=0; error_code<=0; total_cycles<=1; mode_w_q<=start_mode_w;
                fill_slot_q<=0; read_slot_q<=0; slot_ready_q<=0; slot_tail_q<=0;
                fill_pos_q<=0; read_pos_q<=0; fill_pair_q<=0; received_q<=0;
                input_end_q<=0; error_hold_q<=0; out_word_index<=0;
            end else if (busy) begin
                total_cycles<=total_cycles+1;
                if (!error && fault_now) begin
                    error<=1;
                    error_code<=upstream_error ? 3'd4 : bad_count ? 3'd1 : in_last ? 3'd2 : 3'd3;
                    // An already offered word cannot be revoked by an error.
                    error_hold_q<=out_valid && !out_ready;
                    if (upstream_error || (in_fire && in_last)) input_end_q<=1;
                end else if (error) begin
                    if (out_fire) error_hold_q<=0;
                    if (upstream_error || (in_fire && in_last)) input_end_q<=1;
                    if ((input_end_q || upstream_error || (in_fire && in_last)) &&
                        (!error_hold_q || out_fire)) begin
                        busy<=0; done<=1; slot_ready_q<=0;
                    end
                end else begin
                    if (in_fire) begin
                        data_mem[{fill_slot_q,fill_pos_q}]<=in_data;
                        received_q<=received_q+1;
                        if (in_last) input_end_q<=1;
                        if (fill_pos_q == fill_last) begin
                            slot_ready_q[fill_slot_q]<=1;
                            slot_tail_q[fill_slot_q]<=tail_pair;
                            fill_slot_q<=!fill_slot_q;
                            fill_pos_q<=0; fill_pair_q<=fill_pair_q+1;
                        end else fill_pos_q<=fill_pos_q+1;
                    end
                    if (out_fire) begin
                        if (out_last) begin busy<=0; done<=1; end
                        else out_word_index<=out_word_index+1;
                        if (read_pos_q == read_last) begin
                            slot_ready_q[read_slot_q]<=0;
                            read_slot_q<=!read_slot_q; read_pos_q<=0;
                        end else read_pos_q<=read_pos_q+1;
                    end
                end
            end
        end
    end
endmodule
`default_nettype wire
