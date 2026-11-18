`timescale 1ns/1ps
`default_nettype none
// PE data words deliberately retain unspecified data across reset.
// pipe_valid/out_valid reset to0; in_first forces0+product before a frame's
// accumulator can be observed. The enclosing core enforces this32-pair contract.
// Raw 32-pair lane. Global array controller supplies first/last markers.
// R/C/bias are deliberately NOT stored in each PE. The accumulator itself
// holds the completed result while downstream shared correction is stalled.
module q12_pair_acc (
    input logic clk, rst_n,
    input logic in_valid,
    output logic in_ready,
    input logic in_first, in_last,
    input logic signed [11:0] in_x_even, in_x_odd, in_w_even, in_w_odd,
    output logic out_valid,
    input logic out_ready,
    output logic signed [30:0] out_pair_sum
);
    logic signed [12:0] left_sum, right_sum;
    logic signed [25:0] product_q;
    logic signed [30:0] accumulator_q, sum_d;
    logic pipe_valid_q, first_q, last_q;
    logic accumulator_ready, pipe_ready;
    assign left_sum = {in_x_even[11], in_x_even} + {in_w_odd[11], in_w_odd};
    assign right_sum = {in_x_odd[11], in_x_odd} + {in_w_even[11], in_w_even};
    assign accumulator_ready = !out_valid || out_ready;
    assign pipe_ready = !pipe_valid_q || accumulator_ready;
    assign in_ready = rst_n && pipe_ready;
    assign sum_d = (first_q ? 31'sd0 : accumulator_q) + {{5{product_q[25]}}, product_q};
    assign out_pair_sum = accumulator_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            pipe_valid_q <= 1'b0;
            first_q <= 1'b0;
            last_q <= 1'b0;
        end else if (pipe_ready) begin
            pipe_valid_q <= in_valid;
            if (in_valid) begin
                product_q <= left_sum * right_sum;
                first_q <= in_first;
                last_q <= in_last;
            end
        end
    end
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            out_valid <= 1'b0;
        end else begin
            if (out_valid && out_ready) out_valid <= 1'b0;
            if (pipe_valid_q && accumulator_ready) begin
                accumulator_q <= sum_d;
                if (last_q) out_valid <= 1'b1;
            end
        end
    end
endmodule
`default_nettype wire
