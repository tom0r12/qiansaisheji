`timescale 1ns/1ps
`default_nettype none
// Reusable pair-product lane. R/C must come from hardware factor32 units for
// the SAME vectors. The bias and factors are sampled only on the first pair.
// BIAS_W=16 is the compact INT8 format. BIAS_W=48 uses a 49-bit exact result;
// it deliberately does not reproduce an old per-k signed48 overflow trap.
module winograd_int8_dot64 #(
    parameter integer BIAS_W = 16,
    localparam integer RESULT_W = (BIAS_W > 23) ? BIAS_W + 1 : 24
) (
    input logic clk,
    input logic rst_n,
    input logic in_valid,
    output logic in_ready,
    input logic signed [7:0] in_x_even,
    input logic signed [7:0] in_x_odd,
    input logic signed [7:0] in_w_even,
    input logic signed [7:0] in_w_odd,
    input logic signed [20:0] in_row_factor,
    input logic signed [20:0] in_col_factor,
    input logic signed [BIAS_W-1:0] in_bias,
    output logic out_valid,
    input logic out_ready,
    output logic signed [RESULT_W-1:0] out_result,
    output logic signed [21:0] out_dot
);
    logic [4:0] input_count_q;
    logic pipe_valid_q, pipe_first_q, pipe_last_q;
    logic signed [8:0] sum_left, sum_right;
    logic signed [17:0] pair_product_q;
    logic signed [20:0] pipe_row_q, pipe_col_q, row_factor_q, col_factor_q;
    logic signed [BIAS_W-1:0] pipe_bias_q, bias_q;
    logic signed [22:0] accumulator_q, pair_sum_d;
    logic signed [23:0] corrected_dot_d;
    logic signed [RESULT_W-1:0] result_d;
    logic accumulator_ready, pipe_ready;

    assign sum_left = {in_x_even[7], in_x_even} + {in_w_odd[7], in_w_odd};
    assign sum_right = {in_x_odd[7], in_x_odd} + {in_w_even[7], in_w_even};
    assign accumulator_ready = !out_valid || out_ready;
    assign pipe_ready = !pipe_valid_q || accumulator_ready;
    assign in_ready = rst_n && pipe_ready;
    assign pair_sum_d = (pipe_first_q ? 23'sd0 : accumulator_q)
                      + {{5{pair_product_q[17]}}, pair_product_q};
    assign corrected_dot_d = {pair_sum_d[22], pair_sum_d}
                           - {{3{row_factor_q[20]}}, row_factor_q}
                           - {{3{col_factor_q[20]}}, col_factor_q};
    assign result_d = {{(RESULT_W-24){corrected_dot_d[23]}}, corrected_dot_d}
                    + {{(RESULT_W-BIAS_W){bias_q[BIAS_W-1]}}, bias_q};

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            input_count_q <= 5'd0;
            pipe_valid_q <= 1'b0;
            pipe_first_q <= 1'b0;
            pipe_last_q <= 1'b0;
            pair_product_q <= 18'sd0;
            pipe_row_q <= 21'sd0;
            pipe_col_q <= 21'sd0;
            pipe_bias_q <= '0;
        end else if (pipe_ready) begin
            pipe_valid_q <= in_valid;
            if (in_valid) begin
                pair_product_q <= sum_left * sum_right;
                pipe_first_q <= input_count_q == 5'd0;
                pipe_last_q <= input_count_q == 5'd31;
                pipe_row_q <= in_row_factor;
                pipe_col_q <= in_col_factor;
                pipe_bias_q <= in_bias;
                input_count_q <= input_count_q + 5'd1;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            accumulator_q <= 23'sd0;
            row_factor_q <= 21'sd0;
            col_factor_q <= 21'sd0;
            bias_q <= '0;
            out_result <= '0;
            out_dot <= 22'sd0;
            out_valid <= 1'b0;
        end else begin
            if (out_valid && out_ready) out_valid <= 1'b0;
            if (pipe_valid_q && accumulator_ready) begin
                if (pipe_first_q) begin
                    row_factor_q <= pipe_row_q;
                    col_factor_q <= pipe_col_q;
                    bias_q <= pipe_bias_q;
                end
                accumulator_q <= pipe_last_q ? 23'sd0 : pair_sum_d;
                if (pipe_last_q) begin
                    out_result <= result_d;
                    out_dot <= corrected_dot_d[21:0];
                    out_valid <= 1'b1;
                end
            end
        end
    end
endmodule
`default_nettype wire
