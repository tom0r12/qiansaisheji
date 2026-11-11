`timescale 1ns/1ps
// Qingyu FFN1 accelerator. See docs/engineering_contract.md.
module qingyu_accel #(
    parameter integer ROWS = 99,
    parameter integer K = 64,
    parameter integer LANES = 4,
    parameter integer STREAM_MAC = 0,
    parameter integer DOUBLE_BUFFER = 0,
    parameter integer PIPE_MAC = 0,
    parameter integer READ_AHEAD = 0
) (
    input  wire         clk,
    input  wire         rst_n,
`ifdef QINGYU_BLOCK_COPY
    input wire block_pop,
    output wire block_valid, block_slot, block_has_row,
    output wire [31:0] block_data,
`endif
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
    localparam [2:0] E_IDLE=0, E_META_REQ=1, E_META_CAP=2,
                     E_ROW_INIT=3, E_MAC_REQ=4, E_MAC_CAP=5, E_STORE=6, E_DRAIN=7;
    localparam [31:0] ERR_ADDRESS=1, ERR_BUSY_MEMORY=2, ERR_MASK=3,
                      ERR_CONFIG=4, ERR_BUSY_START=5, ERR_OVERFLOW=6,
                      ERR_METADATA=7, ERR_BUSY_CONFIG=8;
    reg [2:0] bus_state, engine_state;
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
    reg signed [47:0] acc [0:LANES-1], odd_acc[0:LANES-1];
    reg odd_store;
    wire odd_valid=row_index+1<ROWS;
    wire [31:0] store_row=row_index+odd_store;
    reg signed [15:0] odd_x_operand;

    reg [1:0] x_en, x_we;
    reg [11:0] x_addr [0:1];
    reg [15:0] x_wdata [0:1];
    wire [15:0] x_rdata [0:1];
    reg [LANES-1:0] w_en, w_we;
    reg [6:0] w_addr [0:LANES-1];
    reg [15:0] w_wdata [0:LANES-1];
    wire [15:0] w_rdata [0:LANES-1];
    reg m_en, m_we;
    reg [6:0] m_addr;
    reg [15:0] m_wdata;
    wire [15:0] m_rdata;
    localparam Y_BANKS = DOUBLE_BUFFER || ROWS*LANES > 1024 ? 4 : 2;
    localparam Y_AW = DOUBLE_BUFFER ? 7 : 10;
    localparam OUTPUT_WORDS = DOUBLE_BUFFER ? 256 : ROWS*LANES;
    reg [1:0] batch_ready, batch_tail;
    wire write_slot = row_index[3];
    wire read_slot = icb_cmd_addr[9]; // 0x7000 or 0x7200
    wire [7:0] batch_words [0:1];
    localparam TAIL_WORDS = ROWS%8 == 0 ? 128 : (ROWS%8)*16;
    assign batch_words[0] = batch_tail[0] ? TAIL_WORDS : 128;
    assign batch_words[1] = batch_tail[1] ? TAIL_WORDS : 128;
    wire slot_readable = batch_ready[read_slot] &&
                         {1'b0,icb_cmd_addr[8:2]} < batch_words[read_slot];
    wire producer_stall = DOUBLE_BUFFER && engine_state==E_ROW_INIT && batch_ready[write_slot];
    reg [Y_BANKS-1:0] y_en, y_we;
    reg [Y_AW-1:0] y_addr [0:Y_BANKS-1];
    reg [15:0] y_wdata [0:Y_BANKS-1];
    wire [15:0] y_rdata [0:Y_BANKS-1];

    // Valid bits, rather than resetting datapath flops, discard an aborted row.
    reg operand_valid, product_valid;
    reg signed [15:0] x_operand;
    genvar g;
    generate
        for (g=0; g<2; g=g+1) begin: g_x
            qingyu_sram16 #(.DEPTH(4096), .ADDR_W(12)) ram (
                .clk(clk), .en(x_en[g]), .we(x_we[g]), .addr(x_addr[g]),
                .wdata(x_wdata[g]), .rdata(x_rdata[g]));
        end
        for (g=0; g<LANES; g=g+1) begin: g_w
            qingyu_sram16 #(.DEPTH(128), .ADDR_W(7)) ram (
                .clk(clk), .en(w_en[g]), .we(w_we[g]), .addr(w_addr[g]),
                .wdata(w_wdata[g]), .rdata(w_rdata[g]));
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
    always @(posedge clk)
        if (PIPE_MAC && engine_state==E_MAC_CAP) begin x_operand<=x_value; if (odd_valid) odd_x_operand<=x_rdata[1]; end
    wire signed [31:0] products [0:LANES-1];
    wire signed [48:0] sums [0:LANES-1], odd_sums[0:LANES-1];
    generate
        for (g=0; g<LANES; g=g+1) begin: g_math
            if (PIPE_MAC) begin: pipelined
                reg signed [15:0] weight_operand;
                reg signed [31:0] product, odd_product;
                always @(posedge clk) begin
                    if (engine_state==E_MAC_CAP) weight_operand <= w_rdata[g];
                    if (operand_valid) begin
                        product <= x_operand * weight_operand;
                        if(odd_valid) odd_product <= odd_x_operand * weight_operand;
                    end
                end
                assign products[g] = product;
                assign odd_sums[g] = $signed({odd_acc[g][47],odd_acc[g]}) + $signed({{17{odd_product[31]}},odd_product});
            end else assign products[g] = x_value * $signed(w_rdata[g]);
            assign sums[g] = $signed({acc[g][47],acc[g]}) +
                             $signed({{17{products[g][31]}},products[g]});
        end
    endgenerate

    function automatic [31:0] round_sat32;
        input signed [47:0] value;
        input [7:0] amount;
        reg [48:0] magnitude, quotient, remainder, half, mask;
        reg signed [49:0] signed_result;
        begin
            magnitude = value[47] ? ({1'b0,~value}+49'd1) : {1'b0,value};
            quotient = magnitude >> amount;
            if (amount != 0) begin
                mask = (49'd1 << amount)-49'd1;
                remainder = magnitude & mask;
                half = 49'd1 << (amount-1);
                if ((remainder > half) || ((remainder == half) && quotient[0]))
                    quotient = quotient + 49'd1;
            end
            signed_result = value[47] ? -$signed({1'b0,quotient}) :
                                       $signed({1'b0,quotient});
            if (signed_result > 50'sd2147483647) round_sat32 = 32'h7fffffff;
            else if (signed_result < -50'sd2147483648) round_sat32 = 32'h80000000;
            else round_sat32 = signed_result[31:0];
        end
    endfunction

    wire [31:0] current_output = round_sat32(odd_store ? odd_acc[lane_index] : acc[lane_index],shift[lane_index]);
    // One 2-word read-ahead FIFO shared by the two ready slots. Reserve
    // the head until the response is accepted, including arbitrary stalls.
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
    wire command_fire = icb_cmd_valid && icb_cmd_ready;
    wire soft_reset_fire = command_fire && !icb_cmd_read &&
        (icb_cmd_addr == 16'h0004) && (icb_cmd_wmask == 4'hf) &&
        icb_cmd_wdata[2];

    wire release_stream = command_fire && !icb_cmd_read && icb_cmd_wmask==4'hf &&
                          icb_cmd_wdata==1 && icb_cmd_addr== (stream_slot ? 16'h24 : 16'h20)
                          && batch_ready[stream_slot];
    wire issue_stream = READ_AHEAD && batch_ready[stream_slot] && stream_has_more &&
                        !fetch_pending && fifo_count<2 && bus_state!=B_OUT_REQ;
`ifdef QINGYU_BLOCK_COPY
    wire [7:0] dequeued = fetch_index - fifo_count - fetch_pending;
    assign block_has_row = batch_ready[stream_slot] && (batch_words[stream_slot]-dequeued >= 16);
    assign block_slot = stream_slot;
    assign block_valid = fifo_count!=0;
    assign block_data = fifo[fifo_head];
    wire consume_stream = (block_pop && block_valid) || (stream_response && icb_rsp_valid && icb_rsp_ready);
