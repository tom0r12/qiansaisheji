`timescale 1ns/1ps
`default_nettype none
module winograd_int8_task8 (
    input logic clk, rst_n,
    input logic begin_valid, output logic begin_ready,
    input logic x_valid, output logic x_ready, input logic [31:0] x_data,
    input logic w_valid, output logic w_ready, input logic [31:0] w_data,
    input logic meta_valid, output logic meta_ready, input logic [31:0] meta_data,
    output logic [2:0] pair_group,
    output logic [1:0] pair_slot_base,
    output logic x_done, pair_loaded, pair_done,
    output logic [2:0] pair_done_index,
    output logic out_valid, input logic out_ready, output logic [31:0] out_data,
    output logic [3:0] out_tile, output logic [8:0] out_word_index,
    output logic busy, done, error,
    output logic [31:0] total_cycles, load_cycles, factor_cycles,
    output logic [31:0] cache_read_cycles, compute_cycles, store_cycles
);
    localparam logic [3:0] IDLE=0, X_LOAD=1, X_DRAIN=2, WAIT_SLOT=3,
        M_READ=6, M_WAIT=7, DOT_READ=10, DOT_WAIT=11, TILE_DRAIN=12, ERROR_DRAIN=13;
    localparam logic [2:0] L_OFF=0,L_W=1,L_META=2,L_COMMIT=3,L_ADVANCE=4,L_WAIT=5,L_DONE=6,L_DRAIN=7;
    localparam logic TAG_M=0, TAG_D=1;
    logic [3:0] state_q, row_group_q;
    logic [2:0] loader_q;
    logic [3:0] compute_tile_q;
    logic [10:0] x_count_q;
    logic [8:0] w_count_q;
    logic [4:0] meta_count_q, meta_write_q, pair_q;
    logic [3:0] meta_read_q;
    logic [3:0] store_row_q;
    logic [3:0] x_low_bank_q,x_load_group_q;
    wire [3:0] x_high_bank = x_low_bank_q==8 ? 4'd0 : x_low_bank_q+4'd1;
    wire [3:0] x_high_group = x_load_group_q+(x_low_bank_q==8 ? 4'd1 : 4'd0);
    logic [1:0] store_word_q;
    logic x_epoch_q,load_meta_bad_q;
    logic [3:0] slot_valid_q;
    logic [3:0] slot_tile_q [0:3];
    logic signed [15:0] bias_load_q [0:31], active_bias_q [0:15];
    logic [7:0] shift_load_q [0:31], active_shift_q [0:15];
    logic signed [20:0] active_c_q [0:15], active_r_q [0:8];
    logic signed [20:0] c_acc_q [0:31], r_acc_lo_q, r_acc_hi_q;
    logic [31:0] c_complete_q;
    logic product_valid_q, product_x_q, product_first_q, product_last_q, product_hi_valid_q;
    logic signed [15:0] product_lo_q, product_hi_q;
    logic [6:0] product_row_q;
    logic [4:0] product_col_q;
    logic product_sink_ready, product_ready, product_fire;
    logic signed [20:0] product_lo_ext, product_hi_ext, r_sum_lo, r_sum_hi;
    logic [1:0] r_pending_q;
    logic signed [20:0] r_pending_value_q [0:1];
    logic [6:0] r_pending_row_q [0:1];
    logic [6:0] r_written_q;
    logic r_cache_write, begin_fire, x_fire, w_fire, meta_fire, new_pair;
    logic load_start,metadata_fault,slot_commit,metadata_grant,tile_final_ack,target_pair_free;
    logic [255:0] burst_data_q [0:2];
    logic [6:0] burst_addr_q [0:2];
    logic [2:0] burst_ready_q;
    logic [1:0] burst_fill_q,burst_drain_q;
    logic [2:0] burst_fill_word_q;
    logic [6:0] bursts_written_q;
    logic burst_write,all_w_committed;
    logic [31:0] factor_word;
    logic [3:0] active_rows, snapshot_rows;
    logic [1:0] active_slot, load_slot;
    logic slot_matches, read_issue, meta_bad;
    logic rd_valid_q, rd_first_q, rd_last_q;
    logic rd_tag_q;
    logic [3:0] rd_index_q;
    logic r_read_valid_q;
    logic [3:0] r_read_index_q;
    logic [8:0] x_en, x_we;
    logic [15:0] w_en, w_we;
    logic [9:0] x_addr [0:8];
    logic [6:0] w_addr [0:15];
    logic [15:0] x_wdata [0:8], w_wdata [0:15];
    wire [15:0] x_rdata [0:8], w_rdata [0:15];
    logic r_en, r_we, m_en, m_we;
    logic [6:0] r_addr, m_addr;
    logic [31:0] r_wdata;
    wire [31:0] r_rdata;
    logic [47:0] m_wdata;
    wire [47:0] m_rdata;
    wire unused_cache_padding = ^{r_rdata[31:21],m_rdata[47:45]};
    wire [143:0] pe_in_ready, pe_out_valid;
    logic [143:0] pe_out_ready;
    wire [3311:0] pe_sum_flat;
    logic [3311:0] snapshot_sum_q;
    logic signed [20:0] snapshot_r_q [0:8];
    logic [3:0] snapshot_group_q,snapshot_tile_q;
    logic snapshot_valid_q,snapshot_capture,snapshot_last_ack;
    logic dot_all_valid, dot_all_valid_delayed_q, core_rst_n;
    logic signed [22:0] selected_sum [0:3];
    logic signed [23:0] corrected [0:3];
    integer i, lane, pe_index;

    assign busy = state_q != IDLE;
    assign begin_ready = rst_n && state_q == IDLE;
    assign begin_fire = begin_valid && begin_ready;
    assign core_rst_n = rst_n && state_q != IDLE;
    assign pair_slot_base = {pair_group[0],1'b0};
    assign active_slot = compute_tile_q[1:0];
    assign load_slot = {pair_group[0],w_count_q[3]};
    assign out_tile = snapshot_tile_q;
    assign active_rows = 4'd9;
    assign slot_matches = slot_valid_q[active_slot] && slot_tile_q[active_slot] == compute_tile_q;
    assign snapshot_rows = 4'd9;
    assign snapshot_last_ack = out_valid && out_ready && store_word_q==3 && store_row_q+4'd1==snapshot_rows;
    assign snapshot_capture = state_q==DOT_WAIT && dot_all_valid && dot_all_valid_delayed_q && (!snapshot_valid_q || snapshot_last_ack) && !error && !metadata_fault;
    assign product_sink_ready = !product_x_q || !product_last_q || r_pending_q == 0;
    assign product_ready = !product_valid_q || product_sink_ready;
    assign product_fire = product_valid_q && product_sink_ready;
    assign x_ready = rst_n && state_q == X_LOAD && product_ready;
    assign w_ready = rst_n && loader_q==L_W && product_ready && !burst_ready_q[burst_fill_q] && !error;
    assign meta_ready = rst_n && loader_q==L_META && !error;
    assign x_fire = x_valid && x_ready;
    assign w_fire = w_valid && w_ready;
    assign meta_fire = meta_valid && meta_ready;
    assign factor_word = x_fire ? x_data : w_data;
    assign product_lo_ext = {{5{product_lo_q[15]}},product_lo_q};
    assign product_hi_ext = {{5{product_hi_q[15]}},product_hi_q};
    assign r_sum_lo = (product_first_q ? 21'sd0 : r_acc_lo_q) + product_lo_ext;
    assign r_sum_hi = (product_first_q ? 21'sd0 : r_acc_hi_q) + product_hi_ext;
    assign r_cache_write = rst_n && r_pending_q != 0 && (state_q == X_LOAD || state_q == X_DRAIN);
    assign new_pair = loader_q==L_ADVANCE && pair_group!=7;
    assign load_start = state_q==X_DRAIN && r_written_q==99 && r_pending_q==0 && !product_valid_q;
    assign target_pair_free = !slot_valid_q[pair_slot_base] && !slot_valid_q[pair_slot_base+2'd1];
    assign burst_write = rst_n && burst_ready_q[burst_drain_q] && state_q!=DOT_READ && !error && !metadata_fault;
    assign all_w_committed = bursts_written_q==64 || (bursts_written_q==63 && burst_write);
    assign metadata_grant = rst_n && loader_q==L_COMMIT && state_q!=M_READ && !error && !metadata_fault;
    assign metadata_fault = meta_fire && meta_count_q==23 && (load_meta_bad_q || meta_bad || !(&c_complete_q));
    assign slot_commit = !error && ((metadata_grant && meta_write_q==31 && all_w_committed) || (loader_q==L_DRAIN && all_w_committed));
    assign tile_final_ack = state_q==TILE_DRAIN && snapshot_last_ack;
    assign meta_bad = meta_data[7:0]>8'd47 || meta_data[15:8]>8'd47 || meta_data[23:16]>8'd47 || meta_data[31:24]>8'd47;
    assign read_issue = (state_q == M_READ && slot_matches) || state_q == DOT_READ;

    // The source retains its two-row stream. An odd bank count requires an
    // explicit bounded bank/group carry, not bank parity or a division unit.
    always_ff @(posedge clk) begin
        if(!rst_n || begin_fire) begin x_low_bank_q<=0;x_load_group_q<=0;end
        else if(x_fire && x_count_q[4:0]==31) begin
            if(x_low_bank_q>=7) begin x_low_bank_q<=x_low_bank_q-4'd7;x_load_group_q<=x_load_group_q+1;end
            else x_low_bank_q<=x_low_bank_q+4'd2;
        end
    end

    // Two products per accepted load word. No software factor data port exists.
    always_ff @(posedge clk) begin
        if (!rst_n || begin_fire) begin
            product_valid_q<=0; product_x_q<=0; product_first_q<=0; product_last_q<=0;
            product_hi_valid_q<=0; product_lo_q<=0; product_hi_q<=0; product_row_q<=0; product_col_q<=0;
        end else if (product_ready) begin
            product_valid_q <= x_fire || w_fire;
            if (x_fire || w_fire) begin
                product_lo_q <= $signed(factor_word[7:0]) * $signed(factor_word[15:8]);
                product_hi_q <= $signed(factor_word[23:16]) * $signed(factor_word[31:24]);
                product_x_q <= x_fire;
                product_first_q <= x_fire ? x_count_q[4:0]==0 : w_count_q[8:4]==0;
                product_last_q <= x_fire ? x_count_q[4:0]==31 : w_count_q[8:4]==31;
                product_hi_valid_q <= !x_fire || x_count_q[10:5]!=49;
                product_row_q <= {x_count_q[10:5],1'b0};
                product_col_q <= {w_count_q[3:0],1'b0};
            end
        end
    end
    always_ff @(posedge clk) begin
        if (!rst_n || begin_fire) begin
            r_acc_lo_q<=0; r_acc_hi_q<=0; r_pending_q<=0; r_written_q<=0; c_complete_q<=0;
            for (integer q=0;q<2;q=q+1) begin r_pending_value_q[q]<=0; r_pending_row_q[q]<=0; end
            for (integer c=0;c<32;c=c+1) c_acc_q[c]<=0;
        end else begin
            if (new_pair) c_complete_q<=0;
            if (r_cache_write) begin
                r_written_q<=r_written_q+1'b1; r_pending_q<=r_pending_q-1'b1;
                r_pending_value_q[0]<=r_pending_value_q[1]; r_pending_row_q[0]<=r_pending_row_q[1];
            end
            if (product_fire) begin
                if (product_x_q) begin
                    r_acc_lo_q<=r_sum_lo;
                    if (product_hi_valid_q) r_acc_hi_q<=r_sum_hi;
                    if (product_last_q) begin
                        r_pending_q<=product_hi_valid_q ? 2'd2 : 2'd1;
                        r_pending_value_q[0]<=r_sum_lo; r_pending_value_q[1]<=r_sum_hi;
                        r_pending_row_q[0]<=product_row_q; r_pending_row_q[1]<=product_row_q+7'd1;
                    end
                end else begin
                    c_acc_q[product_col_q] <= (product_first_q ? 21'sd0 : c_acc_q[product_col_q]) + product_lo_ext;
                    c_acc_q[product_col_q+5'd1] <= (product_first_q ? 21'sd0 : c_acc_q[product_col_q+5'd1]) + product_hi_ext;
                    if (product_last_q) begin c_complete_q[product_col_q]<=1; c_complete_q[product_col_q+5'd1]<=1; end
                end
            end
        end
    end

    // Three bounded burst contexts match three non-read DOT_WAIT edges. A full
    // context writes every W bank on one
    // actual non-read edge; no SRAM ever reads and writes simultaneously.
    always_ff @(posedge clk) begin
        if(!rst_n || begin_fire || new_pair || error || metadata_fault) begin
            burst_ready_q<=0;burst_fill_q<=0;burst_drain_q<=0;burst_fill_word_q<=0;bursts_written_q<=0;
            for(integer b=0;b<3;b=b+1) begin burst_data_q[b]<=0;burst_addr_q[b]<=0;end
        end else begin
            if(w_fire) begin
                burst_data_q[burst_fill_q][int'(burst_fill_word_q)*32+:32]<=w_data;
                burst_fill_word_q<=burst_fill_word_q+1;
                if(burst_fill_word_q==7) begin
                    burst_ready_q[burst_fill_q]<=1;burst_addr_q[burst_fill_q]<={load_slot,w_count_q[8:4]};
                    burst_fill_q<=burst_fill_q==2 ? 2'd0 : burst_fill_q+2'd1;
                end
            end
            if(burst_write) begin
                burst_ready_q[burst_drain_q]<=0;burst_drain_q<=burst_drain_q==2 ? 2'd0 : burst_drain_q+2'd1;bursts_written_q<=bursts_written_q+1;
            end
        end
    end

    // Loading has its own logical group and progress. The committed pulse
    // retains that group's identity; L_ADVANCE moves the target one edge later.
    always_ff @(posedge clk) begin
        if(!rst_n || begin_fire) begin
            loader_q<=L_OFF;pair_group<=0;pair_loaded<=0;w_count_q<=0;meta_count_q<=0;meta_write_q<=0;load_meta_bad_q<=0;
            for(integer c=0;c<32;c=c+1) begin bias_load_q[c]<=0;shift_load_q[c]<=0;end
        end else begin
            pair_loaded<=0;
            if(error || metadata_fault) loader_q<=L_OFF;
            else case(loader_q)
                L_OFF: if(load_start) begin loader_q<=L_W;w_count_q<=0;end
                L_W: if(w_fire) begin
                    w_count_q<=w_count_q+1;
                    if(w_count_q==511) begin loader_q<=L_META;meta_count_q<=0;end
                end
                L_META: if(meta_fire) begin
                    meta_count_q<=meta_count_q+1;
                    for(integer c=0;c<32;c=c+1) begin
                        if(meta_count_q==5'(c/2)) bias_load_q[c]<=meta_data[(c%2)*16+:16];
                        if(meta_count_q==5'(16+c/4)) shift_load_q[c]<=meta_data[(c%4)*8+:8];
                    end
                    if(meta_count_q>=16 && meta_bad) load_meta_bad_q<=1;
                    if(meta_count_q==23) begin loader_q<=L_COMMIT;meta_write_q<=0;end
                end
                L_COMMIT: if(metadata_grant) begin
                    meta_write_q<=meta_write_q+1;
                    if(meta_write_q==31) begin
                        if(all_w_committed) begin loader_q<=L_ADVANCE;pair_loaded<=1;end
                        else loader_q<=L_DRAIN;
                    end
                end
                L_DRAIN: if(all_w_committed) begin loader_q<=L_ADVANCE;pair_loaded<=1;end
                L_ADVANCE: begin
                    if(pair_group==7) loader_q<=L_DONE;
                    else begin pair_group<=pair_group+1;w_count_q<=0;load_meta_bad_q<=0;loader_q<=L_WAIT;end
                end
                L_WAIT: if(target_pair_free) loader_q<=L_W;
                L_DONE: begin end
                default: loader_q<=L_OFF;
            endcase
        end
    end
    always_ff @(posedge clk) begin
        if(!rst_n || begin_fire || error || metadata_fault) begin
            slot_valid_q<=0;
            for(integer s=0;s<4;s=s+1) slot_tile_q[s]<=0;
        end else begin
            if(slot_commit) begin
                slot_valid_q[pair_slot_base]<=1;slot_valid_q[pair_slot_base+2'd1]<=1;
                slot_tile_q[pair_slot_base]<={pair_group,1'b0};slot_tile_q[pair_slot_base+2'd1]<={pair_group,1'b1};
            end
            if(tile_final_ack) slot_valid_q[active_slot]<=0;
        end
    end

    always_comb begin
        x_en=0; x_we=0; w_en=0; w_we=0;
        for (integer r=0;r<9;r=r+1) begin
            x_addr[r]={1'b0,row_group_q,pair_q};
            x_wdata[r]=0;
            if(x_fire && x_low_bank_q==4'(r)) begin
                x_en[r]=1;x_we[r]=1;x_addr[r]={1'b0,x_load_group_q,x_count_q[4:0]};x_wdata[r]=x_data[15:0];
            end else if(x_fire && x_high_bank==4'(r) && x_count_q[10:5]!=49) begin
                x_en[r]=1;x_we[r]=1;x_addr[r]={1'b0,x_high_group,x_count_q[4:0]};x_wdata[r]=x_data[31:16];
            end else if (rst_n && state_q==DOT_READ && 4'(r)<active_rows) x_en[r]=1;
        end
        for (integer c=0;c<16;c=c+1) begin
            w_addr[c]={active_slot,pair_q};
            w_wdata[c]=burst_data_q[burst_drain_q][c*16+:16];
            if (burst_write) begin
                w_en[c]=1; w_we[c]=1; w_addr[c]=burst_addr_q[burst_drain_q];
            end else if (rst_n && state_q==DOT_READ) w_en[c]=1;
        end
        r_en=0; r_we=0; r_addr=7'(row_group_q)*7'd9+{3'b0,pair_q[3:0]};
        r_wdata={{11{r_pending_value_q[0][20]}},r_pending_value_q[0]};
        if (r_cache_write) begin r_en=1; r_we=1; r_addr=r_pending_row_q[0]; end
        else if (rst_n && state_q==DOT_READ && x_epoch_q && {1'b0,pair_q}<{2'b0,active_rows}) r_en=1;
        m_en=0; m_we=0; m_addr={1'b0,active_slot,meta_read_q};
        m_wdata={3'b0,shift_load_q[meta_write_q],bias_load_q[meta_write_q],c_acc_q[meta_write_q]};
        if (rst_n && state_q==M_READ && slot_matches) m_en=1;
        else if (metadata_grant) begin m_en=1; m_we=1; m_addr={1'b0,pair_group[0],meta_write_q}; end
    end
    generate
        for (genvar r=0;r<9;r=r+1) begin: x_bank
            qingyu_sram16 #(.DEPTH(1024),.ADDR_W(10)) memory(.clk,.en(x_en[r]),.we(x_we[r]),.addr(x_addr[r]),.wdata(x_wdata[r]),.rdata(x_rdata[r]));
            for (genvar c=0;c<16;c=c+1) begin: lane
                winograd_int8_pair_acc32_single pe(.clk,.rst_n(core_rst_n),
                    .in_valid(rd_valid_q && rd_tag_q==TAG_D && 4'(r)<active_rows),.in_ready(pe_in_ready[r*16+c]),
                    .in_first(rd_first_q),.in_last(rd_last_q),
                    .in_x_even(x_rdata[r][7:0]),.in_x_odd(x_rdata[r][15:8]),
                    .in_w_even(w_rdata[c][7:0]),.in_w_odd(w_rdata[c][15:8]),
                    .out_valid(pe_out_valid[r*16+c]),.out_ready(pe_out_ready[r*16+c]),.out_pair_sum(pe_sum_flat[(r*16+c)*23+:23]));
            end
        end
        for (genvar c=0;c<16;c=c+1) begin: w_bank
            qingyu_sram16 #(.DEPTH(128),.ADDR_W(7)) memory(.clk,.en(w_en[c]),.we(w_we[c]),.addr(w_addr[c]),.wdata(w_wdata[c]),.rdata(w_rdata[c]));
        end
        for (genvar b=0;b<2;b=b+1) begin: r_cache
            qingyu_sram16 #(.DEPTH(128),.ADDR_W(7)) memory(.clk,.en(r_en),.we(r_we),.addr(r_addr),.wdata(r_wdata[b*16+:16]),.rdata(r_rdata[b*16+:16]));
        end
        for (genvar b=0;b<3;b=b+1) begin: metadata_cache
            qingyu_sram16 #(.DEPTH(128),.ADDR_W(7)) memory(.clk,.en(m_en),.we(m_we),.addr(m_addr),.wdata(m_wdata[b*16+:16]),.rdata(m_rdata[b*16+:16]));
        end
    endgenerate
    always_comb begin
        dot_all_valid=1;
        for (integer r=0;r<9;r=r+1) if (4'(r)<active_rows) dot_all_valid=dot_all_valid && (&pe_out_valid[r*16+:16]);
    end

    // Preserve all original W-prefetch write slots before snapshot capture.
    always_ff @(posedge clk) begin
        if(!core_rst_n)dot_all_valid_delayed_q<=1'b0;
        else dot_all_valid_delayed_q<=dot_all_valid;
    end

    function automatic logic [7:0] requantize(input logic signed [23:0] value,input logic [7:0] shift);
        logic [24:0] magnitude,quotient,remainder,halfway;
        logic signed [25:0] rounded;
        begin
            magnitude=value[23] ? {1'b0,~value}+25'd1 : {1'b0,value};
            quotient=0; remainder=0; halfway=0; rounded=0;
            if (shift==0) rounded={{2{value[23]}},value};
            else if (shift<24) begin
                quotient=magnitude>>shift; remainder=magnitude&((25'd1<<shift)-25'd1); halfway=25'd1<<(shift-8'd1);
                if (remainder>halfway || (remainder==halfway && quotient[0])) quotient=quotient+25'd1;
                rounded=value[23] ? -$signed({1'b0,quotient}) : $signed({1'b0,quotient});
            end
            if (rounded>26'sd127) requantize=8'h7f;
            else if (rounded < -26'sd128) requantize=8'h80;
            else requantize=rounded[7:0];
        end
    endfunction
    always_comb begin
        out_valid=snapshot_valid_q; out_word_index=9'(snapshot_group_q)*9'd36+{3'b0,store_row_q,store_word_q}; out_data=0; pe_out_ready=0;
        lane=0; pe_index=0;
        for (integer b=0;b<4;b=b+1) begin
            lane=int'(store_word_q)*4+b; pe_index=int'(store_row_q)*16+lane;
            selected_sum[b]=snapshot_sum_q[pe_index*23+:23];
            corrected[b]={selected_sum[b][22],selected_sum[b]}
                -{{3{snapshot_r_q[store_row_q][20]}},snapshot_r_q[store_row_q]}
                -{{3{active_c_q[lane][20]}},active_c_q[lane]}+{{8{active_bias_q[lane][15]}},active_bias_q[lane]};
            out_data[b*8+:8]=requantize(corrected[b],active_shift_q[lane]);
        end
        if (snapshot_capture) for (integer r=0;r<9;r=r+1)
            if(4'(r)<active_rows) pe_out_ready[r*16+:16]=16'hffff;
    end

    // A single explicit output snapshot frees the raw lanes for the next row
    // group. Factors and logical output identity travel with the raw sums.
    always_ff @(posedge clk) begin
        if (!rst_n || begin_fire) begin
            snapshot_valid_q<=0;snapshot_sum_q<=0;snapshot_group_q<=0;snapshot_tile_q<=0;
            store_row_q<=0;store_word_q<=0;
            for(integer r=0;r<9;r=r+1) snapshot_r_q[r]<=0;
        end else begin
            if(out_valid && out_ready) begin
                store_word_q<=store_word_q+1;
                if(store_word_q==3) store_row_q<=store_row_q+1;
                if(snapshot_last_ack) snapshot_valid_q<=0;
            end
            if(snapshot_capture) begin
                snapshot_valid_q<=1;snapshot_sum_q<=pe_sum_flat;snapshot_group_q<=row_group_q;snapshot_tile_q<=compute_tile_q;
                store_row_q<=0;store_word_q<=0;
                for(integer r=0;r<9;r=r+1) snapshot_r_q[r]<=active_r_q[r];
            end
        end
    end

    always_ff @(posedge clk) begin
        if (!core_rst_n) begin rd_valid_q<=0; rd_tag_q<=0; rd_index_q<=0; rd_first_q<=0; rd_last_q<=0;r_read_valid_q<=0;r_read_index_q<=0;end
        else begin
            rd_valid_q<=read_issue;
            r_read_valid_q<=r_en && !r_we;
            if(r_en && !r_we) r_read_index_q<=pair_q[3:0];
            if (read_issue) begin
                rd_tag_q<=state_q==M_READ ? TAG_M : TAG_D;
                rd_index_q<=state_q==M_READ ? meta_read_q : 4'b0;
                rd_first_q<=pair_q==0;
                rd_last_q<=state_q==M_READ ? meta_read_q==15 : pair_q==31;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state_q<=IDLE; x_count_q<=0; meta_read_q<=0;
            row_group_q<=0; pair_q<=0; compute_tile_q<=0;
            pair_done_index<=0; x_epoch_q<=0;
            done<=0; error<=0; x_done<=0; pair_done<=0;
            total_cycles<=0; load_cycles<=0; factor_cycles<=0; cache_read_cycles<=0; compute_cycles<=0; store_cycles<=0;
            for (i=0;i<16;i=i+1) begin active_c_q[i]<=0; active_bias_q[i]<=0; active_shift_q[i]<=0; end
            for (i=0;i<9;i=i+1) active_r_q[i]<=0;
        end else begin
            done<=0; x_done<=0; pair_done<=0;
            if (busy) total_cycles<=total_cycles+1;
            case(state_q)
                X_LOAD: load_cycles<=load_cycles+1;
                X_DRAIN: factor_cycles<=factor_cycles+1;
                WAIT_SLOT: begin
                    if(loader_q==L_COMMIT || loader_q==L_DRAIN) factor_cycles<=factor_cycles+1;
                    else load_cycles<=load_cycles+1;
                end
                M_READ,M_WAIT: cache_read_cycles<=cache_read_cycles+1;
                DOT_READ,DOT_WAIT: compute_cycles<=compute_cycles+1;
                TILE_DRAIN,ERROR_DRAIN: store_cycles<=store_cycles+1;
                default: begin end
            endcase
            if (rd_valid_q && rd_tag_q==TAG_M) begin
                active_c_q[rd_index_q[3:0]]<=m_rdata[20:0];
                active_bias_q[rd_index_q[3:0]]<=m_rdata[36:21]; active_shift_q[rd_index_q[3:0]]<=m_rdata[44:37];
            end
            if (r_read_valid_q) active_r_q[r_read_index_q]<=r_rdata[20:0];
            if(metadata_fault) begin
                error<=1;
                if(!snapshot_valid_q || snapshot_last_ack) begin state_q<=IDLE;done<=1;end
                else state_q<=ERROR_DRAIN;
            end else case(state_q)
                IDLE: if (begin_valid) begin
                    state_q<=X_LOAD; x_count_q<=0; meta_read_q<=0;
                    row_group_q<=0; pair_q<=0;
                    compute_tile_q<=0; x_epoch_q<=0; error<=0;
                    total_cycles<=0; load_cycles<=0; factor_cycles<=0; cache_read_cycles<=0; compute_cycles<=0; store_cycles<=0;
                end
                X_LOAD: if (x_fire) begin x_count_q<=x_count_q+1; if (x_count_q==1599) state_q<=X_DRAIN; end
                X_DRAIN: if(load_start) begin x_epoch_q<=1;x_done<=1;state_q<=WAIT_SLOT;end
                WAIT_SLOT: if(slot_matches) begin meta_read_q<=0;row_group_q<=0;state_q<=M_READ;end
                M_READ: begin
                    if (!slot_matches) begin error<=1; done<=1; state_q<=IDLE; end
                    else begin meta_read_q<=meta_read_q+1; if(meta_read_q==15) state_q<=M_WAIT; end
                end
                M_WAIT: if (rd_valid_q && rd_tag_q==TAG_M && rd_last_q) begin state_q<=DOT_READ; pair_q<=0; end
                DOT_READ: begin pair_q<=pair_q+1; if(pair_q==31) state_q<=DOT_WAIT; end
                DOT_WAIT: if(snapshot_capture) begin
                    if(row_group_q!=10) begin row_group_q<=row_group_q+1;pair_q<=0;state_q<=DOT_READ;end
                    else state_q<=TILE_DRAIN;
                end
                TILE_DRAIN: if(snapshot_last_ack) begin
                    if(compute_tile_q[0]) begin pair_done<=1;pair_done_index<=compute_tile_q[3:1];end
                    if(compute_tile_q==15) begin state_q<=IDLE;done<=1;end
                    else begin compute_tile_q<=compute_tile_q+1;row_group_q<=0;meta_read_q<=0;state_q<=WAIT_SLOT;end
                end
                ERROR_DRAIN: if(!snapshot_valid_q || snapshot_last_ack) begin state_q<=IDLE;done<=1;end
                default: begin error<=1; done<=1; state_q<=IDLE; end
            endcase
        end
    end

`ifndef SYNTHESIS
    always @(posedge clk) if(rst_n) begin
        if(r_cache_write && r_addr>=99) $fatal(1,"Out-of-range row factor write");
        if(product_fire && product_x_q && product_last_q && r_pending_q!=0) $fatal(1,"Row factor queue overflow");
        if(state_q==DOT_READ && !x_epoch_q) $fatal(1,"DOT without X epoch");
        if(snapshot_capture && r_read_valid_q) $fatal(1,"Snapshot before row-factor prefetch completion");
        if(m_en && !m_we && snapshot_valid_q) $fatal(1,"Metadata epoch changed before last output ACK");
        if(burst_write && state_q==DOT_READ) $fatal(1,"Single-port W read/write collision");
        if(w_fire && burst_ready_q[burst_fill_q]) $fatal(1,"Overwriting held W burst");
        if(slot_commit && (!target_pair_free || !all_w_committed || !(&c_complete_q))) $fatal(1,"Premature/occupied slot commit");
        if(loader_q==L_W && !target_pair_free) $fatal(1,"Loading occupied slot pair");
        if(state_q==M_READ && !slot_matches) $fatal(1,"Stale metadata slot epoch");
        if(x_fire && x_count_q[10:5]==49 && x_data[31:16]!=0) $fatal(1,"Noncanonical dummy row99 input");
        if(x_fire && (x_low_bank_q>8 || x_load_group_q>10)) $fatal(1,"X mod9 load counter escaped bound");
        if(rd_valid_q && rd_tag_q==TAG_D) for(integer r=0;r<9;r=r+1)
            if(4'(r)<active_rows && !(&pe_in_ready[r*16+:16])) $fatal(1,"SRAM pair response blocked");
    end
`endif
endmodule
`default_nettype wire

// Alternate lane: operand addition, signed product and accumulator update share
// one cycle. This is a timing/area experiment, not a150MHz timing claim.
`default_nettype none
// Keep the alternate lane in the same hashed compilation unit as this core.
/* verilator lint_off DECLFILENAME */
module winograd_int8_pair_acc32_single (
    input logic clk, rst_n,
    input logic in_valid,
    output logic in_ready,
    input logic in_first, in_last,
    input logic signed [7:0] in_x_even, in_x_odd, in_w_even, in_w_odd,
    output logic out_valid,
    input logic out_ready,
    output logic signed [22:0] out_pair_sum
);
    logic signed [8:0] left_sum, right_sum;
    logic signed [17:0] product;
    logic signed [22:0] accumulator_q, sum_d;
    assign left_sum = {in_x_even[7], in_x_even} + {in_w_odd[7], in_w_odd};
    assign right_sum = {in_x_odd[7], in_x_odd} + {in_w_even[7], in_w_even};
    assign product = left_sum * right_sum;
    assign in_ready = rst_n && (!out_valid || out_ready);
    assign sum_d = (in_first ? 23'sd0 : accumulator_q) + {{5{product[17]}},product};
    assign out_pair_sum = accumulator_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin accumulator_q<=23'sd0;out_valid<=1'b0;end
        else begin
            if(out_valid && out_ready)out_valid<=1'b0;
            if(in_valid && in_ready)begin
                accumulator_q<=sum_d;
                if(in_last)out_valid<=1'b1;
            end
        end
    end
endmodule
/* verilator lint_on DECLFILENAME */
`default_nettype wire
