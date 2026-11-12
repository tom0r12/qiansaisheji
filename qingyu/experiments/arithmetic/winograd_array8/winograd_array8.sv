`timescale 1ns/1ps
`default_nettype none
module winograd_array8 (
    input logic clk, rst_n,
    input logic start_valid,
    output logic start_ready,
    input logic load_valid,
    output logic load_ready,
    input logic [31:0] load_data,
    output logic out_valid,
    input logic out_ready,
    output logic [31:0] out_data,
    output logic [8:0] out_word_index,
    output logic busy, done, error,
    output logic [31:0] total_cycles, load_cycles, factor_cycles, compute_cycles, store_cycles
);
    localparam logic [3:0] IDLE=0, LOAD=1, CF_READ=2, CF_WAIT=3,
        RF_READ=4, RF_WAIT=5, DOT_READ=6, DOT_WAIT=7, STORE=8;
    localparam logic [1:0] TAG_C=0, TAG_R=1, TAG_D=2;
    logic [3:0] state_q, row_group_q;
    logic [10:0] load_count_q;
    logic [4:0] pair_q;
    logic [2:0] store_row_q;
    logic [1:0] store_word_q;
    logic [3:0] active_rows;
    logic engine_rst_n, load_fire, read_issue, shift_bad;
    logic rd_valid_q, rd_first_q, rd_last_q;
    logic [1:0] rd_tag_q;
    logic [7:0] w_load_offset;
    logic signed [15:0] bias_q [0:15];
    logic [7:0] shift_q [0:15];
    logic [7:0] x_en, x_we;
    logic [15:0] w_en, w_we;
    logic [9:0] x_addr [0:7];
    logic [6:0] w_addr [0:15];
    logic [15:0] x_wdata [0:7], w_wdata [0:15];
    wire [15:0] x_rdata [0:7], w_rdata [0:15];
    wire [7:0] rf_in_ready, rf_out_valid;
    wire [15:0] cf_in_ready, cf_out_valid;
    wire signed [20:0] rf_result [0:7], cf_result [0:15];
    logic rf_all_valid, cf_all_valid, dot_all_valid;
    wire [127:0] pe_in_ready, pe_out_valid;
    logic [127:0] pe_out_ready;
    wire [2943:0] pe_sum_flat;
    logic signed [22:0] selected_sum [0:3];
    logic signed [23:0] corrected [0:3];
    integer i, lane, pe_index;

    assign busy = state_q != IDLE;
    assign start_ready = rst_n && state_q == IDLE;
    assign load_ready = rst_n && state_q == LOAD;
    assign load_fire = load_ready && load_valid;
    assign engine_rst_n = rst_n && state_q != IDLE;
    assign active_rows = row_group_q == 4'd12 ? 4'd3 : 4'd8;
    assign w_load_offset = 8'(load_count_q - 11'd1600);
    assign read_issue = state_q == CF_READ || state_q == RF_READ || state_q == DOT_READ;
    assign shift_bad = load_data[7:0] > 8'd47 || load_data[15:8] > 8'd47 ||
                       load_data[23:16] > 8'd47 || load_data[31:24] > 8'd47;

    // Each X load word updates two DIFFERENT row banks. Each W word updates
    // two DIFFERENT channel banks. Both halves contain adjacent K elements.
    always_comb begin
        x_en = 0; x_we = 0; w_en = 0; w_we = 0;
        for (integer r=0; r<8; r=r+1) begin
            x_addr[r] = {1'b0, row_group_q, pair_q};
            x_wdata[r] = (r%2 == 0) ? load_data[15:0] : load_data[31:16];
            if (load_fire && load_count_q < 11'd1600 &&
                load_count_q[6:5] == 2'(r/2) && !(load_count_q[10:5] == 6'd49 && r%2 == 1)) begin
                x_en[r] = 1; x_we[r] = 1;
                x_addr[r] = {1'b0, load_count_q[10:7], load_count_q[4:0]};
            end else if ((state_q == RF_READ || state_q == DOT_READ) && 4'(r) < active_rows) x_en[r] = 1;
        end
        for (integer c=0; c<16; c=c+1) begin
            w_addr[c] = {2'b0, pair_q};
            w_wdata[c] = (c%2 == 0) ? load_data[15:0] : load_data[31:16];
            if (load_fire && load_count_q >= 11'd1600 && load_count_q < 11'd1856 && w_load_offset[2:0] == 3'(c/2)) begin
                w_en[c] = 1; w_we[c] = 1; w_addr[c] = {2'b0, w_load_offset[7:3]};
            end else if (state_q == CF_READ || state_q == DOT_READ) w_en[c] = 1;
        end
    end

    generate
        for (genvar r=0; r<8; r=r+1) begin: x_bank
            qingyu_sram16 #(.DEPTH(1024), .ADDR_W(10)) memory (
                .clk, .en(x_en[r]), .we(x_we[r]), .addr(x_addr[r]), .wdata(x_wdata[r]), .rdata(x_rdata[r]));
            winograd_int8_factor32 factor (.clk, .rst_n(engine_rst_n),
                .in_valid(rd_valid_q && rd_tag_q == TAG_R && 4'(r) < active_rows), .in_ready(rf_in_ready[r]),
                .in_even(x_rdata[r][7:0]), .in_odd(x_rdata[r][15:8]), .out_valid(rf_out_valid[r]),
                .out_ready(state_q == RF_WAIT && rf_all_valid), .out_factor(rf_result[r]));
            for (genvar c=0; c<16; c=c+1) begin: lane
                winograd_int8_pair_acc32 pe (.clk, .rst_n(engine_rst_n),
                    .in_valid(rd_valid_q && rd_tag_q == TAG_D && 4'(r) < active_rows), .in_ready(pe_in_ready[r*16+c]),
                    .in_first(rd_first_q), .in_last(rd_last_q),
                    .in_x_even(x_rdata[r][7:0]), .in_x_odd(x_rdata[r][15:8]),
                    .in_w_even(w_rdata[c][7:0]), .in_w_odd(w_rdata[c][15:8]),
                    .out_valid(pe_out_valid[r*16+c]), .out_ready(pe_out_ready[r*16+c]),
                    .out_pair_sum(pe_sum_flat[(r*16+c)*23+:23]));
            end
        end
        for (genvar c=0; c<16; c=c+1) begin: w_bank
            qingyu_sram16 #(.DEPTH(128), .ADDR_W(7)) memory (
                .clk, .en(w_en[c]), .we(w_we[c]), .addr(w_addr[c]), .wdata(w_wdata[c]), .rdata(w_rdata[c]));
            winograd_int8_factor32 factor (.clk, .rst_n(engine_rst_n),
                .in_valid(rd_valid_q && rd_tag_q == TAG_C), .in_ready(cf_in_ready[c]),
                .in_even(w_rdata[c][7:0]), .in_odd(w_rdata[c][15:8]), .out_valid(cf_out_valid[c]),
                .out_ready(state_q == CF_WAIT && cf_all_valid), .out_factor(cf_result[c]));
        end
    endgenerate

    always_comb begin
        cf_all_valid = &cf_out_valid;
        rf_all_valid = 1'b1; dot_all_valid = 1'b1;
        for (integer r=0; r<8; r=r+1) begin
            if (4'(r) < active_rows) begin
                rf_all_valid = rf_all_valid && rf_out_valid[r];
                dot_all_valid = dot_all_valid && (&pe_out_valid[r*16+:16]);
            end
        end
    end

    function automatic logic [7:0] requantize(input logic signed [23:0] value, input logic [7:0] shift);
        logic [24:0] magnitude, quotient, remainder, halfway;
        logic signed [25:0] rounded;
        begin
            magnitude = value[23] ? {1'b0, ~value} + 25'd1 : {1'b0, value};
            quotient = 0; remainder = 0; halfway = 0; rounded = 0;
            if (shift == 0) rounded = {{2{value[23]}}, value};
            else if (shift < 8'd24) begin
                quotient = magnitude >> shift;
                remainder = magnitude & ((25'd1 << shift) - 25'd1);
                halfway = 25'd1 << (shift - 8'd1);
                if (remainder > halfway || (remainder == halfway && quotient[0])) quotient = quotient + 25'd1;
                rounded = value[23] ? -$signed({1'b0, quotient}) : $signed({1'b0, quotient});
            end
            if (rounded > 26'sd127) requantize = 8'h7f;
            else if (rounded < -26'sd128) requantize = 8'h80;
            else requantize = rounded[7:0];
        end
    endfunction

    // Only four correction/rounding paths. Shared factors/bias stay fixed for
    // this group until every packed output has been accepted.
    always_comb begin
        out_valid = state_q == STORE;
        out_data = 0; out_word_index = {row_group_q, store_row_q, store_word_q};
        pe_out_ready = 0;
        lane = 0; pe_index = 0;
        for (integer b=0; b<4; b=b+1) begin
            lane = int'(store_word_q)*4+b;
            pe_index = int'(store_row_q)*16+lane;
            selected_sum[b] = pe_sum_flat[pe_index*23+:23];
            corrected[b] = {selected_sum[b][22], selected_sum[b]}
                         - {{3{rf_result[store_row_q][20]}}, rf_result[store_row_q]}
                         - {{3{cf_result[lane][20]}}, cf_result[lane]}
                         + {{8{bias_q[lane][15]}}, bias_q[lane]};
            out_data[b*8+:8] = requantize(corrected[b], shift_q[lane]);
            out_valid = out_valid && pe_out_valid[pe_index];
        end
        if (out_valid && out_ready) begin
            for (integer b=0; b<4; b=b+1)
                pe_out_ready[int'(store_row_q)*16+int'(store_word_q)*4+b] = 1'b1;
        end
    end

`ifndef SYNTHESIS
    // There is no speculative next-group read: all result consumers have
    // drained before a new 32-pair stream starts. Prove that the fixed-rate
    // synchronous SRAM response therefore always has a ready consumer.
    always @(posedge clk) begin
        if (engine_rst_n && rd_valid_q) begin
            if (rd_tag_q == TAG_C && !(&cf_in_ready)) $fatal(1, "Column factor read response blocked");
            for (integer r=0; r<8; r=r+1) if (4'(r) < active_rows) begin
                if (rd_tag_q == TAG_R && !rf_in_ready[r]) $fatal(1, "Row factor read response blocked");
                if (rd_tag_q == TAG_D && !(&pe_in_ready[r*16+:16])) $fatal(1, "Pair read response blocked");
            end
        end
    end
`endif

    // SRAM read response is consumed exactly one cycle after its request.
    always_ff @(posedge clk) begin
        if (!engine_rst_n) begin
            rd_valid_q <= 0; rd_tag_q <= TAG_C; rd_first_q <= 0; rd_last_q <= 0;
        end else begin
            rd_valid_q <= read_issue;
            if (read_issue) begin
                rd_tag_q <= state_q == CF_READ ? TAG_C : state_q == RF_READ ? TAG_R : TAG_D;
                rd_first_q <= pair_q == 0; rd_last_q <= pair_q == 31;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state_q <= IDLE; load_count_q <= 0; row_group_q <= 0; pair_q <= 0;
            store_row_q <= 0; store_word_q <= 0; done <= 0; error <= 0;
            total_cycles <= 0; load_cycles <= 0; factor_cycles <= 0; compute_cycles <= 0; store_cycles <= 0;
            for (i=0; i<16; i=i+1) begin bias_q[i] <= 0; shift_q[i] <= 0; end
        end else begin
            done <= 0;
            if (busy) total_cycles <= total_cycles + 1;
            case (state_q)
                LOAD: load_cycles <= load_cycles + 1;
                CF_READ, CF_WAIT, RF_READ, RF_WAIT: factor_cycles <= factor_cycles + 1;
                DOT_READ, DOT_WAIT: compute_cycles <= compute_cycles + 1;
                STORE: store_cycles <= store_cycles + 1;
                default: begin end
            endcase
            case (state_q)
                IDLE: if (start_valid) begin
                    state_q <= LOAD; load_count_q <= 0; row_group_q <= 0; pair_q <= 0;
                    store_row_q <= 0; store_word_q <= 0; error <= 0;
                    total_cycles <= 0; load_cycles <= 0; factor_cycles <= 0; compute_cycles <= 0; store_cycles <= 0;
                    for (i=0; i<16; i=i+1) begin bias_q[i] <= 0; shift_q[i] <= 0; end
                end
                LOAD: if (load_fire) begin
                    load_count_q <= load_count_q + 1;
                    for (i=0; i<16; i=i+1) begin
                        if (load_count_q == 11'(1856+i/2)) bias_q[i] <= load_data[(i%2)*16+:16];
                        if (load_count_q == 11'(1864+i/4)) shift_q[i] <= load_data[(i%4)*8+:8];
                    end
                    if (load_count_q >= 11'd1864 && shift_bad) error <= 1;
                    if (load_count_q == 11'd1867) begin
                        pair_q <= 0;
                        if (error || shift_bad) begin state_q <= IDLE; done <= 1; end
                        else state_q <= CF_READ;
                    end
                end
                CF_READ, RF_READ, DOT_READ: begin
                    pair_q <= pair_q + 1;
                    if (pair_q == 31) state_q <= state_q == CF_READ ? CF_WAIT : state_q == RF_READ ? RF_WAIT : DOT_WAIT;
                end
                CF_WAIT: if (cf_all_valid) begin
                    state_q <= RF_READ; pair_q <= 0;
                end
                RF_WAIT: if (rf_all_valid) begin
                    state_q <= DOT_READ; pair_q <= 0;
                end
                DOT_WAIT: if (dot_all_valid) begin state_q <= STORE; store_row_q <= 0; store_word_q <= 0; end
                STORE: if (out_valid && out_ready) begin
                    store_word_q <= store_word_q + 1;
                    if (store_word_q == 3) begin
                        store_row_q <= store_row_q + 1;
                        if ({1'b0, store_row_q}+4'd1 == active_rows) begin
                            if (row_group_q == 12) begin state_q <= IDLE; done <= 1; end
                            else begin row_group_q <= row_group_q + 1; state_q <= RF_READ; pair_q <= 0; end
                        end
                    end
                end
                default: begin state_q <= IDLE; error <= 1; done <= 1; end
            endcase
        end
    end
endmodule
`default_nettype wire
