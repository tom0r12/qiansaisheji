"""combo4 patch: X pair write, async weight cmd, pipelined meta read,
8-lane Y store (OUT16), ROW_INIT merged into the last store cycle,
partial-input transfer length fix. Run with the combo4 directory as argv[1]."""
import sys, pathlib

root = pathlib.Path(sys.argv[1])


def patch(name, pairs):
    p = root / "rtl" / name
    raw = p.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    s = raw.replace("\r\n", "\n")
    for old, new in pairs:
        n = s.count(old)
        if n != 1:
            raise SystemExit(f"{name}: anchor count {n}: {old[:80]!r}")
        s = s.replace(old, new)
    if crlf:
        s = s.replace("\n", "\r\n")
    p.write_bytes(s.encode("utf-8"))
    print("patched", name, len(pairs))


accel = [
    # ---- ports
    ("""    input wire [15:0] input_data,
""", """    input wire [15:0] input_data,
    // combo4: XPAIR writes the K-pair {input_data_hi,input_data} in one cycle.
    input wire input_pair,
    input wire [15:0] input_data_hi,
"""),
    # ---- localparams
    ("""    localparam ROW_WORDS = OUT16 ? 8 : 16;
""", """    localparam ROW_WORDS = OUT16 ? 8 : 16;
    // combo4: with INT16 outputs each 128x16 Y macro is 4x oversized, so both
    // batch slots share all eight macros (slot = address bit) and a store
    // writes eight lanes per cycle.  The X buffer splits even/odd K across
    // its two macros so a packed input word lands in one cycle.
    localparam YWIDE = OUT16 && DOUBLE_BUFFER;
    localparam XPAIR = OUT16;
    localparam STORE_STEP = YWIDE ? 8 : OUT16 ? 4 : 2;
"""),
    ("""    reg [15:0] x_wdata [0:3];
""", """    reg [15:0] x_wdata [0:3];
    reg [15:0] x_wdata_hi [0:3];
    reg [3:0] x_wpair;
"""),
    # ---- X macros
    ("""            reg read_bank;
            always @(posedge clk) if(x_en[g] && !x_we[g]) read_bank<=x_addr[g][10];
            assign x_rdata[g]=bank_q[read_bank];
            qingyu_sram16 #(.DEPTH(1024),.ADDR_W(10)) ram0(
                .clk(clk),.en(x_en[g] && x_addr[g][10]==1'b0),.we(x_we[g]),
                .addr(x_addr[g][9:0]),.wdata(x_wdata[g]),.rdata(bank_q[0]));
            qingyu_sram16 #(.DEPTH(1024),.ADDR_W(10)) ram1(
                .clk(clk),.en(x_en[g] && x_addr[g][10]==1'b1),.we(x_we[g]),
                .addr(x_addr[g][9:0]),.wdata(x_wdata[g]),.rdata(bank_q[1]));
""", """            reg read_bank;
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
"""),
    # ---- store fire / read-ahead conflict
    ("""    wire consume_stream;
    wire issue_stream = READ_AHEAD && batch_ready[stream_slot] && stream_has_more &&
                        (fifo_count+{1'b0,fetch_pending} < 2 || consume_stream) && bus_state!=B_OUT_REQ;
""", """    wire consume_stream;
    // YWIDE: a store owns all eight Y macros for that cycle.
    wire store_fire = busy && engine_state==E_STORE && !producer_stall;
    wire issue_stream = READ_AHEAD && batch_ready[stream_slot] && stream_has_more &&
                        (fifo_count+{1'b0,fetch_pending} < 2 || consume_stream) && bus_state!=B_OUT_REQ &&
                        !(YWIDE && store_fire);
"""),
    ("""            if (issue_stream) begin fetch_index<=fetch_index+1'b1; fetched_bank<={stream_slot,fetch_index[0],1'b0}; end
""", """            if (issue_stream) begin fetch_index<=fetch_index+1'b1;
                fetched_bank<= YWIDE ? {1'b0,fetch_index[1:0],1'b0} : {stream_slot,fetch_index[0],1'b0}; end
"""),
    # ---- comb defaults
    ("""        packed_output=0; store_lane=0; x_en=0; x_we=0; w_en=0; w_wr_en=0; m_en=0; m_we=0; y_en=0; y_we=0;
""", """        packed_output=0; store_lane=0; x_en=0; x_we=0; x_wpair=0; w_en=0; w_wr_en=0; m_en=0; m_we=0; y_en=0; y_we=0;
"""),
    ("""            x_addr[physical_index]=0; x_wdata[physical_index]=0;
""", """            x_addr[physical_index]=0; x_wdata[physical_index]=0; x_wdata_hi[physical_index]=0;
"""),
    ("""            x_wdata[input_elem[7:6]]=input_data;
""", """            x_wdata[input_elem[7:6]]=input_data;
            x_wdata_hi[input_elem[7:6]]=input_data_hi;
            if (XPAIR) x_wpair[input_elem[7:6]]=input_pair;
"""),
    # read-ahead issue
    ("""        if (issue_stream) begin
            bank_index={stream_slot,fetch_index[0],1'b0};
            y_en[bank_index+:2]=2'b11;
            y_addr[bank_index]=fetch_index[6:1]; y_addr[bank_index+1]=fetch_index[6:1];
        end
        if (PIPE_MAC && bus_state==B_OUT_REQ) begin
            bank_index={bus_index[8],bus_index[1],1'b0};
            y_en[bank_index+:2]=2'b11;
            y_addr[bank_index]=bus_index[7:2];
            y_addr[bank_index+1]=bus_index[7:2];
        end
""", """        if (issue_stream) begin
            if (YWIDE) begin
                // word w of a batch: row w[5:3], lanes 2*w[2:0]+{0,1}
                bank_index={fetch_index[1:0],1'b0};
                y_addr[bank_index]={stream_slot,fetch_index[5:3],fetch_index[2]};
            end else begin
                bank_index={stream_slot,fetch_index[0],1'b0};
                y_addr[bank_index]=fetch_index[6:1];
            end
            y_en[bank_index+:2]=2'b11;
            y_addr[bank_index+1]=y_addr[bank_index];
        end
        if (PIPE_MAC && bus_state==B_OUT_REQ) begin
            if (YWIDE) begin
                bank_index={bus_index[2:1],1'b0};
                y_addr[bank_index]={bus_index[8],bus_index[6:4],bus_index[3]};
            end else begin
                bank_index={bus_index[8],bus_index[1],1'b0};
                y_addr[bank_index]=bus_index[7:2];
            end
            y_en[bank_index+:2]=2'b11;
            y_addr[bank_index+1]=y_addr[bank_index];
        end
"""),
    # meta pipelined read
    ("""            if (engine_state==E_META_REQ) begin
                m_en=1; m_we=0; m_addr=meta_lane*4+meta_segment;
            end
""", """            if (engine_state==E_META_REQ) begin
                m_en=1; m_we=0; m_addr=meta_lane*4+meta_segment;
            end
            // combo4: issue the next metadata word while capturing this one.
            if (engine_state==E_META_CAP && !(meta_segment==3 && meta_lane==LANES-1)) begin
                m_en=1; m_we=0; m_addr=meta_lane*4+meta_segment+1;
            end
"""),
    # wide store
    ("""                if (OUT16) for(store_lane=0;store_lane<2;store_lane=store_lane+1) begin
""", """                if (YWIDE) for(store_lane=0;store_lane<8;store_lane=store_lane+1) begin
                    // lane {lane_index[3],j} -> macro j, address {slot,row,lane[3]}
                    y_en[store_lane]=1; y_we[store_lane]=1;
                    y_addr[store_lane]={write_slot,store_row[2:0],lane_index[3]};
                    y_wdata[store_lane]=round_sat16(odd_store==3 ? acc3[{lane_index[3],store_lane[2:0]}] : odd_store==2 ? acc2[{lane_index[3],store_lane[2:0]}] : odd_store==1 ? odd_acc[{lane_index[3],store_lane[2:0]}] : acc[{lane_index[3],store_lane[2:0]}],shift[{lane_index[3],store_lane[2:0]}]);
                end else
                if (OUT16) for(store_lane=0;store_lane<2;store_lane=store_lane+1) begin
"""),
    # B_OUT_REQ wait for store, HI_CAP data
    ("""                B_OUT_REQ: bus_state<=B_HI_CAP;
""", """                B_OUT_REQ: if (!(YWIDE && store_fire)) bus_state<=B_HI_CAP;
"""),
    ("""                    icb_rsp_rdata<=(DOUBLE_BUFFER && bus_kind==3) ? {y_rdata[{bus_index[8],bus_index[1],1'b1}],y_rdata[{bus_index[8],bus_index[1],1'b0}]} :
""", """                    icb_rsp_rdata<=(YWIDE && bus_kind==3) ? {y_rdata[{bus_index[2:1],1'b1}],y_rdata[{bus_index[2:1],1'b0}]} :
                                   (DOUBLE_BUFFER && bus_kind==3) ? {y_rdata[{bus_index[8],bus_index[1],1'b1}],y_rdata[{bus_index[8],bus_index[1],1'b0}]} :
"""),
    # meta FSM: stay in CAP
    ("""                        if (meta_lane==LANES-1) begin row_index<=0; engine_state<=E_ROW_INIT; end
                        else begin meta_lane<=meta_lane+1; engine_state<=E_META_REQ; end
                    end else begin meta_segment<=meta_segment+1; engine_state<=E_META_REQ; end
""", """                        if (meta_lane==LANES-1) begin row_index<=0; engine_state<=E_ROW_INIT; end
                        else begin meta_lane<=meta_lane+1; engine_state<=E_META_CAP; end
                    end else begin meta_segment<=meta_segment+1; engine_state<=E_META_CAP; end
"""),
    # store step + merged ROW_INIT
    ("""                    if (lane_index==LANES-(OUT16 ? 4 : 2)) begin
""", """                    if (lane_index==LANES-STORE_STEP) begin
"""),
    ("""                        end else begin row_index<=row_index+4; engine_state<=E_ROW_INIT; end
                    end else lane_index<=lane_index+(OUT16 ? 4 : 2);
""", """                        end else if (YWIDE) begin
                            // combo4: the next group's ROW_INIT happens on this last store
                            // edge; the store above has already sampled the accumulators.
                            odd_store<=0; k_index<=0; lane_index<=0; row_index<=row_index+4;
                            for (si=0; si<LANES; si=si+1) begin acc[si]<=bias[si]; if(row_index+5<ROWS) odd_acc[si]<=bias[si]; if(row_index+6<ROWS) acc2[si]<=bias[si]; if(row_index+7<ROWS) acc3[si]<=bias[si]; end
                            engine_state<=E_MAC_REQ;
                        end else begin row_index<=row_index+4; engine_state<=E_ROW_INIT; end
                    end else lane_index<=lane_index+STORE_STEP;
"""),
]

