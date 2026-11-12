`timescale 1ns/1ps
// Production-configuration component regression. Expected values are generated
// by an independent Python integer model, never by the implementation under test.
module tb_candidate_stream;
    localparam ROWS=99, K=64, LANES=16, WORDS=ROWS*LANES/2;
    reg clk=0, rst_n=0;
    always #5 clk=~clk;
    reg input_write=0, input_pair=1, weight_write=0, meta_wr_en=0;
    reg [12:0] input_elem=0;
    reg [15:0] input_data=0, input_data_hi=0, meta_wr_data=0;
    reg [2:0] weight_pair=0;
    reg [5:0] weight_k=0, meta_wr_addr=0;
    reg [31:0] weight_word=0;
    reg block_pop=0, block_release=0;
    wire [7:0] block_remaining;
    wire block_valid, block_slot, block_has_row, block_next_valid;
    wire [31:0] block_data, block_next_data;
    wire weight_load_ok, meta_read_phase, accel_busy;
    reg cmd_valid=0, cmd_read=0, rsp_ready=0;
    reg [15:0] cmd_addr=0;
    reg [31:0] cmd_wdata=0;
    wire cmd_ready, rsp_valid, rsp_err;
    wire [31:0] rsp_data;
    qingyu_accel #(.ROWS(ROWS), .K(K), .LANES(LANES), .STREAM_MAC(1),
        .DOUBLE_BUFFER(1), .PIPE_MAC(1), .READ_AHEAD(1), .WEIGHT_STREAM(1), .OUT16(1)) dut (
        .clk(clk), .rst_n(rst_n), .input_write(input_write), .input_pair(input_pair),
        .input_elem(input_elem), .input_data(input_data), .input_data_hi(input_data_hi),
        .weight_write(weight_write), .weight_pair(weight_pair), .weight_k(weight_k),
        .weight_word(weight_word), .weight_load_ok(weight_load_ok),
        .meta_wr_en(meta_wr_en), .meta_wr_addr(meta_wr_addr), .meta_wr_data(meta_wr_data),
        .meta_read_phase(meta_read_phase), .block_pop(block_pop), .block_release(block_release),
        .block_remaining(block_remaining), .block_valid(block_valid), .block_slot(block_slot),
        .block_has_row(block_has_row), .block_data(block_data),
        .block_next_valid(block_next_valid), .block_next_data(block_next_data),
        .accel_busy(accel_busy), .icb_cmd_valid(cmd_valid), .icb_cmd_ready(cmd_ready),
        .icb_cmd_read(cmd_read), .icb_cmd_addr(cmd_addr), .icb_cmd_wdata(cmd_wdata),
        .icb_cmd_wmask(4'hf), .icb_rsp_valid(rsp_valid), .icb_rsp_ready(rsp_ready),
        .icb_rsp_rdata(rsp_data), .icb_rsp_err(rsp_err));

    reg [15:0] xs[0:ROWS*K-1], metadata[0:63];
    reg [31:0] ws[0:K*LANES/2-1], expected[0:WORDS-1];
    reg [31:0] rng=1, got;
    integer cases=3, outputs=0, bus_stalls=0, stream_stalls=0, fast_consumer=0;
    integer x_storage_checks=0, x_words_checked=0;
    integer overlap_cycles=0;
    integer case_id, compute_cycles;
    string vector_dir, filename;

    // Diagnostic instrumentation only; the expected-data checker above and
    // below depends solely on ports and independently generated vector files.
    always @(posedge clk)
        if(rst_n && dut.store_fire && dut.issue_stream) overlap_cycles=overlap_cycles+1;

    function automatic [31:0] advance(input [31:0] value);
        reg [31:0] t;
        begin t=value^(value<<13); t=t^(t>>17); advance=t^(t<<5); end
    endfunction

    // All requests and backpressure changes happen on falling edges, avoiding
    // testbench/DUT races. A stalled response must retain data, error and valid.
    task automatic access(input bit read_op, input [15:0] address, input [31:0] data);
        integer timeout_count, hold_cycles;
        reg [31:0] snapshot;
        reg error_snapshot;
        begin
            @(negedge clk);
            cmd_valid=1; cmd_read=read_op; cmd_addr=address; cmd_wdata=data; rsp_ready=0;
            timeout_count=0;
            @(posedge clk);
            while (!cmd_ready) begin
                timeout_count=timeout_count+1;
                if(timeout_count>50000) $fatal(1,"command timeout addr=%h",address);
                @(posedge clk);
            end
            @(negedge clk); cmd_valid=0;
            timeout_count=0;
            while (!rsp_valid) begin
                @(negedge clk); timeout_count=timeout_count+1;
                if(timeout_count>50000) $fatal(1,"response timeout addr=%h",address);
            end
            snapshot=rsp_data; error_snapshot=rsp_err;
            rng=advance(rng); hold_cycles=fast_consumer ? 0 : 1+(rng%7);
            repeat(hold_cycles) begin
                @(negedge clk); bus_stalls=bus_stalls+1;
                if(!rsp_valid || rsp_data!==snapshot || rsp_err!==error_snapshot)
                    $fatal(1,"ICB response changed under backpressure addr=%h",address);
            end
            if(error_snapshot) $fatal(1,"unexpected ICB error addr=%h",address);
            got=snapshot; rsp_ready=1;
            @(negedge clk); rsp_ready=0;
        end
    endtask

    task automatic load_inputs;
        integer i;
        begin
            for(i=0;i<ROWS*K;i=i+2) begin
                @(negedge clk);
                if(accel_busy) $fatal(1,"test attempted input load while busy");
                input_write=1; input_elem=i; input_data=xs[i]; input_data_hi=xs[i+1];
            end
            @(negedge clk); input_write=0;
        end
    endtask

    // Check the external storage contract, independently of physical banks.
    // Read every word after packed writes, rewrite through MMIO, then update
    // individual halfwords through the single-element streaming interface.
    task automatic check_input_storage;
        integer i;
        reg [31:0] wanted;
        begin
            for(i=0;i<ROWS*K;i=i+2) begin
                access(1,16'h1000+2*i,0);
                wanted={xs[i+1],xs[i]};
                if(got!==wanted) $fatal(1,"packed input readback index=%0d got=%h expected=%h",i,got,wanted);
                x_words_checked=x_words_checked+1;
                access(0,16'h1000+2*i,~wanted);
            end
            for(i=0;i<ROWS*K;i=i+2) begin
                access(1,16'h1000+2*i,0);
                wanted=~{xs[i+1],xs[i]};
                if(got!==wanted) $fatal(1,"MMIO input readback index=%0d got=%h expected=%h",i,got,wanted);
                x_words_checked=x_words_checked+1;
            end
            for(i=0;i<ROWS*K;i=i+1) begin
                @(negedge clk);
                input_write=1; input_pair=0; input_elem=i;
                input_data=xs[i]; input_data_hi=16'h5a5a;
            end
            @(negedge clk); input_write=0; input_pair=1;
            for(i=ROWS*K-2;i>=0;i=i-2) begin
                access(1,16'h1000+2*i,0);
                wanted={xs[i+1],xs[i]};
                if(got!==wanted) $fatal(1,"single input readback index=%0d got=%h expected=%h",i,got,wanted);
                x_words_checked=x_words_checked+1;
            end
        end
    endtask

    task automatic load_parameters;
        integer i;
        begin
            for(i=0;i<K*LANES/2;i=i+1) begin
                @(negedge clk);
                if(!weight_load_ok) $fatal(1,"weight loader unavailable");
                weight_write=1; weight_k=i/8; weight_pair=i%8; weight_word=ws[i];
            end
            @(negedge clk); weight_write=0;
            for(i=0;i<64;i=i+1) begin
                @(negedge clk);
                if(meta_read_phase) $fatal(1,"metadata conflict");
                meta_wr_en=1; meta_wr_addr=i; meta_wr_data=metadata[i];
            end
            @(negedge clk); meta_wr_en=0;
        end
    endtask

    task automatic assert_reset_empty;
        begin
            if(accel_busy || block_valid) $fatal(1,"stale compute/output after reset");
            access(1,16'h0008,0); if(got!==0) $fatal(1,"status survived reset");
            access(1,16'h0020,0); if(got!==0) $fatal(1,"slot A survived reset");
            access(1,16'h0024,0); if(got!==0) $fatal(1,"slot B survived reset");
        end
    endtask

    task automatic wait_first_output;
        integer timeout_count;
        begin
            timeout_count=0;
            while(!block_valid) begin
                @(negedge clk); timeout_count=timeout_count+1;
                if(timeout_count>20000) $fatal(1,"first output timeout");
            end
        end
    endtask

    task automatic consume_outputs;
        integer base, j, count, stalled, timeout_count;
        reg expected_slot;
        reg [31:0] snapshot;
        begin
            base=0; expected_slot=0;
            while(base<WORDS) begin
                count=(WORDS-base<64) ? WORDS-base : 64;
                wait_first_output();
                if(block_slot!==expected_slot || block_remaining!==count || !block_has_row)
                    $fatal(1,"wrong batch metadata base=%0d slot=%b remaining=%0d expected=%0d",
                        base,block_slot,block_remaining,count);
                // Indexed reads inspect the same SRAM without consuming the
                // stream head. Read both ends of each slot, including the tail.
                if(!fast_consumer) begin
                    access(1,16'h7000+512*expected_slot,0);
                    if(got!==expected[base]) $fatal(1,"indexed first word mismatch base=%0d",base);
                    access(1,16'h7000+512*expected_slot+4*(count-1),0);
                    if(got!==expected[base+count-1]) $fatal(1,"indexed last word mismatch base=%0d",base);
                    if(block_remaining!==count) $fatal(1,"indexed read consumed stream data");
                end
                for(j=0;j<count;j=j+1) begin
                    timeout_count=0;
                    while(!block_valid) begin
                        @(negedge clk); timeout_count=timeout_count+1;
                        if(timeout_count>20000) $fatal(1,"output timeout at %0d",base+j);
                    end
                    snapshot=block_data;
                    rng=advance(rng); stalled=fast_consumer ? 0 : rng%8;
                    repeat(stalled) begin
                        @(negedge clk); stream_stalls=stream_stalls+1;
                        if(!block_valid || block_data!==snapshot || block_slot!==expected_slot)
                            $fatal(1,"stream changed under backpressure at %0d",base+j);
                    end
                    if(snapshot!==expected[base+j])
                        $fatal(1,"mismatch case=%0d word=%0d actual=%h expected=%h",
                            case_id,base+j,snapshot,expected[base+j]);
                    block_pop=1;
                    @(negedge clk); block_pop=0;
                    outputs=outputs+2;
                end
                repeat(3) @(negedge clk);
                if(block_remaining!==0 || block_valid || block_has_row)
                    $fatal(1,"extra data past batch boundary base=%0d",base);
                block_release=1;
                @(negedge clk); block_release=0;
                base=base+count; expected_slot=!expected_slot;
            end
            repeat(5) @(negedge clk);
            access(1,16'h0008,0);
            if(got!==2) $fatal(1,"completion status=%h",got);
            access(1,16'h001c,0);
            if(got!==ROWS*LANES) $fatal(1,"wrong output count=%0d",got);
            access(1,16'h0018,0); compute_cycles=got;
            access(1,16'h0020,0); if(got!==0) $fatal(1,"unreleased slot A");
            access(1,16'h0024,0); if(got!==0) $fatal(1,"unreleased slot B");
            $display("CANDIDATE_CASE case=%0d outputs=%0d compute_cycles=%0d",case_id,ROWS*LANES,compute_cycles);
        end
    endtask

    initial begin
        if(!$value$plusargs("VECTORS=%s",vector_dir)) $fatal(1,"VECTORS required");
        if($value$plusargs("CASES=%d",cases)) begin end
        if($value$plusargs("SEED=%d",rng)) begin end
        if($value$plusargs("FAST=%d",fast_consumer)) begin end
        if($value$plusargs("X_STORAGE=%d",x_storage_checks)) begin end
        if(rng==0) rng=1;
        repeat(4) @(negedge clk); rst_n=1;
        assert_reset_empty();
        for(case_id=0;case_id<cases;case_id=case_id+1) begin
            filename=$sformatf("%s/case%02d_x.hex",vector_dir,case_id); $readmemh(filename,xs);
            filename=$sformatf("%s/case%02d_w.hex",vector_dir,case_id); $readmemh(filename,ws);
            filename=$sformatf("%s/case%02d_meta.hex",vector_dir,case_id); $readmemh(filename,metadata);
            filename=$sformatf("%s/case%02d_expected.hex",vector_dir,case_id); $readmemh(filename,expected);
            load_inputs();
            if(x_storage_checks && case_id<2) check_input_storage();
            load_parameters();
            access(0,16'h000c,case_id%12); access(0,16'h0010,16*(case_id%16));
            access(0,16'h0004,3);
            if(case_id==0) begin
                // Hold output long enough to fill both double-buffer slots;
                // abort with a full producer/consumer boundary, then reload.
                wait_first_output(); repeat(2500) @(negedge clk);
                access(1,16'h0020,0); if(got!==64) $fatal(1,"first full slot missing");
                access(1,16'h0024,0); if(got!==64) $fatal(1,"second full slot missing");
                access(0,16'h0004,4); assert_reset_empty();
                load_inputs(); load_parameters(); access(0,16'h0004,3);
            end else if(case_id==1) begin
                // Abort while the MAC has in-flight products and a status
                // response is held by a stalled bus consumer.
                repeat(23) @(negedge clk);
                if(!accel_busy) $fatal(1,"reset was not exercised during computation");
                cmd_valid=1; cmd_read=1; cmd_addr=16'h0008; cmd_wdata=0; rsp_ready=0;
                @(posedge clk); while(!cmd_ready) @(posedge clk);
                @(negedge clk); cmd_valid=0;
                while(!rsp_valid) @(negedge clk);
                rst_n=0; repeat(3) @(negedge clk); rst_n=1;
                if(rsp_valid) $fatal(1,"stalled response survived hardware reset");
                assert_reset_empty(); load_inputs(); load_parameters(); access(0,16'h0004,3);
            end
            consume_outputs();
        end
        // No parameter writes: START must reuse the resident W bank correctly.
        access(0,16'h0004,3); consume_outputs();
        $display("PASS candidate_stream synthetic outputs=%0d cases=%0d bus_stall_cycles=%0d stream_stall_cycles=%0d overlap_cycles=%0d soft_abort=1 hard_abort=1 resident_restart=1",
            outputs,cases,bus_stalls,stream_stalls,overlap_cycles);
        $display("X_STORAGE words_checked=%0d",x_words_checked);
        $finish;
    end
    initial begin #100000000; $fatal(1,"global timeout"); end
endmodule
