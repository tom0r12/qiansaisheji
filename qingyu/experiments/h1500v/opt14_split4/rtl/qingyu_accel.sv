`timescale 1ns/1ps
// Qingyu FFN1 accelerator. See docs/engineering_contract.md.
module qingyu_accel #(
    parameter integer ROWS = 99,
    parameter integer K = 64,
    parameter integer LANES = 4,
    parameter integer STREAM_MAC = 0,
    parameter integer DOUBLE_BUFFER = 0,
    parameter integer PIPE_MAC = 0,
    parameter integer READ_AHEAD = 0,
    parameter integer WEIGHT_STREAM = 0,
    parameter integer OUT16 = 0
) (
    input  wire         clk,
    input  wire         rst_n,
`ifdef QINGYU_BLOCK_COPY
    input wire input_write,
    input wire [12:0] input_elem,
    input wire [15:0] input_data,
    // combo4: XPAIR writes the K-pair {input_data_hi,input_data} in one cycle.
    input wire input_pair,
    input wire [15:0] input_data_hi,
    output wire [7:0] block_remaining,
    output wire block_next_valid,
    output wire [31:0] block_next_data,
    input wire block_pop,
    // opt8: FIO write-back engine releases the stream slot it just copied.
    input wire block_release,
    output wire weight_load_ok,
    input wire weight_write,
    input wire [2:0] weight_pair,
    input wire [5:0] weight_k,
    input wire [31:0] weight_word,
    // Block metadata port: one 16-bit metadata word per cycle, written into
    // the single 128x16 metadata RAM.  The FIO only asserts it while the
    // engine is outside its metadata read phase, so no port arbitration is
    // needed.  Address layout is the legacy MMIO layout (lane*4+segment).
    input wire meta_wr_en,
    input wire [5:0] meta_wr_addr,
    input wire [15:0] meta_wr_data,
    output wire meta_read_phase,
    output wire block_valid, block_slot, block_has_row,
    output wire [31:0] block_data,
`endif
    output wire         accel_busy,
    input  wire         icb_cmd_valid,
    output wire         icb_cmd_ready,
    input  wire         icb_cmd_read,
    input  wire [15:0]  icb_cmd_addr,
    input  wire [31:0]  icb_cmd_wdata,
    input  wire [3:0]   icb_cmd_wmask,
    output reg          icb_rsp_valid,
    input  wire         icb_rsp_ready,
    output reg  [31:0]  icb_rsp_rdata,
    output reg          icb_rsp_err
);
    localparam [2:0] B_IDLE=0, B_LO=1, B_LO_CAP=2, B_HI=3, B_HI_CAP=4, B_OUT_REQ=5;
    localparam [3:0] E_IDLE=0, E_META_REQ=1, E_META_CAP=2,
                     E_ROW_INIT=3, E_MAC_REQ=4, E_MAC_CAP=5, E_STORE=6, E_DRAIN=7,
                     E_SNAP=8, E_FINAL=9;
    // combo4/opt6: INT16-output store/X-buffer modes (declared before first use)
    localparam YWIDE = OUT16 && DOUBLE_BUFFER;
    localparam XPAIR = OUT16;
    localparam STORE_STEP = YWIDE ? 8 : OUT16 ? 4 : 2;
    localparam [31:0] ERR_ADDRESS=1, ERR_BUSY_MEMORY=2, ERR_MASK=3,
                      ERR_CONFIG=4, ERR_BUSY_START=5, ERR_OVERFLOW=6,
                      ERR_METADATA=7, ERR_BUSY_CONFIG=8;
    reg [2:0] bus_state;
    reg [3:0] engine_state;
    reg [1:0] bus_kind; // 0=input, 1=weight, 2=metadata, 3=output
    reg bus_read;
    reg [31:0] bus_wdata, bus_read_lo;
    integer bus_index;
    reg busy, done_flag, error_flag;
    reg [31:0] layer_id, tile_col_base, error_code, compute_cycles, output_count;
    integer row_index, k_index, lane_index, meta_lane, meta_segment;
    reg [47:0] meta_assembly;
    reg signed [47:0] bias [0:LANES-1];
    reg [7:0] shift [0:LANES-1];
    // opt9: next tile's metadata, assembled as the words are written
    reg signed [47:0] nbias [0:LANES-1];
    reg [7:0] nshift [0:LANES-1];
    reg [LANES-1:0] nbad;
    reg signed [47:0] acc [0:LANES-1], odd_acc[0:LANES-1], acc2[0:LANES-1], acc3[0:LANES-1];
    reg [1:0] odd_store;
    wire odd_valid=row_index+1<ROWS;
    wire [31:0] store_row=row_index+odd_store;
    reg signed [15:0] odd_x_operand, x2_operand, x3_operand;

    reg [3:0] x_en, x_we;
    reg [11:0] x_addr [0:3];
    reg [15:0] x_wdata [0:3];
    reg [15:0] x_wdata_hi [0:3];
    reg [3:0] x_wpair;
    wire [15:0] x_rdata [0:3];
    // Two private W banks. The MAC reads bank rd_bank while the loader fills
    // the other bank, so a weight transfer for tile n+1 hides under tile n.
    reg rd_bank;
    reg weight_pending; // set when a W bank image is written since the last START
    // Set by a START that consumed a pending image: the bank rotation exposed
    // one idle bank, so a new prefetch may fill it while the engine is busy.
    // After a START that reused the resident image the banks are not known to
    // be paired, so the loader must stay idle (legacy single-bank protocol).
    reg bank_rotated;
    reg [LANES-1:0] w_en;                 // read port (MAC fetch or MMIO readback)
    reg [6:0] w_addr [0:LANES-1];
    reg [LANES-1:0] w_wr_en;              // write port, always bank ~rd_bank
    reg [6:0] w_wr_addr [0:LANES-1];
    reg [15:0] w_wr_wdata [0:LANES-1];
    wire [15:0] w_rdata [0:LANES-1];
    // The MMIO W window is the programming port: it addresses the bank the
    // loader is filling, so write-then-readback stays consistent.  The bank
    // select has to survive the capture states as well: the low half is
    // registered in B_LO_CAP and the high half in B_HI_CAP, and w_rdata is
    // muxed from w_read_bank there, so restricting it to B_LO/B_HI would
    // capture the MAC bank instead of the bank that was addressed.
    wire w_bus_w = ((bus_state==B_LO)||(bus_state==B_HI)) && (bus_kind==1);
    wire w_bus_read = ((bus_state==B_LO)||(bus_state==B_LO_CAP)||
                       (bus_state==B_HI)||(bus_state==B_HI_CAP)) &&
                      (bus_kind==1) && bus_read;
    wire w_read_bank = w_bus_read ? ~rd_bank : rd_bank;
`ifdef QINGYU_BLOCK_COPY
    wire weight_stream_write = WEIGHT_STREAM && weight_write;
