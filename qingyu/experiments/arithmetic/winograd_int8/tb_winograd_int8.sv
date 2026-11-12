`timescale 1ns/1ps
`default_nettype none
module tb_winograd_int8;
    logic clk = 1'b0;
    always #5 clk = !clk;
    logic rst_n = 1'b0;
    logic f_valid = 0, fx_ready, fw_ready, fx_valid, fw_valid;
    logic f_out_ready = 0, d_out_ready = 0;
    logic signed [7:0] fx_even = 0, fx_odd = 0, fw_even = 0, fw_odd = 0;
    logic signed [20:0] fx_factor, fw_factor;
    logic d_valid = 0, d16_ready, d48_ready, d16_valid, d48_valid;
    logic signed [7:0] dx_even = 0, dx_odd = 0, dw_even = 0, dw_odd = 0;
    logic signed [20:0] d_row = 0, d_col = 0, captured_row = 0, captured_col = 0;
    logic signed [15:0] d_bias16 = 0, frame_bias16 = 0;
    logic signed [47:0] d_bias48 = 0, frame_bias48 = 0;
    logic signed [23:0] d16_result;
    logic signed [48:0] d48_result;
    logic signed [21:0] d16_dot, d48_dot;
    logic signed [7:0] x [0:63], w [0:63];
    integer f_force_stall = 0, d_force_stall = 0, random_backpressure = 1;
    integer seed = 1, junk, cases = 0, total_factor_outputs = 0, total_dot_outputs = 0;
    integer cycles = 0, resets = 0, factor_outputs = 0, dot_outputs = 0;
    integer fp = 0, dp = 0, fwr = 0, frd = 0, dwr = 0, drd = 0;
    integer first_cycle = 0, latency_min = 99999, latency_max = 0;
    integer last_result_cycle = 0, fast_gap_min = 99999, fast_gap_max = 0, fast_results = 0;
    integer measure_fast = 0, stalled_factor_cycles = 0, stalled_dot_cycles = 0;
    integer dot_input_wait = 0, factor_input_wait = 0;
    longint signed rf_run = 0, cf_run = 0, dot_run = 0, bias16_run = 0, bias48_run = 0;
    longint signed expected_rf [0:8191], expected_cf [0:8191];
    longint signed expected_dot [0:8191], expected16 [0:8191], expected48 [0:8191];
    integer expected_first [0:8191];
    logic old_f_stall = 0, old_d_stall = 0;
    logic signed [20:0] old_rf, old_cf;
    logic signed [23:0] old16;
    logic signed [48:0] old48;
    logic signed [21:0] olddot;

    winograd_int8_factor32 row_factor (.clk, .rst_n, .in_valid(f_valid), .in_ready(fx_ready),
        .in_even(fx_even), .in_odd(fx_odd), .out_valid(fx_valid), .out_ready(f_out_ready), .out_factor(fx_factor));
    winograd_int8_factor32 col_factor (.clk, .rst_n, .in_valid(f_valid), .in_ready(fw_ready),
        .in_even(fw_even), .in_odd(fw_odd), .out_valid(fw_valid), .out_ready(f_out_ready), .out_factor(fw_factor));
    winograd_int8_dot64 #(.BIAS_W(16)) dot16 (.clk, .rst_n, .in_valid(d_valid), .in_ready(d16_ready),
        .in_x_even(dx_even), .in_x_odd(dx_odd), .in_w_even(dw_even), .in_w_odd(dw_odd),
        .in_row_factor(d_row), .in_col_factor(d_col), .in_bias(d_bias16),
        .out_valid(d16_valid), .out_ready(d_out_ready), .out_result(d16_result), .out_dot(d16_dot));
    winograd_int8_dot64 #(.BIAS_W(48)) dot48 (.clk, .rst_n, .in_valid(d_valid), .in_ready(d48_ready),
        .in_x_even(dx_even), .in_x_odd(dx_odd), .in_w_even(dw_even), .in_w_odd(dw_odd),
        .in_row_factor(d_row), .in_col_factor(d_col), .in_bias(d_bias48),
        .out_valid(d48_valid), .out_ready(d_out_ready), .out_result(d48_result), .out_dot(d48_dot));

    always @(negedge clk) begin
        f_out_ready = !f_force_stall && (!random_backpressure || (($urandom % 4) != 0));
        d_out_ready = !d_force_stall && (!random_backpressure || (($urandom % 4) != 0));
    end

    // Independent scoreboard uses original products only, never the Winograd
    // identity to predict a dot result. R/C presented to the DUT are captured
    // from the two hardware factor modules, not from these reference arrays.
    always @(posedge clk) begin
        cycles = cycles + 1;
        if (!rst_n) begin
            fp = 0; dp = 0; fwr = 0; frd = 0; dwr = 0; drd = 0;
            factor_outputs = 0; dot_outputs = 0;
            rf_run = 0; cf_run = 0; dot_run = 0;
            old_f_stall = 0; old_d_stall = 0;
        end else begin
            if ((fx_ready !== fw_ready) || (fx_valid !== fw_valid)) $fatal(1, "Factor protocol differs");
            if ((d16_ready !== d48_ready) || (d16_valid !== d48_valid)) $fatal(1, "Bias-mode protocol differs");
            if (old_f_stall && (!fx_valid || fx_factor !== old_rf || fw_factor !== old_cf))
                $fatal(1, "Factor payload changed under response backpressure");
            if (old_d_stall && (!d16_valid || d16_result !== old16 || d48_result !== old48 || d16_dot !== olddot))
                $fatal(1, "Dot payload changed under response backpressure");
            old_f_stall = fx_valid && !f_out_ready;
            old_d_stall = d16_valid && !d_out_ready;
            old_rf = fx_factor; old_cf = fw_factor;
            old16 = d16_result; old48 = d48_result; olddot = d16_dot;
            if (old_f_stall) stalled_factor_cycles = stalled_factor_cycles + 1;
            if (old_d_stall) stalled_dot_cycles = stalled_dot_cycles + 1;
            if (f_valid && !fx_ready) factor_input_wait = factor_input_wait + 1;
            if (d_valid && !d16_ready) dot_input_wait = dot_input_wait + 1;
            if (f_valid && fx_ready) begin
                if (fp == 0) begin rf_run = 0; cf_run = 0; end
                rf_run = rf_run + longint'($signed(fx_even)) * longint'($signed(fx_odd));
                cf_run = cf_run + longint'($signed(fw_even)) * longint'($signed(fw_odd));
                if (fp == 31) begin
                    expected_rf[fwr] = rf_run; expected_cf[fwr] = cf_run; fwr = fwr + 1;
                    fp = 0;
                end else fp = fp + 1;
            end
            if (fx_valid && f_out_ready) begin
                if (frd >= fwr) $fatal(1, "Unexpected/stale factor response");
                if (longint'($signed(fx_factor)) != expected_rf[frd] || longint'($signed(fw_factor)) != expected_cf[frd])
                    $fatal(1, "Factor mismatch");
                captured_row = fx_factor; captured_col = fw_factor;
                frd = frd + 1; factor_outputs = factor_outputs + 1; total_factor_outputs = total_factor_outputs + 1;
            end
            if (d_valid && d16_ready) begin
                if (dp == 0) begin
                    dot_run = 0; bias16_run = longint'($signed(d_bias16)); bias48_run = longint'($signed(d_bias48));
                    first_cycle = cycles;
                end
                dot_run = dot_run + longint'($signed(dx_even)) * longint'($signed(dw_even))
                                  + longint'($signed(dx_odd)) * longint'($signed(dw_odd));
                if (dp == 31) begin
                    expected_dot[dwr] = dot_run; expected16[dwr] = dot_run + bias16_run;
                    expected48[dwr] = dot_run + bias48_run; expected_first[dwr] = first_cycle;
                    dwr = dwr + 1; dp = 0;
                end else dp = dp + 1;
            end
            if (d16_valid && d_out_ready) begin
                if (drd >= dwr) $fatal(1, "Unexpected/stale dot response");
                if (longint'($signed(d16_dot)) != expected_dot[drd] || longint'($signed(d48_dot)) != expected_dot[drd]
                    || longint'($signed(d16_result)) != expected16[drd] || longint'($signed(d48_result)) != expected48[drd])
                    $fatal(1, "Dot mismatch result16=%0d expected=%0d result48=%0d expected=%0d dot=%0d", d16_result, expected16[drd], d48_result, expected48[drd], expected_dot[drd]);
                if (measure_fast) begin
                    if (cycles - expected_first[drd] < latency_min) latency_min = cycles - expected_first[drd];
                    if (cycles - expected_first[drd] > latency_max) latency_max = cycles - expected_first[drd];
                    if (fast_results != 0) begin
                        if (cycles - last_result_cycle < fast_gap_min) fast_gap_min = cycles - last_result_cycle;
                        if (cycles - last_result_cycle > fast_gap_max) fast_gap_max = cycles - last_result_cycle;
                    end
                    fast_results = fast_results + 1; last_result_cycle = cycles;
                end
                drd = drd + 1; dot_outputs = dot_outputs + 1; total_dot_outputs = total_dot_outputs + 1;
            end
        end
        if (cycles > 2000000) $fatal(1, "Timeout");
    end

    task automatic reset_all;
        begin
            @(negedge clk); rst_n = 0; f_valid = 0; d_valid = 0;
            repeat (3) @(posedge clk);
            @(negedge clk); rst_n = 1; resets = resets + 1;
        end
    endtask

    task automatic send_factors(input integer count, input integer bubbles);
        integer k, gap;
        begin
            for (k = 0; k < count; k = k + 1) begin
                if (bubbles) begin
                    gap = $urandom % 3;
                    repeat (gap) begin @(negedge clk); f_valid = 0; end
                end
                @(negedge clk); f_valid = 1;
                fx_even = x[(k % 32)*2]; fx_odd = x[(k % 32)*2+1];
                fw_even = w[(k % 32)*2]; fw_odd = w[(k % 32)*2+1];
                do @(posedge clk); while (!fx_ready);
            end
            @(negedge clk); f_valid = 0;
        end
    endtask

    task automatic send_dots(input integer count, input integer bubbles);
        integer k, gap;
        begin
            for (k = 0; k < count; k = k + 1) begin
                if (bubbles) begin
                    gap = $urandom % 3;
                    repeat (gap) begin @(negedge clk); d_valid = 0; end
                end
                @(negedge clk); d_valid = 1;
                dx_even = x[(k % 32)*2]; dx_odd = x[(k % 32)*2+1];
                dw_even = w[(k % 32)*2]; dw_odd = w[(k % 32)*2+1];
                // Deliberately corrupt non-first metadata: it must be ignored.
                d_row = (k % 32 == 0) ? captured_row : ~captured_row;
                d_col = (k % 32 == 0) ? captured_col : ~captured_col;
                d_bias16 = (k % 32 == 0) ? frame_bias16 : ~frame_bias16;
                d_bias48 = (k % 32 == 0) ? frame_bias48 : ~frame_bias48;
                do @(posedge clk); while (!d16_ready);
            end
            @(negedge clk); d_valid = 0;
        end
    endtask

    function automatic integer edge_value(input integer code);
        case (code)
            0: edge_value = -128; 1: edge_value = -127; 2: edge_value = -1;
            3: edge_value = 0; 4: edge_value = 1; 5: edge_value = 126;
            default: edge_value = 127;
        endcase
    endfunction

    task automatic choose_bias(input integer index);
        case (index % 5)
            0: begin frame_bias16 = 0; frame_bias48 = 0; end
            1: begin frame_bias16 = 16'sh7fff; frame_bias48 = 48'sh7fffffffffff; end
            2: begin frame_bias16 = 16'sh8000; frame_bias48 = 48'sh800000000000; end
            3: begin frame_bias16 = -16'sd1; frame_bias48 = -48'sd1; end
            default: begin frame_bias16 = 16'($urandom); frame_bias48 = {$urandom, 16'($urandom)}; end
        endcase
    endtask

    task automatic run_case;
        integer f_target, d_target;
        begin
            choose_bias(cases);
            f_target = factor_outputs + 1; d_target = dot_outputs + 1;
            send_factors(32, 1); wait (factor_outputs == f_target);
            send_dots(32, 1); wait (dot_outputs == d_target);
            cases = cases + 1;
        end
    endtask

    integer a, b, c, d, k, n, target;
    initial begin
        if (!$value$plusargs("SEED=%d", seed)) seed = 1;
        junk = $urandom(seed);
        reset_all();
        for (a = 0; a < 7; a = a + 1)
          for (b = 0; b < 7; b = b + 1)
            for (c = 0; c < 7; c = c + 1)
              for (d = 0; d < 7; d = d + 1) begin
                for (k = 0; k < 32; k = k + 1) begin
                    x[2*k] = 8'(edge_value(a)); x[2*k+1] = 8'(edge_value(b));
                    w[2*k] = 8'(edge_value(c)); w[2*k+1] = 8'(edge_value(d));
                end
                run_case();
              end
        for (n = 0; n < 500; n = n + 1) begin
            for (k = 0; k < 64; k = k + 1) begin x[k] = 8'($urandom); w[k] = 8'($urandom); end
            run_case();
        end
        // Abort at early/middle/last accepted input; queues must restart empty.
        for (n = 1; n < 32; n = n + 15) begin
            send_factors(n, 0); reset_all(); run_case();
            send_dots(n, 0); reset_all(); run_case();
        end
        f_force_stall = 1;
        send_factors(32, 0); wait (fx_valid); repeat (12) @(posedge clk);
        reset_all(); f_force_stall = 0; run_case();
        d_force_stall = 1;
        send_dots(32, 0); wait (d16_valid); repeat (12) @(posedge clk);
        reset_all(); d_force_stall = 0; run_case();
        // Fill the one-entry multiply pipeline behind a blocked result.
        d_force_stall = 1;
        send_dots(33, 0); repeat (8) @(posedge clk);
        if (d16_ready) $fatal(1, "Expected input backpressure with full pipeline");
        @(negedge clk); d_valid = 1;
        repeat (5) @(posedge clk);
        reset_all(); d_force_stall = 0; run_case();
        // Hold an offered command through a stall, then resume without reset.
        d_force_stall = 1; target = dot_outputs + 2;
        fork
            send_dots(64, 0);
            begin wait (d16_valid); repeat (12) @(posedge clk); @(negedge clk); d_force_stall = 0; end
        join
        wait (dot_outputs == target);
        f_force_stall = 1; target = factor_outputs + 2;
        fork
            send_factors(64, 0);
            begin wait (fx_valid); repeat (12) @(posedge clk); @(negedge clk); f_force_stall = 0; end
        join
        wait (factor_outputs == target);
        // Sustained frames: factors hardware-computed once and reused legally.
        random_backpressure = 0; measure_fast = 1;
        target = dot_outputs + 40;
        send_dots(32*40, 0); wait (dot_outputs == target);
        measure_fast = 0;
        if (fast_gap_min != 32 || fast_gap_max != 32 || latency_min != 33 || latency_max != 33)
            $fatal(1, "Unexpected throughput/latency %0d/%0d %0d/%0d", fast_gap_min, fast_gap_max, latency_min, latency_max);
        $display("PASS cases=%0d factor_outputs=%0d dot_outputs=%0d resets=%0d stall_factor=%0d stall_dot=%0d inputwait_factor=%0d inputwait_dot=%0d fast_frames=%0d response_latency=%0d frame_ii=%0d cycles=%0d",
                 cases, total_factor_outputs, total_dot_outputs, resets, stalled_factor_cycles, stalled_dot_cycles,
                 factor_input_wait, dot_input_wait, fast_results, latency_min, fast_gap_min, cycles);
        $finish;
    end
endmodule
`default_nettype wire