fio = [
    ("""`ifdef QINGYU_OUT16
 // INT16 outputs: an output row is 8 words; output rows are 512 bytes apart.
 localparam [12:0] OROW_WORDS=8;
 localparam [32:0] OROW_BYTES=512;
`else
 localparam [12:0] OROW_WORDS=16;
 localparam [32:0] OROW_BYTES=1024;
`endif
""", """`ifdef QINGYU_OUT16
 // INT16 outputs: an output row is 8 words; output rows are 512 bytes apart.
 localparam [12:0] OROW_WORDS=8;
 localparam [32:0] OROW_BYTES=512;
 // combo4: the accelerator takes a whole packed input word per cycle, and
 // weight commands answer at once (the transfer finishes in the background;
 // START waits for it and reports a failed background read).
 localparam XPAIR=1, WL_ASYNC=1;
`else
 localparam [12:0] OROW_WORDS=16;
 localparam [32:0] OROW_BYTES=1024;
 localparam XPAIR=0, WL_ASYNC=0;
`endif
 reg start_wl_err; // START response carries a failed async weight transfer
"""),
    ("""      transfer_words<=input_full_cmd ? 3168 : stage256_cmd ? 256 : batch_cmd ? block_remaining : loading ? 16 : OROW_WORDS;
""", """      transfer_words<=input_full_cmd ? 3168 : stage256_cmd ? 256 : batch_cmd ? block_remaining : (loading || input_cmd) ? 16 : OROW_WORDS;
"""),
    ("""     if (input_block) phase<=mem_rsp_err ? IDLE : INPUT_HI;
""", """     if (input_block && XPAIR) begin
      // both halves were written this cycle; the next read already launched
      if (!mem_rsp_err) begin word_number<=word_number+1'b1; dst_addr<=dst_addr+4; end
      phase<=(mem_rsp_err || word_number==transfer_words-1) ? IDLE : (mem_cmd_ready ? READ_RSP : READ_CMD);
     end
     else if (input_block) phase<=mem_rsp_err ? IDLE : INPUT_HI;
"""),
    ("""wire input_read_next = phase==INPUT_HI && word_number!=transfer_words-1;
""", """wire input_read_next = XPAIR ? (phase==READ_RSP && input_block && blk_rsp && !mem_rsp_err && word_number!=transfer_words-1)
                              : (phase==INPUT_HI && word_number!=transfer_words-1);
"""),
    ("""  .input_write(rst_n && input_block && ((phase==READ_RSP && blk_rsp && !mem_rsp_err) || phase==INPUT_HI)),
""", """  .input_write(rst_n && input_block && ((phase==READ_RSP && blk_rsp && !mem_rsp_err) || phase==INPUT_HI)),
  .input_pair(XPAIR==1), .input_data_hi(mem_rsp_rdata[31:16]),
"""),
    ("""    if (block_cmd && weight_cmd && legal_block) wl_pending_rsp<=1;
""", """    if (block_cmd && weight_cmd && legal_block && !WL_ASYNC) wl_pending_rsp<=1;
    start_wl_err<=WL_ASYNC && acc_selected && start_cmd && !icb_cmd_read && wl_error;
"""),
    ("""   host_valid<=0; host_code<=0; wl_pending_rsp<=0;
""", """   host_valid<=0; host_code<=0; wl_pending_rsp<=0; start_wl_err<=0;
"""),
    ("""assign icb_rsp_err = owner_block ? (transfer_error || (wl_pending_rsp && wl_error)) : owner_accel ? acc_rsp_err : local_error;
""", """assign icb_rsp_err = owner_block ? (transfer_error || (wl_pending_rsp && wl_error)) : owner_accel ? (acc_rsp_err || start_wl_err) : local_error;
"""),
]

patch("qingyu_accel.sv", accel)
patch("qingyu_fio.sv", fio)