`else
    wire weight_stream_write = 1'b0;
`endif
    wire bus_weight_write = w_bus_w && !bus_read;
    reg m_en, m_we;
    reg [6:0] m_addr;
    reg [15:0] m_wdata;
    wire [15:0] m_rdata;
    localparam Y_BANKS = 8;
    localparam Y_AW = DOUBLE_BUFFER ? 7 : 10;
    localparam OUTPUT_WORDS = DOUBLE_BUFFER ? 256 : ROWS*LANES;
    reg [1:0] batch_ready, batch_tail;
    // opt6 (YWIDE): store unit state.  sv: a row group is being stored;
    // sc = {row-in-group[1:0], lane-half}; sbase = first row of that group.
    reg sv, wslot;
    reg [3:0] sc;
    reg [31:0] sbase;
    wire [31:0] srow = sbase + sc[3:2];
    // opt7: shadow copies of the four row accumulators, read by the store unit.
    reg signed [47:0] sh0 [0:LANES-1], sh1 [0:LANES-1], sh2 [0:LANES-1], sh3 [0:LANES-1];
    wire [31:0] next_row = row_index + 4;
    // YWIDE: the batch slot alternates per completed batch, across tiles.
    wire write_slot = YWIDE ? wslot : row_index[3];
    wire read_slot = icb_cmd_addr[9]; // 0x7000 or 0x7200
    wire [7:0] batch_words [0:1];
    // OUT16: a row of 16 INT16 results is 8 packed words.
    localparam ROW_WORDS = OUT16 ? 8 : 16;
    // combo4: with INT16 outputs each 128x16 Y macro is 4x oversized, so both
    // batch slots share all eight macros (slot = address bit) and a store
    // writes eight lanes per cycle.  The X buffer splits even/odd K across
    // its two macros so a packed input word lands in one cycle.
    localparam BATCH_WORDS = 4*ROW_WORDS;
    localparam TAIL_WORDS = ROWS%4 == 0 ? BATCH_WORDS : (ROWS%4)*ROW_WORDS;
    assign batch_words[0] = batch_tail[0] ? TAIL_WORDS : BATCH_WORDS;
    assign batch_words[1] = batch_tail[1] ? TAIL_WORDS : BATCH_WORDS;
    wire slot_readable = batch_ready[read_slot] &&
                         {1'b0,icb_cmd_addr[8:2]} < batch_words[read_slot];
    // The host holds a batch slot until it has copied the eight rows out.  The
    // engine computes the next four-row group into its accumulators and only
    // stalls when it actually has to store, which gives the host one extra
    // group of slack while a blocking weight prefetch keeps it off the bus.
    wire producer_stall = YWIDE ? (sv && sc==3'd0 && batch_ready[write_slot]) :
                          DOUBLE_BUFFER && engine_state==E_STORE && lane_index==0 &&
                          odd_store==0 && batch_ready[write_slot];
    reg [Y_BANKS-1:0] y_en, y_we;
    reg [Y_AW-1:0] y_addr [0:Y_BANKS-1];
    reg [15:0] y_wdata [0:Y_BANKS-1];
    wire [15:0] y_rdata [0:Y_BANKS-1];

    // Valid bits, rather than resetting datapath flops, discard an aborted row.
    reg operand_valid, product_valid;
    reg signed [15:0] x_operand;
    genvar g;
    generate
        // Four independent row banks; each needs at most 25*64=1600 words.
        // Two 1024-word macros per bank avoid allocating unused 4096-word space.
        for (g=0; g<4; g=g+1) begin: g_x
            wire [15:0] bank_q[0:1];
            reg read_bank;
            // XPAIR: macro = K parity, address = linear index / 2.
            wire xsel = XPAIR ? x_addr[g][0] : x_addr[g][10];
            wire [9:0] xa = XPAIR ? x_addr[g][10:1] : x_addr[g][9:0];
            always @(posedge clk) if(x_en[g] && !x_we[g]) read_bank<=xsel;
            assign x_rdata[g]=bank_q[read_bank];
            qingyu_sram16 #(.DEPTH(1024),.ADDR_W(10)) ram0(
                .clk(clk),.en(x_en[g] && (x_wpair[g] || xsel==1'b0)),.we(x_we[g]),
                .addr(xa),.wdata(x_wdata[g]),.rdata(bank_q[0]));
            qingyu_sram16 #(.DEPTH(1024),.ADDR_W(10)) ram1(
                .clk(clk),.en(x_en[g] && (x_wpair[g] || xsel==1'b1)),.we(x_we[g]),
                .addr(xa),.wdata(x_wpair[g] ? x_wdata_hi[g] : x_wdata[g]),.rdata(bank_q[1]));
        end
        for (g=0; g<LANES; g=g+1) begin: g_w
            wire [15:0] bank0_q, bank1_q;
            wire bank0_we = w_wr_en[g] && rd_bank;
            wire bank1_we = w_wr_en[g] && !rd_bank;
            qingyu_sram16 #(.DEPTH(128), .ADDR_W(7)) bank0 (
                .clk(clk), .en((w_en[g] && !w_read_bank) || bank0_we), .we(bank0_we),
                .addr(bank0_we ? w_wr_addr[g] : w_addr[g]),
                .wdata(w_wr_wdata[g]), .rdata(bank0_q));
            qingyu_sram16 #(.DEPTH(128), .ADDR_W(7)) bank1 (
                .clk(clk), .en((w_en[g] && w_read_bank) || bank1_we), .we(bank1_we),
                .addr(bank1_we ? w_wr_addr[g] : w_addr[g]),
                .wdata(w_wr_wdata[g]), .rdata(bank1_q));
            assign w_rdata[g] = w_read_bank ? bank1_q : bank0_q;
        end
        for (g=0; g<Y_BANKS; g=g+1) begin: g_y
            qingyu_sram16 #(.DEPTH(1<<Y_AW), .ADDR_W(Y_AW)) ram (
                .clk(clk), .en(y_en[g]), .we(y_we[g]), .addr(y_addr[g]),
                .wdata(y_wdata[g]), .rdata(y_rdata[g]));
        end
    endgenerate
    qingyu_sram16 #(.DEPTH(128), .ADDR_W(7)) metadata_ram (
        .clk(clk), .en(m_en), .we(m_we), .addr(m_addr),
        .wdata(m_wdata), .rdata(m_rdata));

    // Select the bank for the returning operand, even when issuing the next read.
    wire signed [15:0] x_value = x_rdata[0];
    // opt6: marks the k=0 product (bias replaces the accumulator operand).
    reg op_first, prod_first;
    always @(posedge clk) begin
        op_first <= engine_state==E_MAC_CAP && k_index==0;
        prod_first <= op_first;
    end
    wire first_bias = YWIDE && prod_first;
    always @(posedge clk)
        if (PIPE_MAC && engine_state==E_MAC_CAP) begin x_operand<=x_value; if (odd_valid) odd_x_operand<=x_rdata[1]; if(row_index+2<ROWS) x2_operand<=x_rdata[2]; if(row_index+3<ROWS) x3_operand<=x_rdata[3]; end
    wire signed [31:0] products [0:LANES-1];
    wire signed [48:0] sums [0:LANES-1], odd_sums[0:LANES-1], sums2[0:LANES-1], sums3[0:LANES-1];
    generate
        for (g=0; g<LANES; g=g+1) begin: g_math
            if (PIPE_MAC) begin: pipelined
                reg signed [15:0] weight_operand;
                reg signed [31:0] product, odd_product, product2, product3;
                always @(posedge clk) begin
                    if (engine_state==E_MAC_CAP) weight_operand <= w_rdata[g];
                    if (operand_valid) begin
                        product <= x_operand * weight_operand;
                        if(odd_valid) odd_product <= odd_x_operand * weight_operand;
                        if(row_index+2<ROWS) product2<=x2_operand*weight_operand;
                        if(row_index+3<ROWS) product3<=x3_operand*weight_operand;
                    end
                end
                assign products[g] = product;
                wire signed [47:0] base1 = first_bias ? bias[g] : odd_acc[g];
                wire signed [47:0] base2 = first_bias ? bias[g] : acc2[g];
                wire signed [47:0] base3 = first_bias ? bias[g] : acc3[g];
                assign sums2[g]=$signed({base2[47],base2})+$signed({{17{product2[31]}},product2});
                assign sums3[g]=$signed({base3[47],base3})+$signed({{17{product3[31]}},product3});
                assign odd_sums[g] = $signed({base1[47],base1}) + $signed({{17{odd_product[31]}},odd_product});
            end else assign products[g] = x_value * $signed(w_rdata[g]);
            wire signed [47:0] base0 = first_bias ? bias[g] : acc[g];
            assign sums[g] = $signed({base0[47],base0}) +
                             $signed({{17{products[g][31]}},products[g]});
        end
    endgenerate

    // Arithmetic floor quotient plus guard/sticky gives symmetric ties-to-even,
    // including negative halfway cases, without magnitude/negation shifters.
    function automatic [31:0] round_sat32;
        input signed [47:0] value;
        input [7:0] amount;
        reg signed [95:0] extended, shifted;
        reg signed [48:0] rounded;
        reg increment;
        begin
            extended = {value,48'b0};
            shifted = extended >>> amount;
            increment = shifted[47] && ((|shifted[46:0]) || shifted[48]);
            rounded = $signed({shifted[95],shifted[95:48]}) + $signed({48'b0,increment});
            if (rounded > 49'sd2147483647) round_sat32=32'h7fffffff;
            else if (rounded < -49'sd2147483648) round_sat32=32'h80000000;
            else round_sat32=rounded[31:0];
        end
    endfunction

    // Same arithmetic floor/guard/sticky RNE as round_sat32, INT16 saturation.
    function automatic [15:0] round_sat16;
        input signed [47:0] value;
        input [7:0] amount;
        reg signed [95:0] extended, shifted;
        reg signed [48:0] rounded;
        reg increment;
        begin
            extended = {value,48'b0};
            shifted = extended >>> amount;
            increment = shifted[47] && ((|shifted[46:0]) || shifted[48]);
            rounded = $signed({shifted[95],shifted[95:48]}) + $signed({48'b0,increment});
            if (rounded > 49'sd32767) round_sat16=16'h7fff;
            else if (rounded < -49'sd32768) round_sat16=16'h8000;
            else round_sat16=rounded[15:0];
        end
    endfunction

    wire [31:0] current_output = round_sat32(odd_store==3 ? acc3[lane_index] : odd_store==2 ? acc2[lane_index] : odd_store==1 ? odd_acc[lane_index] : acc[lane_index],shift[lane_index]);
    // One 2-word read-ahead FIFO shared by the two ready slots. Reserve
    // the head until the response is accepted, including arbitrary stalls.
    reg [3:0] fetched_bank;
    reg stream_slot, fetch_pending, fifo_head, fifo_tail, stream_response;
    reg [1:0] fifo_count;
    reg [7:0] fetch_index;
    reg [31:0] fifo [0:1];
    wire stream_port = icb_cmd_addr==16'h0028 || icb_cmd_addr==16'h002c;
    wire selected_stream = READ_AHEAD && icb_cmd_read && stream_port &&
                           icb_cmd_addr[2]==stream_slot && batch_ready[stream_slot];
    wire stream_has_more = fetch_index < batch_words[stream_slot];
    wire stream_wait = selected_stream && fifo_count==0 && (fetch_pending || stream_has_more);
    assign icb_cmd_ready = (bus_state == B_IDLE) && !icb_rsp_valid && !stream_wait;
    assign accel_busy = busy;
`ifdef QINGYU_BLOCK_COPY
    // The loader always fills the bank the MAC is not reading, so a transfer
    // is legal at any time, including while the engine is busy.
    wire weight_bank = ~rd_bank;
    assign weight_load_ok = WEIGHT_STREAM && (weight_bank != rd_bank) && (!busy || bank_rotated);
`endif
    wire command_fire = icb_cmd_valid && icb_cmd_ready;
`ifdef QINGYU_BLOCK_COPY
    // The metadata RAM is single-ported; the FIO defers its block metadata
    // writes until the engine has finished reading the previous tile's meta.
    assign meta_read_phase = (engine_state==E_META_REQ) || (engine_state==E_META_CAP);
`endif
    wire soft_reset_fire = command_fire && !icb_cmd_read &&
        (icb_cmd_addr == 16'h0004) && (icb_cmd_wmask == 4'hf) &&
        icb_cmd_wdata[2];

`ifdef QINGYU_BLOCK_COPY
    wire hw_release = block_release && batch_ready[stream_slot];
`else
    wire hw_release = 1'b0;
`endif
    wire release_stream = (command_fire && !icb_cmd_read && icb_cmd_wmask==4'hf &&
                          icb_cmd_wdata==1 && icb_cmd_addr== (stream_slot ? 16'h24 : 16'h20)
                          && batch_ready[stream_slot]) || hw_release;
    wire consume_stream;
    // YWIDE: a store owns all eight Y macros for that cycle.
    wire store_fire = YWIDE ? (busy && sv && !producer_stall) :
                              (busy && engine_state==E_STORE && !producer_stall);
    // opt7: snapshot cycle; also issues the next group's k=0 read.
    wire snap_go = YWIDE && engine_state==E_SNAP && !sv;
    wire mac_kick = snap_go && next_row < ROWS;
    wire issue_stream = READ_AHEAD && batch_ready[stream_slot] && stream_has_more &&
                        (fifo_count+{1'b0,fetch_pending} < 2 || consume_stream) && bus_state!=B_OUT_REQ &&
                        !(YWIDE && store_fire && write_slot==stream_slot);
`ifdef QINGYU_BLOCK_COPY
    wire [7:0] dequeued = fetch_index - fifo_count - fetch_pending;
    assign block_remaining=batch_words[stream_slot]-dequeued;
    assign block_has_row = batch_ready[stream_slot] && (batch_words[stream_slot]-dequeued >= ROW_WORDS);
    assign block_slot = stream_slot;
    assign block_valid = fifo_count!=0;
    assign block_next_valid = fifo_count==2 || (fifo_count==1 && fetch_pending);
    assign block_next_data = fifo_count==2 ? fifo[!fifo_head] : {y_rdata[fetched_bank+1],y_rdata[fetched_bank]};
    assign block_data = fifo[fifo_head];
    assign consume_stream = (block_pop && block_valid) || (stream_response && icb_rsp_valid && icb_rsp_ready);
`else
    assign consume_stream = stream_response && icb_rsp_valid && icb_rsp_ready;
`endif
    always @(posedge clk) begin
        if (!rst_n || soft_reset_fire || (!busy && batch_ready==0) || release_stream) begin
            stream_slot <= rst_n && !soft_reset_fire && release_stream ? !stream_slot : 0;
            fetch_index<=0; fetch_pending<=0; fifo_count<=0;
            fifo_head<=0; fifo_tail<=0; stream_response<=0;
        end else if (READ_AHEAD) begin
            fetch_pending<=issue_stream;
            if (issue_stream) begin fetch_index<=fetch_index+1'b1;
                fetched_bank<= YWIDE ? {stream_slot,fetch_index[0],1'b0} : {stream_slot,fetch_index[0],1'b0}; end
            if (fetch_pending) begin
                fifo[fifo_tail]<={y_rdata[fetched_bank+1],y_rdata[fetched_bank]};
                fifo_tail<=!fifo_tail;
            end
            if (consume_stream) begin
                fifo_head<=!fifo_head;
                stream_response<=0;
            end
            if (command_fire && selected_stream && fifo_count!=0) stream_response<=1;
            case ({fetch_pending,consume_stream})
                2'b10: fifo_count<=fifo_count+1'b1;
                2'b01: fifo_count<=fifo_count-1'b1;
                default: ;
            endcase
        end
    end

    always @(posedge clk) begin
        if (!rst_n || !PIPE_MAC || soft_reset_fire ||
            (engine_state!=E_MAC_CAP && engine_state!=E_DRAIN)) begin
            operand_valid<=0;
            product_valid<=0;
        end else begin
            operand_valid<=engine_state==E_MAC_CAP;
            product_valid<=operand_valid;
        end
    end
    // Synchronous SRAM returns the prior issue while the next K is addressed.
    wire prefetch = STREAM_MAC && engine_state==E_MAC_CAP && k_index<K-1;
    wire [31:0] issue_k = prefetch ? k_index+1 : k_index;
    wire output_read = STREAM_MAC && command_fire && (DOUBLE_BUFFER ? slot_readable : !busy) && icb_cmd_read &&
        icb_cmd_addr[1:0]==0 && icb_cmd_addr>=16'h7000 && icb_cmd_addr<16'h7000+OUTPUT_WORDS*4;
    integer ci, physical_index, access_elem, bank_index, store_lane;
    reg [31:0] packed_output;
    reg [15:0] bus_half, bus_mem_read;
    reg overflow_any;
    always @* begin
        overflow_any = 1'b0;
        for (ci=0; ci<LANES; ci=ci+1)
            if ((sums[ci][48] != sums[ci][47]) || (odd_valid && odd_sums[ci][48] != odd_sums[ci][47]) || (row_index+2<ROWS && sums2[ci][48]!=sums2[ci][47]) || (row_index+3<ROWS && sums3[ci][48]!=sums3[ci][47])) overflow_any = 1'b1;
    end

    // One physical SRAM owner at a time. MMIO memory operations are accepted
    // only while the engine is idle, and each packed word uses two cycles.
    always @* begin
        packed_output=0; store_lane=0; x_en=0; x_we=0; x_wpair=0; w_en=0; w_wr_en=0; m_en=0; m_we=0; y_en=0; y_we=0;
        m_addr=0; m_wdata=0;
        for (physical_index=0; physical_index<4; physical_index=physical_index+1) begin
            x_addr[physical_index]=0; x_wdata[physical_index]=0; x_wdata_hi[physical_index]=0;
        end
        for (physical_index=0; physical_index<Y_BANKS; physical_index=physical_index+1) begin
            y_addr[physical_index]=0; y_wdata[physical_index]=0;
        end
        for (physical_index=0; physical_index<LANES; physical_index=physical_index+1) begin
            w_addr[physical_index]=0; w_wr_addr[physical_index]=0; w_wr_wdata[physical_index]=0;
`ifdef QINGYU_BLOCK_COPY
            if (WEIGHT_STREAM && weight_write && weight_pair==(physical_index/2)) begin
                w_wr_en[physical_index]=1;
                w_wr_addr[physical_index]={1'b0,weight_k};
                w_wr_wdata[physical_index]=physical_index%2 ? weight_word[31:16] : weight_word[15:0];
            end
`endif
        end
        access_elem = bus_index + (((bus_state==B_HI)||(bus_state==B_HI_CAP)) ? 1:0);
        bank_index = 0;
        bus_half = (bus_state==B_HI) ? bus_wdata[31:16] : bus_wdata[15:0];
        bus_mem_read = 0;
        case (bus_kind)
            0: bus_mem_read=x_rdata[(access_elem/K)%4];
            1: bus_mem_read=w_rdata[access_elem%LANES];
            2: bus_mem_read=m_rdata;
            3: bus_mem_read=y_rdata[((access_elem>>11)*2 + access_elem%2)%Y_BANKS];
        endcase
        if ((bus_state==B_LO)||(bus_state==B_HI)) begin
            case (bus_kind)
                0: begin
                    bank_index=(access_elem/K)%4;
                    x_en[bank_index]=1; x_we[bank_index]=!bus_read;
                    x_addr[bank_index]=(access_elem/(4*K))*K+(access_elem%K);
                    x_wdata[bank_index]=bus_half;
                end
                1: begin
                    bank_index=access_elem%LANES;
                    w_addr[bank_index]=access_elem/LANES;
                    if (bus_read) begin
                        w_en[bank_index]=1;
                    end else begin
                        w_wr_en[bank_index]=1;
                        w_wr_addr[bank_index]=access_elem/LANES;
                        w_wr_wdata[bank_index]=bus_half;
                    end
                end
                2: begin m_en=1; m_we=!bus_read; m_addr=access_elem; m_wdata=bus_half; end
                3: begin
                    bank_index=((access_elem>>11)*2 + access_elem%2)%Y_BANKS;
                    y_en[bank_index]=1; y_we[bank_index]=0;
                    y_addr[bank_index]=access_elem/2;
                end
            endcase
        end
`ifdef QINGYU_BLOCK_COPY
        // FIO block metadata write has priority over the legacy MMIO side; the
        // FIO never asserts it during E_META_REQ/E_META_CAP so reads are safe.
        if (meta_wr_en) begin
            m_en=1; m_we=1; m_addr={1'b0,meta_wr_addr}; m_wdata=meta_wr_data;
        end
`endif
`ifdef QINGYU_BLOCK_COPY
        if (input_write && !busy) begin
            x_en[input_elem[7:6]]=1; x_we[input_elem[7:6]]=1;
            x_addr[input_elem[7:6]]={1'b0,input_elem[12:8],input_elem[5:0]};
            x_wdata[input_elem[7:6]]=input_data;
            x_wdata_hi[input_elem[7:6]]=input_data_hi;
            if (XPAIR) x_wpair[input_elem[7:6]]=input_pair;
        end
`endif
        if (issue_stream) begin
            if (YWIDE) begin
                // word w of a batch: row w[5:3], lanes 2*w[2:0]+{0,1}
                bank_index={stream_slot,fetch_index[0],1'b0};
                y_addr[bank_index]=fetch_index[4:1];
            end else begin
                bank_index={stream_slot,fetch_index[0],1'b0};
                y_addr[bank_index]=fetch_index[6:1];
            end
            y_en[bank_index+:2]=2'b11;
            y_addr[bank_index+1]=y_addr[bank_index];
        end
        if (PIPE_MAC && bus_state==B_OUT_REQ && !(YWIDE && store_fire && write_slot==bus_index[8])) begin
            if (YWIDE) begin
                bank_index={bus_index[8],bus_index[1],1'b0};
                y_addr[bank_index]=bus_index[5:2];
            end else begin
                bank_index={bus_index[8],bus_index[1],1'b0};
                y_addr[bank_index]=bus_index[7:2];
            end
            y_en[bank_index+:2]=2'b11;
            y_addr[bank_index+1]=y_addr[bank_index];
        end
        if (!PIPE_MAC && output_read) begin
            bank_index = DOUBLE_BUFFER ? {read_slot,1'b0} : (((icb_cmd_addr-16'h7000)>>12)*2)%Y_BANKS;
            y_en[bank_index+:2]=2'b11;
            y_addr[bank_index]=(icb_cmd_addr-16'h7000)>>2;
            y_addr[bank_index+1]=y_addr[bank_index];
        end
        if (busy) begin
            if (engine_state==E_META_REQ) begin
                m_en=1; m_we=0; m_addr=meta_lane*4+meta_segment;
            end
            // combo4: issue the next metadata word while capturing this one.
            if (engine_state==E_META_CAP && !(meta_segment==3 && meta_lane==LANES-1)) begin
                m_en=1; m_we=0; m_addr=meta_lane*4+meta_segment+1;
            end
            if (mac_kick) begin
                x_en={next_row+3<ROWS,next_row+2<ROWS,next_row+1<ROWS,1'b1};
                x_addr[0]=(next_row/4)*K;
                x_addr[1]=x_addr[0]; x_addr[2]=x_addr[0]; x_addr[3]=x_addr[0];
                for (physical_index=0; physical_index<LANES; physical_index=physical_index+1) begin
                    w_en[physical_index]=1;
                    w_addr[physical_index]=0;
                end
            end
            if (engine_state==E_MAC_REQ || prefetch) begin
                x_en={row_index+3<ROWS,row_index+2<ROWS,odd_valid,1'b1};
                x_addr[0]=(row_index/4)*K+issue_k;
                x_addr[1]=x_addr[0]; x_addr[2]=x_addr[0]; x_addr[3]=x_addr[0];
                for (physical_index=0; physical_index<LANES; physical_index=physical_index+1) begin
                    w_en[physical_index]=1;
                    w_addr[physical_index]=issue_k;
                end
            end
            // A stalled store must not keep driving the full slot: the host
            // may already be streaming that bank out through the read-ahead
            // port.  Only store on the cycles that actually advance.
            if (store_fire) begin
                // OUT16: lanes 4m..4m+3 per cycle; word j=lane/2 of the row goes to
                // bank pair j[0] at {row,j[2:1]}, matching the read-ahead pattern.
                if (YWIDE) for(store_lane=0;store_lane<4;store_lane=store_lane+1) begin
                    bank_index={write_slot,store_lane[1:0]};
                    // lane {lane_index[3],j} -> macro j, address {slot,row,lane[3]}
                    y_en[bank_index]=1; y_we[bank_index]=1;
                    y_addr[bank_index]={srow[1:0],sc[1:0]};
                    y_wdata[bank_index]=round_sat16(sc[3:2]==3 ? sh3[{sc[1:0],store_lane[1:0]}] : sc[3:2]==2 ? sh2[{sc[1:0],store_lane[1:0]}] : sc[3:2]==1 ? sh1[{sc[1:0],store_lane[1:0]}] : sh0[{sc[1:0],store_lane[1:0]}],shift[{sc[1:0],store_lane[1:0]}]);
                end else
                if (OUT16) for(store_lane=0;store_lane<2;store_lane=store_lane+1) begin
                    bank_index=write_slot*4+store_lane*2;
                    y_en[bank_index+:2]=2'b11; y_we[bank_index+:2]=2'b11;
                    y_addr[bank_index]={store_row[2:0],lane_index[3:2]};
                    y_addr[bank_index+1]=y_addr[bank_index];
                    y_wdata[bank_index]=round_sat16(odd_store==3 ? acc3[{lane_index[3:2],store_lane[0],1'b0}] : odd_store==2 ? acc2[{lane_index[3:2],store_lane[0],1'b0}] : odd_store==1 ? odd_acc[{lane_index[3:2],store_lane[0],1'b0}] : acc[{lane_index[3:2],store_lane[0],1'b0}],shift[{lane_index[3:2],store_lane[0],1'b0}]);
                    y_wdata[bank_index+1]=round_sat16(odd_store==3 ? acc3[{lane_index[3:2],store_lane[0],1'b1}] : odd_store==2 ? acc2[{lane_index[3:2],store_lane[0],1'b1}] : odd_store==1 ? odd_acc[{lane_index[3:2],store_lane[0],1'b1}] : acc[{lane_index[3:2],store_lane[0],1'b1}],shift[{lane_index[3:2],store_lane[0],1'b1}]);
                end else
                for(store_lane=0;store_lane<2;store_lane=store_lane+1) begin
                    bank_index=write_slot*4+store_lane*2;
                    packed_output=round_sat32(odd_store==3 ? acc3[{lane_index[3:1],store_lane[0]}] : odd_store==2 ? acc2[{lane_index[3:1],store_lane[0]}] : odd_store==1 ? odd_acc[{lane_index[3:1],store_lane[0]}] : acc[{lane_index[3:1],store_lane[0]}],shift[{lane_index[3:1],store_lane[0]}]);
                    y_en[bank_index+:2]=2'b11; y_we[bank_index+:2]=2'b11;
                    y_addr[bank_index]={store_row[2:0],lane_index[3:1]};
                    y_addr[bank_index+1]=y_addr[bank_index];
                    y_wdata[bank_index]=packed_output[15:0];y_wdata[bank_index+1]=packed_output[31:16];
                end
            end
        end
    end

    task automatic respond_error;
        input [31:0] code;
        begin
            icb_rsp_valid<=1; icb_rsp_err<=1; icb_rsp_rdata<=0;
            error_flag<=1; error_code<=code;
        end
    endtask

    integer si;
    always @(posedge clk) begin
        if (!rst_n) begin
            bus_state<=B_IDLE; engine_state<=E_IDLE;
            icb_rsp_valid<=0; icb_rsp_err<=0; icb_rsp_rdata<=0;
            bus_kind<=0; bus_index<=0; bus_read<=0; bus_wdata<=0; bus_read_lo<=0;
            batch_ready<=0; batch_tail<=0;
            busy<=0; done_flag<=0; error_flag<=0; error_code<=0;
            layer_id<=0; tile_col_base<=0; compute_cycles<=0; output_count<=0;
            row_index<=0; k_index<=0; lane_index<=0; meta_lane<=0; meta_segment<=0;
            meta_assembly<=0;
            rd_bank<=0; weight_pending<=0; bank_rotated<=0;
            sv<=0; sc<=0; sbase<=0; wslot<=0;
            for (si=0; si<LANES; si=si+1) begin bias[si]<=0; shift[si]<=0; acc[si]<=0; end
        end else if (soft_reset_fire) begin
            bus_state<=B_IDLE; engine_state<=E_IDLE;
            icb_rsp_valid<=1; icb_rsp_err<=0; icb_rsp_rdata<=0;
            batch_ready<=0; batch_tail<=0;
            busy<=0; done_flag<=0; error_flag<=0; error_code<=0;
            layer_id<=0; tile_col_base<=0; compute_cycles<=0; output_count<=0;
            row_index<=0; k_index<=0; lane_index<=0; meta_lane<=0; meta_segment<=0;
            meta_assembly<=0;
            sv<=0; sc<=0; wslot<=0;
        end else begin
            if (icb_rsp_valid && icb_rsp_ready) icb_rsp_valid<=0;
            if (!busy) sv<=0;
            if (hw_release) batch_ready[stream_slot]<=0;
            if (busy) compute_cycles<=compute_cycles+1;
            if (weight_stream_write || bus_weight_write) weight_pending<=1;
            case (bus_state)
                B_IDLE: if (command_fire) begin
                    icb_rsp_rdata<=0; icb_rsp_err<=0;
                    if (icb_cmd_addr[1:0]!=0) respond_error(ERR_ADDRESS);
                    else if (!icb_cmd_read && icb_cmd_wmask!=4'hf) respond_error(ERR_MASK);
                    else if ((icb_cmd_addr>=16'h1000)&&(icb_cmd_addr<16'h1000+ROWS*K*2)) begin
                        if (busy) respond_error(ERR_BUSY_MEMORY);
                        else begin
                            bus_kind<=0; bus_index<=(icb_cmd_addr-16'h1000)/2;
                            bus_read<=icb_cmd_read; bus_wdata<=icb_cmd_wdata; bus_state<=B_LO;
                        end
                    end else if ((icb_cmd_addr>=16'h5000)&&(icb_cmd_addr<16'h5000+K*LANES*2)) begin
                        if (busy) respond_error(ERR_BUSY_MEMORY);
                        else begin
                            bus_kind<=1; bus_index<=(icb_cmd_addr-16'h5000)/2;
                            bus_read<=icb_cmd_read; bus_wdata<=icb_cmd_wdata; bus_state<=B_LO;
                        end
                    end else if ((icb_cmd_addr>=16'h6000)&&(icb_cmd_addr<16'h6000+LANES*8)) begin
                        if (busy) respond_error(ERR_BUSY_MEMORY);
                        else begin
                            bus_kind<=2; bus_index<=(icb_cmd_addr-16'h6000)/2;
                            bus_read<=icb_cmd_read; bus_wdata<=icb_cmd_wdata; bus_state<=B_LO;
                        end
                    end else if ((icb_cmd_addr>=16'h7000)&&(icb_cmd_addr<16'h7000+OUTPUT_WORDS*4)) begin
                        if (DOUBLE_BUFFER ? !slot_readable : busy) respond_error(ERR_BUSY_MEMORY);
                        else if (!icb_cmd_read) respond_error(ERR_ADDRESS);
                        else begin
                            bus_kind<=3; bus_index<=(icb_cmd_addr-16'h7000)/2;
                            bus_read<=1; bus_wdata<=0; bus_state<=PIPE_MAC ? B_OUT_REQ : STREAM_MAC ? B_HI_CAP : B_LO;
                        end
                    end else if (icb_cmd_read) begin
                        icb_rsp_valid<=1;
                        case (icb_cmd_addr)
                            16'h0000: icb_rsp_rdata<=DOUBLE_BUFFER ? 32'h51590002 : 32'h51590001;
                            16'h0028,16'h002c: if (selected_stream && fifo_count!=0)
                                icb_rsp_rdata<=fifo[fifo_head];
                            else respond_error(ERR_ADDRESS);
                            16'h0020,16'h0024: if (DOUBLE_BUFFER)
                                icb_rsp_rdata<={error_flag,23'b0,batch_ready[icb_cmd_addr[2]] ?
                                                batch_words[icb_cmd_addr[2]] : 8'd0};
                            else respond_error(ERR_ADDRESS);
                            16'h0004: icb_rsp_rdata<=0;
                            16'h0008: icb_rsp_rdata<={29'b0,error_flag,done_flag,busy};
                            16'h000c: icb_rsp_rdata<=layer_id;
                            16'h0010: icb_rsp_rdata<=tile_col_base;
                            16'h0014: icb_rsp_rdata<=error_code;
                            16'h0018: icb_rsp_rdata<=compute_cycles;
                            16'h001c: icb_rsp_rdata<=output_count;
                            default: respond_error(ERR_ADDRESS);
                        endcase
                    end else begin
                        icb_rsp_valid<=1;
                        case (icb_cmd_addr)
                            16'h0020,16'h0024: if (DOUBLE_BUFFER && icb_cmd_wdata==1 &&
                                                    batch_ready[icb_cmd_addr[2]])
                                batch_ready[icb_cmd_addr[2]]<=0;
                            else respond_error(ERR_CONFIG);
                            16'h0004: begin
                                if (icb_cmd_wdata[31:3]!=0) respond_error(ERR_CONFIG);
                                else if (icb_cmd_wdata[0] && (busy || (DOUBLE_BUFFER && !YWIDE && |batch_ready))) respond_error(ERR_BUSY_START);
                                else begin
                                    if (icb_cmd_wdata[1]) begin done_flag<=0; error_flag<=0; error_code<=0; end
                                    if (icb_cmd_wdata[0]) begin
                                        busy<=1; done_flag<=0; output_count<=0; compute_cycles<=0;
                                        // nothing waiting for the host: restart the slot sequence
                                        if (YWIDE && batch_ready==0) wslot<=0;
                                        meta_lane<=0; meta_segment<=0; meta_assembly<=0;
                                        row_index<=0; k_index<=0; lane_index<=0; engine_state<=E_META_REQ;
                                        // The next tile reads the bank just loaded, but only when a
                                        // new weight image was written since the previous START;
                                        // otherwise the weight image persists unchanged.
                                        bank_rotated<=weight_pending;
                                        if (weight_pending) rd_bank<=~rd_bank;
                                        weight_pending<=0;
                                        if (YWIDE) begin
                                            for (si=0; si<LANES; si=si+1) begin bias[si]<=nbias[si]; shift[si]<=nshift[si]; end
                                            engine_state<=E_ROW_INIT;
                                            if (|nbad) begin
                                                busy<=0; error_flag<=1; error_code<=ERR_METADATA; engine_state<=E_IDLE;
                                            end
                                        end
                                    end
                                end
                            end
                            16'h000c: begin
                                if (busy) respond_error(ERR_BUSY_CONFIG);
                                else if (icb_cmd_wdata>11) respond_error(ERR_CONFIG);
                                else layer_id<=icb_cmd_wdata;
                            end
                            16'h0010: begin
                                if (busy) respond_error(ERR_BUSY_CONFIG);
                                else if ((icb_cmd_wdata>256-LANES)||((icb_cmd_wdata%LANES)!=0)) respond_error(ERR_CONFIG);
                                else tile_col_base<=icb_cmd_wdata;
                            end
                            default: respond_error(ERR_ADDRESS);
                        endcase
                    end
                end
                B_LO: if (bus_read) bus_state<=B_LO_CAP; else bus_state<=B_HI;
                B_LO_CAP: begin bus_read_lo<=bus_mem_read; bus_state<=B_HI; end
                B_HI: begin
                    if (bus_read) bus_state<=B_HI_CAP;
                    else begin bus_state<=B_IDLE; icb_rsp_valid<=1; icb_rsp_err<=0; icb_rsp_rdata<=0; end
                end
                B_OUT_REQ: if (!(YWIDE && store_fire && write_slot==bus_index[8])) bus_state<=B_HI_CAP;
                B_HI_CAP: begin
                    bus_state<=B_IDLE; icb_rsp_valid<=1; icb_rsp_err<=0;
                    icb_rsp_rdata<=(YWIDE && bus_kind==3) ? {y_rdata[{bus_index[2:1],1'b1}],y_rdata[{bus_index[2:1],1'b0}]} :
                                   (DOUBLE_BUFFER && bus_kind==3) ? {y_rdata[{bus_index[8],bus_index[1],1'b1}],y_rdata[{bus_index[8],bus_index[1],1'b0}]} :
                                   (STREAM_MAC && bus_kind==3) ? {y_rdata[((bus_index>>11)*2+1)%Y_BANKS],y_rdata[((bus_index>>11)*2)%Y_BANKS]} : {bus_mem_read,bus_read_lo[15:0]};
                end
                default: bus_state<=B_IDLE;
            endcase

            case (engine_state)
                E_META_REQ: engine_state<=E_META_CAP;
                E_META_CAP: begin
                    case (meta_segment)
                        0: meta_assembly[15:0]<=m_rdata;
                        1: meta_assembly[31:16]<=m_rdata;
                        2: meta_assembly[47:32]<=m_rdata;
                        3: begin bias[meta_lane]<=meta_assembly; shift[meta_lane]<=m_rdata[7:0]; end
                    endcase
                    if ((meta_segment==3)&&((m_rdata[15:8]!=0)||(m_rdata[7:0]>47))) begin
                        busy<=0; error_flag<=1; error_code<=ERR_METADATA; engine_state<=E_IDLE;
                    end else if (meta_segment==3) begin
                        meta_segment<=0;
                        if (meta_lane==LANES-1) begin row_index<=0; engine_state<=E_ROW_INIT; end
                        else begin meta_lane<=meta_lane+1; engine_state<=E_META_CAP; end
                    end else begin meta_segment<=meta_segment+1; engine_state<=E_META_CAP; end
                end
                E_ROW_INIT: begin
                    odd_store<=0; for (si=0; si<LANES; si=si+1) begin acc[si]<=bias[si]; if(odd_valid) odd_acc[si]<=bias[si]; if(row_index+2<ROWS) acc2[si]<=bias[si]; if(row_index+3<ROWS) acc3[si]<=bias[si]; end
                    k_index<=0; lane_index<=0; engine_state<=E_MAC_REQ;
                end
                E_MAC_REQ: engine_state<=E_MAC_CAP;
                E_MAC_CAP, E_DRAIN: begin
                    if ((!PIPE_MAC || product_valid) && overflow_any) begin
                        busy<=0; error_flag<=1; error_code<=ERR_OVERFLOW; engine_state<=E_IDLE;
                    end else begin
                        if (!PIPE_MAC || product_valid)
                            for (si=0; si<LANES; si=si+1) begin acc[si]<=sums[si][47:0]; if(odd_valid) odd_acc[si]<=odd_sums[si][47:0]; if(row_index+2<ROWS) acc2[si]<=sums2[si][47:0]; if(row_index+3<ROWS) acc3[si]<=sums3[si][47:0]; end
                        if (PIPE_MAC && k_index==K-1 && (engine_state==E_MAC_CAP || operand_valid))
                            engine_state<=E_DRAIN;
                        else if (k_index==K-1 && YWIDE) begin
                            k_index<=0; engine_state<=E_SNAP;
                        end
                        else if (k_index==K-1) begin lane_index<=0; engine_state<=E_STORE; end
                        else begin k_index<=k_index+1; engine_state<=STREAM_MAC ? E_MAC_CAP : E_MAC_REQ; end
                    end
                end
                E_STORE: if (!producer_stall) begin
                    if (lane_index==LANES-STORE_STEP) begin
                        if (DOUBLE_BUFFER && (store_row[2:0]==7 || store_row==ROWS-1)) begin
                            batch_ready[write_slot]<=1;
                            batch_tail[write_slot]<=store_row==ROWS-1;
                        end
                        if (odd_store<3 && store_row+1<ROWS) begin odd_store<=odd_store+1; lane_index<=0; end
                        else if (store_row==ROWS-1) begin
                            busy<=0; done_flag<=1; output_count<=ROWS*LANES; engine_state<=E_IDLE;
                        end else if (YWIDE) begin
                            // combo4: the next group's ROW_INIT happens on this last store
                            // edge; the store above has already sampled the accumulators.
                            odd_store<=0; k_index<=0; lane_index<=0; row_index<=row_index+4;
                            for (si=0; si<LANES; si=si+1) begin acc[si]<=bias[si]; if(row_index+5<ROWS) odd_acc[si]<=bias[si]; if(row_index+6<ROWS) acc2[si]<=bias[si]; if(row_index+7<ROWS) acc3[si]<=bias[si]; end
                            engine_state<=E_MAC_REQ;
                        end else begin row_index<=row_index+4; engine_state<=E_ROW_INIT; end
                    end else lane_index<=lane_index+STORE_STEP;
                end
                E_SNAP: if (snap_go) begin
                    for (si=0; si<LANES; si=si+1) begin
                        sh0[si]<=acc[si]; sh1[si]<=odd_acc[si]; sh2[si]<=acc2[si]; sh3[si]<=acc3[si];
                    end
                    sv<=1; sc<=0; sbase<=row_index;
                    if (next_row<ROWS) begin row_index<=next_row; engine_state<=E_MAC_CAP; end
                    else engine_state<=E_FINAL;
                end
                E_FINAL: ;
                default: ;
            endcase
            // opt6 store unit (YWIDE): 8 cycles per 4-row group, 2 per row.
            if (YWIDE && store_fire) begin
                if (sc[1:0]==2'd3) begin
                    if (srow[1:0]==3 || srow==ROWS-1) begin
                        batch_ready[write_slot]<=1;
                        batch_tail[write_slot]<=srow==ROWS-1;
                        wslot<=!wslot;
                    end
                    if (sc[3:2]!=2'd3 && srow+1<ROWS) sc<=sc+4'd1;
                    else begin
                        sv<=0;
                        if (srow==ROWS-1) begin
                            busy<=0; done_flag<=1; output_count<=ROWS*LANES; engine_state<=E_IDLE;
                        end
                    end
                end else sc<=sc+4'd1;
            end
        end
    end

    // opt9 metadata capture: segment 0..2 = bias[15:0],[31:16],[47:32], 3 = {0,shift}
    integer mi, me;
    always @(posedge clk) begin
        if (!rst_n) nbad <= 0;
        else if (YWIDE) begin
`ifdef QINGYU_BLOCK_COPY
            if (meta_wr_en) begin
                mi = meta_wr_addr[5:2];
                case (meta_wr_addr[1:0])
                    2'd0: nbias[mi][15:0] <= meta_wr_data;
                    2'd1: nbias[mi][31:16] <= meta_wr_data;
                    2'd2: nbias[mi][47:32] <= meta_wr_data;
                    2'd3: begin nshift[mi] <= meta_wr_data[7:0];
                                nbad[mi] <= (meta_wr_data[15:8]!=0) || (meta_wr_data[7:0]>47); end
                endcase
            end else
`endif
            if (((bus_state==B_LO)||(bus_state==B_HI)) && bus_kind==2 && !bus_read) begin
                me = bus_index + (bus_state==B_HI ? 1 : 0);
                mi = me / 4;
                case (me % 4)
                    0: nbias[mi][15:0] <= bus_half;
                    1: nbias[mi][31:16] <= bus_half;
                    2: nbias[mi][47:32] <= bus_half;
                    3: begin nshift[mi] <= bus_half[7:0];
                             nbad[mi] <= (bus_half[15:8]!=0) || (bus_half[7:0]>47); end
                endcase
            end
        end
    end

`ifndef SYNTHESIS
    initial begin
        if ((READ_AHEAD && !PIPE_MAC) || (PIPE_MAC && !DOUBLE_BUFFER) || (DOUBLE_BUFFER && (LANES!=16 || !STREAM_MAC)) || ROWS<1 || K<1 || K>128 || ROWS*K>8192 || (ROWS*K)%2!=0 ||
            LANES<1 || LANES>16 || 256%LANES!=0 || K*LANES%2!=0 || ROWS*LANES>2048)
            $fatal(1,"Unsupported accelerator dimensions");
    end
`endif
endmodule
