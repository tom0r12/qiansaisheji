`timescale 1ns/1ps
`default_nettype none
// Hardware-only R_i or C_j generation: 32 signed8 pair products.
// One elastic multiply stage. Frames are exactly 32 accepted inputs.
module winograd_int8_factor32 (
    input logic clk,
    input logic rst_n,
    input logic in_valid,
    output logic in_ready,
    input logic signed [7:0] in_even,
    input logic signed [7:0] in_odd,
    output logic out_valid,
    input logic out_ready,
    output logic signed [20:0] out_factor
);
    logic [4:0] input_count_q;
    logic pipe_valid_q, pipe_first_q, pipe_last_q;
    logic signed [15:0] product_q;
    logic signed [20:0] accumulator_q, sum_d;
    logic accumulator_ready, pipe_ready;

    assign accumulator_ready = !out_valid || out_ready;
    assign pipe_ready = !pipe_valid_q || accumulator_ready;
    assign in_ready = rst_n && pipe_ready;
    assign sum_d = (pipe_first_q ? 21'sd0 : accumulator_q)
                 + {{5{product_q[15]}}, product_q};

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            input_count_q <= 5'd0;
            pipe_valid_q <= 1'b0;
            pipe_first_q <= 1'b0;
            pipe_last_q <= 1'b0;
            product_q <= 16'sd0;
        end else if (pipe_ready) begin
            pipe_valid_q <= in_valid;
            if (in_valid) begin
                product_q <= in_even * in_odd;
                pipe_first_q <= input_count_q == 5'd0;
                pipe_last_q <= input_count_q == 5'd31;
                input_count_q <= input_count_q + 5'd1;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            accumulator_q <= 21'sd0;
            out_factor <= 21'sd0;
            out_valid <= 1'b0;
        end else begin
            if (out_valid && out_ready) out_valid <= 1'b0;
            if (pipe_valid_q && accumulator_ready) begin
                accumulator_q <= pipe_last_q ? 21'sd0 : sum_d;
                if (pipe_last_q) begin
                    out_factor <= sum_d;
                    out_valid <= 1'b1;
                end
            end
        end
    end
endmodule
`default_nettype wire