`else
    wire consume_stream = stream_response && icb_rsp_valid && icb_rsp_ready;
`endif
    always @(posedge clk) begin
        if (!rst_n || soft_reset_fire || (!busy && batch_ready==0) || release_stream) begin
            stream_slot <= rst_n && !soft_reset_fire && release_stream ? !stream_slot : 0;
            fetch_index<=0; fetch_pending<=0; fifo_count<=0;
            fifo_head<=0; fifo_tail<=0; stream_response<=0;
        end else if (READ_AHEAD) begin
            fetch_pending<=issue_stream;
            if (issue_stream) fetch_index<=fetch_index+1'b1;
            if (fetch_pending) begin
                fifo[fifo_tail]<={y_rdata[{stream_slot,1'b1}],y_rdata[{stream_slot,1'b0}]};
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
    integer ci, physical_index, access_elem, bank_index;
    reg [15:0] bus_half, bus_mem_read;
    reg overflow_any;
    always @* begin
        overflow_any = 1'b0;
        for (ci=0; ci<LANES; ci=ci+1)
            if ((sums[ci][48] != sums[ci][47]) || (odd_valid && odd_sums[ci][48] != odd_sums[ci][47])) overflow_any = 1'b1;
    end

    // One physical SRAM owner at a time. MMIO memory operations are accepted
    // only while the engine is idle, and each packed word uses two cycles.
    always @* begin
        x_en=0; x_we=0; w_en=0; w_we=0; m_en=0; m_we=0; y_en=0; y_we=0;
        m_addr=0; m_wdata=0;
        for (physical_index=0; physical_index<2; physical_index=physical_index+1) begin
            x_addr[physical_index]=0; x_wdata[physical_index]=0;
        end
        for (physical_index=0; physical_index<Y_BANKS; physical_index=physical_index+1) begin
            y_addr[physical_index]=0; y_wdata[physical_index]=0;
        end
        for (physical_index=0; physical_index<LANES; physical_index=physical_index+1) begin
            w_addr[physical_index]=0; w_wdata[physical_index]=0;
        end
        access_elem = bus_index + (((bus_state==B_HI)||(bus_state==B_HI_CAP)) ? 1:0);
        bank_index = 0;
        bus_half = (bus_state==B_HI) ? bus_wdata[31:16] : bus_wdata[15:0];
        bus_mem_read = 0;
        case (bus_kind)
            0: bus_mem_read=x_rdata[(access_elem/K)%2];
            1: bus_mem_read=w_rdata[access_elem%LANES];
            2: bus_mem_read=m_rdata;
            3: bus_mem_read=y_rdata[((access_elem>>11)*2 + access_elem%2)%Y_BANKS];
        endcase
        if ((bus_state==B_LO)||(bus_state==B_HI)) begin
            case (bus_kind)
                0: begin
                    bank_index=(access_elem/K)%2;
                    x_en[bank_index]=1; x_we[bank_index]=!bus_read;
                    x_addr[bank_index]=(access_elem/(2*K))*K+(access_elem%K);
                    x_wdata[bank_index]=bus_half;
                end
                1: begin
                    bank_index=access_elem%LANES;
                    w_en[bank_index]=1; w_we[bank_index]=!bus_read;
                    w_addr[bank_index]=access_elem/LANES;
                    w_wdata[bank_index]=bus_half;
                end
                2: begin m_en=1; m_we=!bus_read; m_addr=access_elem; m_wdata=bus_half; end
                3: begin
                    bank_index=((access_elem>>11)*2 + access_elem%2)%Y_BANKS;
                    y_en[bank_index]=1; y_we[bank_index]=0;
                    y_addr[bank_index]=access_elem/2;
                end
            endcase
        end
        if (issue_stream) begin
            bank_index={stream_slot,1'b0};
            y_en[bank_index+:2]=2'b11;
            y_addr[bank_index]=fetch_index[6:0]; y_addr[bank_index+1]=fetch_index[6:0];
        end
        if (PIPE_MAC && bus_state==B_OUT_REQ) begin
            bank_index={bus_index[8],1'b0};
            y_en[bank_index+:2]=2'b11;
            y_addr[bank_index]=bus_index[7:1];
            y_addr[bank_index+1]=bus_index[7:1];
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
            if (engine_state==E_MAC_REQ || prefetch) begin
                x_en={odd_valid,1'b1};
                x_addr[0]=(row_index/2)*K+issue_k;
                x_addr[1]=x_addr[0];
                for (physical_index=0; physical_index<LANES; physical_index=physical_index+1) begin
                    w_en[physical_index]=1; w_we[physical_index]=0;
                    w_addr[physical_index]=issue_k;
                end
            end
            if (engine_state==E_STORE) begin
                bank_index=DOUBLE_BUFFER ? {write_slot,1'b0} : (((row_index*LANES+lane_index)>>10)*2)%Y_BANKS;
                y_en[bank_index+:2]=2'b11; y_we[bank_index+:2]=2'b11;
                y_addr[bank_index]=store_row*LANES+lane_index;
                y_addr[bank_index+1]=store_row*LANES+lane_index;
                y_wdata[bank_index]=current_output[15:0]; y_wdata[bank_index+1]=current_output[31:16];
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
            for (si=0; si<LANES; si=si+1) begin bias[si]<=0; shift[si]<=0; acc[si]<=0; end
        end else if (soft_reset_fire) begin
            bus_state<=B_IDLE; engine_state<=E_IDLE;
            icb_rsp_valid<=1; icb_rsp_err<=0; icb_rsp_rdata<=0;
            batch_ready<=0; batch_tail<=0;
            busy<=0; done_flag<=0; error_flag<=0; error_code<=0;
            layer_id<=0; tile_col_base<=0; compute_cycles<=0; output_count<=0;
            row_index<=0; k_index<=0; lane_index<=0; meta_lane<=0; meta_segment<=0;
            meta_assembly<=0;
        end else begin
            if (icb_rsp_valid && icb_rsp_ready) icb_rsp_valid<=0;
            if (busy) compute_cycles<=compute_cycles+1;
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
                                else if (icb_cmd_wdata[0] && (busy || (DOUBLE_BUFFER && |batch_ready))) respond_error(ERR_BUSY_START);
                                else begin
                                    if (icb_cmd_wdata[1]) begin done_flag<=0; error_flag<=0; error_code<=0; end
                                    if (icb_cmd_wdata[0]) begin
                                        busy<=1; done_flag<=0; output_count<=0; compute_cycles<=0;
                                        meta_lane<=0; meta_segment<=0; meta_assembly<=0;
                                        row_index<=0; k_index<=0; lane_index<=0; engine_state<=E_META_REQ;
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
                B_OUT_REQ: bus_state<=B_HI_CAP;
                B_HI_CAP: begin
                    bus_state<=B_IDLE; icb_rsp_valid<=1; icb_rsp_err<=0;
                    icb_rsp_rdata<=(DOUBLE_BUFFER && bus_kind==3) ? {y_rdata[{bus_index[8],1'b1}],y_rdata[{bus_index[8],1'b0}]} :
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
                        else begin meta_lane<=meta_lane+1; engine_state<=E_META_REQ; end
                    end else begin meta_segment<=meta_segment+1; engine_state<=E_META_REQ; end
                end
                E_ROW_INIT: if (!producer_stall) begin
                    odd_store<=0; for (si=0; si<LANES; si=si+1) begin acc[si]<=bias[si]; if(odd_valid) odd_acc[si]<=bias[si]; end
                    k_index<=0; lane_index<=0; engine_state<=E_MAC_REQ;
                end
                E_MAC_REQ: engine_state<=E_MAC_CAP;
                E_MAC_CAP, E_DRAIN: begin
                    if ((!PIPE_MAC || product_valid) && overflow_any) begin
                        busy<=0; error_flag<=1; error_code<=ERR_OVERFLOW; engine_state<=E_IDLE;
                    end else begin
                        if (!PIPE_MAC || product_valid)
                            for (si=0; si<LANES; si=si+1) begin acc[si]<=sums[si][47:0]; if(odd_valid) odd_acc[si]<=odd_sums[si][47:0]; end
                        if (PIPE_MAC && k_index==K-1 && (engine_state==E_MAC_CAP || operand_valid))
                            engine_state<=E_DRAIN;
                        else if (k_index==K-1) begin lane_index<=0; engine_state<=E_STORE; end
                        else begin k_index<=k_index+1; engine_state<=STREAM_MAC ? E_MAC_CAP : E_MAC_REQ; end
                    end
                end
                E_STORE: begin
                    if (lane_index==LANES-1) begin
                        if (DOUBLE_BUFFER && (store_row[2:0]==7 || store_row==ROWS-1)) begin
                            batch_ready[write_slot]<=1;
                            batch_tail[write_slot]<=store_row==ROWS-1;
                        end
                        if (odd_valid && !odd_store) begin odd_store<=1; lane_index<=0; end
                        else if (store_row==ROWS-1) begin
                            busy<=0; done_flag<=1; output_count<=ROWS*LANES; engine_state<=E_IDLE;
                        end else begin row_index<=row_index+2; engine_state<=E_ROW_INIT; end
                    end else lane_index<=lane_index+1;
                end
                default: ;
            endcase
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
