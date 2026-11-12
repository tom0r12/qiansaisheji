// System-bus endpoint. One outstanding response, including host notification.
module qingyu_fio (
 input wire clk, input wire rst_n,
`ifdef QINGYU_BLOCK_COPY
 input wire cpu_cmd_valid, cpu_cmd_read, cpu_rsp_ready,
 input wire [31:0] cpu_cmd_addr, cpu_cmd_wdata,
 input wire [3:0] cpu_cmd_wmask,
 output wire cpu_cmd_ready, cpu_rsp_valid, cpu_rsp_err,
 output wire [31:0] cpu_rsp_rdata,
 output wire mem_cmd_valid, mem_cmd_read, mem_rsp_ready,
 output wire [31:0] mem_cmd_addr, mem_cmd_wdata,
 output wire [3:0] mem_cmd_wmask,
 input wire mem_cmd_ready, mem_rsp_valid, mem_rsp_err,
 input wire [31:0] mem_rsp_rdata,
 // opt5 multi-port shared SRAM: extra masters (see header comment of patch)
 output wire cw_cmd_valid, input wire cw_cmd_ready, output wire [31:0] cw_cmd_addr, cw_cmd_wdata,
 input wire cw_rsp_valid, cw_rsp_err,
 output wire ld_cmd_valid, input wire ld_cmd_ready, output wire [31:0] ld_cmd_addr,
 input wire ld_rsp_valid, ld_rsp_err, input wire [31:0] ld_rsp_rdata,
 output wire sr_cmd_valid, input wire sr_cmd_ready, output wire [31:0] sr_cmd_addr,
 input wire sr_rsp_valid, sr_rsp_err, input wire [31:0] sr_rsp_rdata,
 output wire sw_cmd_valid, input wire sw_cmd_ready, output wire [31:0] sw_cmd_addr, sw_cmd_wdata,
 input wire sw_rsp_valid, sw_rsp_err,
 // opt11 input-load engine port
 output wire in_cmd_valid, input wire in_cmd_ready, output wire [31:0] in_cmd_addr,
 input wire in_rsp_valid, in_rsp_err, input wire [31:0] in_rsp_rdata,
`endif
 input wire icb_cmd_valid, output wire icb_cmd_ready,
 input wire icb_cmd_read, input wire [31:0] icb_cmd_addr,
 input wire [31:0] icb_cmd_wdata, input wire [3:0] icb_cmd_wmask,
 output wire icb_rsp_valid, input wire icb_rsp_ready,
 output wire [31:0] icb_rsp_rdata, output wire icb_rsp_err,
 output reg host_valid, output reg [31:0] host_code
);
 reg pending, owner_accel, local_error;
 reg [31:0] local_data;
 wire select_accel = icb_cmd_addr[31:16] == 16'hf000;
 wire select_host = icb_cmd_addr == 32'hf0010000;
 wire acc_cmd_ready, acc_rsp_valid, acc_rsp_err;
 wire [31:0] acc_rsp_data;
`ifdef QINGYU_BLOCK_COPY
 // The E203 supplies one bounded 64-byte destination per command.
 localparam IDLE=0, READ_CMD=1, READ_RSP=2, WRITE_CMD=3, WRITE_RSP=4, INPUT_HI=5, COPY=6, CP_DRAIN=7;
`ifdef QINGYU_OUT16
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
 localparam M_IDLE=0, M_SHIFT_REQ=1, M_SHIFT_RSP=2, M_LO_REQ=3, M_LO_RSP=4,
            M_HI_REQ=5, M_HI_RSP=6, M_WR=7;
 reg [2:0] phase;
 reg [11:0] word_number;
 reg input_block, batch_block;
 reg [7:0] input_group;
 reg [12:0] transfer_words;
 wire [7:0] block_remaining;
 wire block_next_valid;
 wire [31:0] block_next_data;
 reg [31:0] dst_addr, loaded_word;
 reg load_block, transfer_error, cpu_outstanding;
 wire weight_load_ok;
 wire accel_busy, accel_meta_phase;
 // Weight prefetch engine: reads the next tile's weights from the live bank
 // while the CPU keeps issuing output copies, so the transfer costs no CPU time.
 reg wl_busy, wl_wait, wl_tile;
 reg [9:0] wl_word;
 reg [31:0] wl_addr;
 reg [4:0] wl_pair;
 reg rsp_is_wl;
 reg wl_pending_rsp; // hold the ICB response until the background transfer completes
 reg wl_error;       // background weight read failed; surfaced on that command's response
 wire wl_last;
 wire blk_rsp, wl_rsp, wl_req, wl_rsp_ok, blk_req, meta_req, meta_rsp;
 reg meta_busy, rsp_is_meta;
 // Background staging engine (opt4): copies W pairs start..7 from the staging
 // image (live + 0x40000) into the live W buffer, pair-major, 64 rows x 16
 // words per pair, using only bus cycles every other engine leaves idle.
 // A weight command waits until its pair has been fully staged.
 // opt5: reads on sr_*, writes on sw_*; st_{p,k,w} is the write (completion)
 // pointer used by the weight-command hold, st_r{p,k,w} the read pointer.
 reg st_busy, st_rd_done, st_buf_v;
 // Staging errors are sticky for this transfer and reported by START/WAIT.
 // Completion follows the final write response, not merely its acceptance.
 reg st_error, st_last_pending;
 reg [31:0] st_wbase, st_buf;
 reg [2:0] st_p, st_rp;
 reg [5:0] st_k, st_rk;
 reg [3:0] st_w, st_rw;
 wire st_rsp;
 // opt6 pre-copy (bias/shift) ahead of the W pairs
 reg [31:0] pre_base;
 reg [11:0] pre_words, pre_rc, pre_wc;
 reg rd_pre, wr_pre;
 // opt5 block staging copy: read pointer, one-word buffer, write outstanding
 reg [12:0] cp_rd;
 reg cp_buf_v, cp_err, cw_out;
 reg [31:0] cp_buf;
 // opt8 automatic write-back: destination queue (row 0 of a tile), batch index
 localparam [3:0] AW_BATCHES = 4'd13; // ceil(99/8)
 reg [31:0] aw_q0, aw_q1;
 reg [1:0] aw_cnt;
 reg [3:0] aw_bidx;
 reg aw_active, aw_error;
 reg [2:0] meta_state;
 reg [3:0] meta_lane;
 reg [1:0] meta_seg;
 reg [31:0] meta_bias_base, meta_shift_base, meta_bias_cur, meta_shift_cur;
 reg [31:0] meta_lo_w, meta_hi_w, meta_shift_w;
 wire [31:0] meta_rd_addr;
 wire [31:0] blk_addr, blk_wdata, wl_addr_next;
 wire blk_read;
 wire weight_tile_cmd=icb_cmd_addr==32'hf0000080;
 wire weight_cmd=weight_tile_cmd || icb_cmd_addr[31:7]==(32'hf0000800>>7);
 wire input_full_cmd=icb_cmd_addr==32'hf0000090;
 wire stage256_cmd=icb_cmd_addr==32'hf0000084;
 wire input_cmd=input_full_cmd || icb_cmd_addr>=32'hf0000a00 && icb_cmd_addr<32'hf0000d18;
 wire batch_cmd=icb_cmd_addr==32'hf000003c || icb_cmd_addr==32'hf0000040;
 // Block metadata: per layer the driver stores the live bias/shift base
 // addresses; per tile it sends the column base and the FIO gathers the 16
 // lanes (bias 32-bit halves + shift) from shared SRAM into the accel.
 wire meta_shift_cmd=icb_cmd_addr==32'hf00000a4;
 wire meta_bias_cmd=icb_cmd_addr==32'hf00000a8;
 wire meta_blk_cmd=icb_cmd_addr==32'hf00000a0;
 wire meta_cmd=meta_shift_cmd || meta_bias_cmd || meta_blk_cmd;
 wire st_cmd=icb_cmd_addr==32'hf00000b0;
 wire st_pre_cmd=icb_cmd_addr==32'hf00000b4;
 wire st_cnt_cmd=icb_cmd_addr==32'hf00000b8;
 wire cpa_cnt_cmd=icb_cmd_addr==32'hf00000bc;
 wire cpa_cmd=icb_cmd_addr==32'hf00000c8;
 // opt12: held until the accelerator is idle, so the CPU stalls on the bus
 // instead of polling the status register.
 wire wait_cmd=icb_cmd_addr==32'hf00000cc;
 reg [12:0] cpa_count;
 reg cp_async, cpa_err;
 reg owner_imm, ctl_err; // response owner: command answered at once
 // opt11 input engine
 reg il_busy, il_wait, il_err;
 reg [11:0] il_word, il_words;
 reg [7:0] il_group;
 reg [31:0] il_addr;
 // opt10: pre-copy region bookkeeping for the read holds
 wire [31:0] pre_wr_addr = pre_base + {18'b0, pre_wc, 2'b00};
 wire [31:0] pre_end_addr = pre_base + {18'b0, pre_words, 2'b00};
 wire meta_pre_overlap = wr_pre &&
   ((pre_base < meta_bias_base + 32'h800 && meta_bias_base < pre_end_addr) ||
    (pre_base < meta_shift_base + 32'h100 && meta_shift_base < pre_end_addr));
 wire aw_cmd=icb_cmd_addr==32'hf00000c0;
 wire aw_wait_cmd=icb_cmd_addr==32'hf00000c4;
 // Weight source pair = wdata[8:6] (W rows are 512 bytes, 0x200-aligned base).
 wire st_hold_weight = st_busy && (icb_cmd_wdata[8:6] >= st_p);
 wire batch_release_cmd=!icb_cmd_read && icb_cmd_wmask==4'hf && icb_cmd_wdata==32'd1 &&
                        (icb_cmd_addr==32'hf0000020 || icb_cmd_addr==32'hf0000024);
 wire start_cmd=icb_cmd_addr==32'hf0000004;
 wire block_cmd=stage256_cmd || input_cmd || batch_cmd || icb_cmd_addr==32'hf0000030 || icb_cmd_addr==32'hf0000034 ||
                icb_cmd_addr==32'hf0000038 || weight_cmd || meta_cmd || st_cmd || st_pre_cmd || st_cnt_cmd ||
                cpa_cnt_cmd || cpa_cmd || wait_cmd ||
                aw_cmd || aw_wait_cmd;
 wire loading=stage256_cmd || icb_cmd_addr==32'hf0000038;
 wire block_valid, block_slot, block_has_row;
 wire [31:0] block_data;
 wire dest_ok= (loading || OROW_WORDS==16 ? icb_cmd_wdata[5:0]==0 : icb_cmd_wdata[4:0]==0) &&
              (loading ? (icb_cmd_wdata>=32'ha0000000 && icb_cmd_wdata<=32'ha003ffc0) :
                         (icb_cmd_wdata>=32'ha0000000 && icb_cmd_wdata<=32'ha007ffc0));
 // Each command reads eight words from each of two adjacent live W rows.
 // The last shared address is base + 512 + 28. Reject staging/out-of-range reads.
 wire weight_source_ok=icb_cmd_addr[1:0]==0 && icb_cmd_wdata[4:0]==0 &&
                       icb_cmd_wdata>=32'ha0000000 && icb_cmd_wdata<=32'ha003fde0;
 wire [32:0] batch_rows={25'b0,block_remaining}>>(OROW_WORDS==16 ? 4 : 3);
 wire [32:0] batch_last={1'b0,icb_cmd_wdata}+(batch_rows-1)*OROW_BYTES+(OROW_WORDS*4-1);
 wire batch_row_multiple = OROW_WORDS==16 ? block_remaining[3:0]==0 : block_remaining[2:0]==0;
 wire row_last_word = OROW_WORDS==16 ? word_number[3:0]==15 : word_number[2:0]==7;
 wire [31:0] row_jump = OROW_BYTES[31:0]-(OROW_WORDS-1)*4;
 wire meta_args_ok = meta_blk_cmd ?
   (icb_cmd_wdata<=32'd240 && icb_cmd_wdata[3:0]==0 &&
    meta_bias_base>=32'ha0000000 && meta_bias_base<=32'ha007f800 &&
    meta_shift_base>=32'ha0000000 && meta_shift_base<=32'ha007ff00) :
   (icb_cmd_wdata>=32'ha0000000 && icb_cmd_wdata<=32'ha007ffc0 &&
    (meta_shift_cmd ? icb_cmd_wdata[1:0]==0 : icb_cmd_wdata[2:0]==0));
 wire legal_block=!icb_cmd_read && icb_cmd_wmask==4'hf &&
   (aw_wait_cmd || wait_cmd ? 1'b1 :
    aw_cmd ? icb_cmd_wdata[4:0]==0 && icb_cmd_wdata>=32'ha0000000 &&
             icb_cmd_wdata<=32'ha007ffe0-32'd50176 :
    cpa_cnt_cmd ? icb_cmd_wdata[31:13]==0 && icb_cmd_wdata[12:0]!=0 :
    cpa_cmd ? icb_cmd_wdata[5:0]==0 && icb_cmd_wdata>=32'ha0000000 && cpa_count!=0 &&
              icb_cmd_wdata + {17'b0, cpa_count, 2'b00} <= 32'ha0040000 :
    st_cnt_cmd ? icb_cmd_wdata[31:12]==0 && icb_cmd_wdata[11:0]!=0 &&
                 pre_base + {18'b0, icb_cmd_wdata[11:0], 2'b00} <= 32'ha0040000 :
    st_pre_cmd ? icb_cmd_wdata[5:0]!=0 && icb_cmd_wdata>=32'ha0000000 &&
                 ({icb_cmd_wdata[31:6],6'b0}+{20'b0,icb_cmd_wdata[5:0],6'b0})<=32'ha0040000 :
    st_cmd ? icb_cmd_wdata[5:0]==0 && icb_cmd_wdata>=32'ha0000000 &&
            {icb_cmd_wdata[31:9],9'b0}<=32'ha0038000 :
    meta_cmd ? meta_args_ok :
    input_cmd ? weight_source_ok && !accel_busy && (!input_full_cmd || icb_cmd_wdata<=32'ha003ce80) :
    weight_cmd ? weight_source_ok && weight_load_ok && (!weight_tile_cmd || icb_cmd_wdata<=32'ha00381e0) :
    dest_ok && (loading ? (!stage256_cmd || icb_cmd_wdata<=32'ha003fc00) :
     block_has_row && block_slot==(batch_cmd ? icb_cmd_addr==32'hf0000040 : icb_cmd_addr[2]) &&
     (!batch_cmd || (batch_row_multiple && block_remaining!=0 && batch_last<33'h0a0080000))));
 wire request_block=icb_cmd_valid && block_cmd && !pending;
 wire take_block=request_block && !cpu_outstanding;
 wire passthru=(phase==IDLE);
 wire acc_selected=select_accel && !block_cmd;
 // Batch release writes (0x20/0x24) only touch the accumulator handshake, not
 // the weight stream, so they may pass while wl_busy.  START must still wait
 // for the metadata gather and for the weight prefetch to finish.
 wire accel_cmd_ok=(!wl_busy || icb_cmd_read || batch_release_cmd) && (!meta_busy || !start_cmd) &&
                   (!il_busy || !start_cmd);
 // commands that never use the block-engine phase (answered at once)
 wire ctl_cmd = weight_cmd || meta_cmd || st_cmd || st_pre_cmd || st_cnt_cmd || aw_cmd || aw_wait_cmd ||
                cpa_cnt_cmd || wait_cmd || (XPAIR && input_cmd);
 wire imm_cmd = ctl_cmd || cpa_cmd;
 assign icb_cmd_ready=!pending && (block_cmd ? (!cpu_outstanding && (!weight_cmd || (!wl_busy && !st_hold_weight)) &&
                                                (!meta_cmd || (!meta_busy && !(meta_blk_cmd && meta_pre_overlap))) &&
                                                (!(st_cmd || st_pre_cmd || st_cnt_cmd) || !st_busy) &&
                                                (!aw_cmd || aw_cnt!=2'd2) && (!aw_wait_cmd || aw_cnt==2'd0) &&
                                                // transfer commands start only from IDLE (the write-back
                                                // engine may own the block engine meanwhile)
                                                (!(XPAIR && input_cmd) || !il_busy) && (!wait_cmd || !accel_busy) &&
                                                (ctl_cmd || phase==IDLE)) :
                                   (!acc_selected || acc_cmd_ready) && accel_cmd_ok);
 assign icb_rsp_valid=pending && (owner_accel ? acc_rsp_valid : (wl_pending_rsp ? !wl_busy : (owner_imm || passthru)));
 assign cpu_cmd_ready=passthru && !request_block && mem_cmd_ready;
 assign cpu_rsp_valid=passthru && blk_rsp;
 assign cpu_rsp_rdata=mem_rsp_rdata;
 assign cpu_rsp_err=mem_rsp_err;
 // During a staging copy, a successful response can launch the next transfer
 // on the same edge. If the downstream port stalls we retain address/data
 // and reissue in READ_CMD or WRITE_CMD. Weight commands instead run on the
 // prefetch engine below so they never hold up the CPU's output copies.
 wire output_write_next = phase==WRITE_RSP && !load_block && word_number!=transfer_words-1 && blk_rsp && !mem_rsp_err && block_next_valid;
 wire [31:0] output_next_addr=dst_addr+(batch_block && row_last_word ? row_jump : 32'd4);
 // opt10: an input word is read only after the staging engine has written it
 wire hold_cur = input_block && wr_pre && dst_addr >= pre_wr_addr && dst_addr < pre_end_addr;
 wire hold_nxt = input_block && wr_pre && (dst_addr+32'd4) >= pre_wr_addr && (dst_addr+32'd4) < pre_end_addr;
 wire input_read_next = XPAIR ? (phase==READ_RSP && input_block && blk_rsp && !mem_rsp_err && word_number!=transfer_words-1 && !hold_nxt)
                              : (phase==INPUT_HI && word_number!=transfer_words-1);
 wire stage_write_now = phase==READ_RSP && load_block && blk_rsp && !mem_rsp_err;
 wire stage_read_next = phase==WRITE_RSP && load_block && word_number!=transfer_words-1 && blk_rsp && !mem_rsp_err;
 // opt5 staging copy (0x38/0x84): read staging on mem_*, write live on cw_*.
 // cw_* has the highest bank priority, so its ready never depends on mem_*.
 wire cp_rsp = phase==COPY && mem_rsp_valid;
 wire cp_rsp_ok = cp_rsp && !mem_rsp_err;
 wire cp_have = cp_buf_v || cp_rsp_ok;
 assign cw_cmd_valid = rst_n && phase==COPY && cp_have;
 assign cw_cmd_addr = dst_addr + {18'b0, word_number, 2'b00};
 assign cw_cmd_wdata = cp_buf_v ? cp_buf : mem_rsp_rdata;
 wire cw_fire = cw_cmd_valid && cw_cmd_ready;
 // A fair arbiter may prefer a read over a write. Do not make this read's
 // valid depend on the write's ready (the old fixed-priority fabric allowed
 // that shortcut). The buffer must be empty before requesting another read.
 wire cp_read = phase==COPY && !cp_err && !(cp_rsp && mem_rsp_err) &&
                cp_rd != transfer_words && !cp_have;
 assign blk_req = passthru ? cpu_cmd_valid && !request_block :
                  (phase==READ_CMD && !hold_cur) || (phase==WRITE_CMD && (load_block || block_valid)) ||
                  stage_write_now || stage_read_next || input_read_next || output_write_next || cp_read;
 assign blk_addr = passthru ? cpu_cmd_addr : cp_read ? dst_addr + 32'h40000 + {17'b0, cp_rd, 2'b00} :
                  output_write_next ? output_next_addr : input_read_next ? dst_addr+4 :
                  stage_read_next ? dst_addr+32'h40004 :
                  phase==READ_CMD && !input_block ? dst_addr+32'h40000 : dst_addr;
 assign blk_read = passthru ? cpu_cmd_read : phase==READ_CMD || stage_read_next || input_read_next || cp_read;
 assign blk_wdata = passthru ? cpu_cmd_wdata : stage_write_now ? mem_rsp_rdata :
                  load_block ? loaded_word : output_write_next ? block_next_data : block_data;
 // The prefetch engine takes every bus cycle the copy engine leaves idle.
 assign blk_rsp = mem_rsp_valid;
 assign st_rsp = sr_rsp_valid;
 assign wl_rsp = ld_rsp_valid && rsp_is_wl;
 assign meta_rsp = ld_rsp_valid && rsp_is_meta;
 assign wl_rsp_ok = wl_rsp && !ld_rsp_err;
 assign wl_last = wl_tile ? wl_word==10'd511 : wl_word==10'd15;
 // A request may launch in the same cycle its predecessor answers, in which
 // case the address must already be stepped.
 assign wl_addr_next = wl_addr+(wl_word[2:0]==7 ? 32'd484 : 32'd4);
 // The fill-in weight prefetcher outranks the metadata gatherer but never
 // preempts the CPU copy engine.  A weight command is a blocking MMIO write
 // (its response waits for the whole 512-word transfer), so stretching that
 // transfer with the 36-word background gather costs real cycles; the gather
 // still finishes long before the next START, which meta_busy gates anyway.
 assign wl_req = wl_busy && (!wl_wait || (wl_rsp && !wl_last)) && rst_n;
 assign meta_req = meta_busy && rst_n &&
                   (meta_state==M_SHIFT_REQ || meta_state==M_LO_REQ || meta_state==M_HI_REQ) && !wl_req;
 // Staging engine (opt5): pipelined copy, one read (sr_*) and one write (sw_*)
 // per cycle.  A read is issued only when the word it returns can be written
 // or buffered, so one buffer word suffices.
 wire st_fault = (sr_rsp_valid && sr_rsp_err) || (sw_rsp_valid && sw_rsp_err);
 wire st_have = st_buf_v || (st_rsp && !sr_rsp_err);
 assign sw_cmd_valid = rst_n && st_busy && st_have && !st_error && !st_fault;
 assign sw_cmd_addr = wr_pre ? pre_wr_addr : st_wbase + {17'b0, st_k, st_p, st_w, 2'b00};
 assign sw_cmd_wdata = st_buf_v ? st_buf : sr_rsp_rdata;
 wire sw_fire = sw_cmd_valid && sw_cmd_ready;
 assign sr_cmd_valid = rst_n && st_busy && !st_rd_done && !st_have && !st_error && !st_fault;
 assign sr_cmd_addr = (rd_pre ? pre_base + {18'b0, pre_rc, 2'b00} : st_wbase + {17'b0, st_rk, st_rp, st_rw, 2'b00}) + 32'h40000;
 wire sr_fire = sr_cmd_valid && sr_cmd_ready;
 assign mem_cmd_valid = blk_req;
 assign mem_cmd_addr = blk_addr;
 assign mem_cmd_read = blk_read;
 assign mem_cmd_wmask = passthru ? cpu_cmd_wmask : 4'hf;
 assign mem_cmd_wdata = blk_wdata;
 assign mem_rsp_ready = passthru ? cpu_rsp_ready :
                        (phase==READ_RSP || phase==WRITE_RSP || phase==COPY || phase==CP_DRAIN);
 assign ld_cmd_valid = wl_req || meta_req;
 assign ld_cmd_addr = meta_req ? meta_rd_addr : (wl_rsp ? wl_addr_next : wl_addr);
 // Metadata gatherer: reads 2 bias words per lane plus one shift word per
 // four lanes from the live shared SRAM, then writes the four 16-bit metadata
 // segments (bias[15:0], bias[31:16], bias[47:32], {8'b0,shift}) per lane.
 assign meta_rd_addr = (meta_state==M_SHIFT_REQ) ? meta_shift_cur+{28'b0,meta_lane[3:2],2'b00} :
                       (meta_state==M_LO_REQ)    ? meta_bias_cur+{25'b0,meta_lane,3'b000} :
                                                   meta_bias_cur+{25'b0,meta_lane,3'b000}+32'd4;
 wire meta_wr_en = meta_busy && (meta_state==M_WR) && !accel_meta_phase;
 wire [5:0] meta_wr_addr = {meta_lane,meta_seg};
 wire [15:0] meta_shift_byte = meta_shift_w >> {meta_lane[1:0],3'b000};
 wire [15:0] meta_wr_data = (meta_seg==2'd0) ? meta_lo_w[15:0] :
                            (meta_seg==2'd1) ? meta_lo_w[31:16] :
                            (meta_seg==2'd2) ? meta_hi_w[15:0] :
                                               {8'b0,meta_shift_byte[7:0]};
 wire block_pop=phase==WRITE_RSP && blk_rsp && !mem_rsp_err && !load_block;
 // opt8: the write-back engine starts only when no CPU access or command
 // response is outstanding, so passthrough responses are never displaced.
 wire aw_go = phase==IDLE && aw_cnt!=2'd0 && !aw_active && block_has_row && !(take_block && icb_cmd_ready) &&
              !pending && !cpu_outstanding && !cpu_cmd_valid && rst_n;
 wire aw_done = aw_active && phase==WRITE_RSP && blk_rsp && (mem_rsp_err || word_number==transfer_words-1);
 wire aw_release = aw_done && !mem_rsp_err;
 always @(posedge clk) begin
  if (!rst_n) begin
   aw_q0<=0; aw_q1<=0; aw_cnt<=0; aw_bidx<=0; aw_active<=0; aw_error<=0;
  end else begin
   if (aw_go) aw_active<=1;
   if (aw_done) begin
    aw_active<=0;
    if (mem_rsp_err) aw_error<=1;
   end
   // queue: push on 0xc0, pop after the 13th batch of the current tile
   if (aw_done && aw_bidx==AW_BATCHES-4'd1) begin
    aw_bidx<=0;
    aw_q0<=aw_q1;
    if (take_block && aw_cmd && legal_block && aw_cnt!=2'd2) begin
     if (aw_cnt==2'd1) aw_q0<=icb_cmd_wdata; else aw_q1<=icb_cmd_wdata;
    end else aw_cnt<=aw_cnt-2'd1;
   end else begin
    if (aw_done) aw_bidx<=aw_bidx+4'd1;
    if (take_block && aw_cmd && legal_block && aw_cnt!=2'd2) begin
     if (aw_cnt==2'd0) begin aw_q0<=icb_cmd_wdata; aw_error<=0; end else aw_q1<=icb_cmd_wdata;
     aw_cnt<=aw_cnt+2'd1;
    end
   end
  end
 end
 wire weight_write=rst_n && wl_rsp_ok;
 // ---- opt11 input engine ------------------------------------------------
 // a live word may be read once the copy that produces it has written it
 wire [31:0] il_issue_addr = (il_wait && in_rsp_valid) ? il_addr + 32'd4 : il_addr;
 wire il_hold = ((phase==COPY || phase==CP_DRAIN) && load_block &&
                 il_issue_addr >= dst_addr + {18'b0, word_number, 2'b00} &&
                 il_issue_addr < dst_addr + {17'b0, transfer_words, 2'b00}) ||
                (wr_pre && il_issue_addr >= pre_wr_addr && il_issue_addr < pre_end_addr);
 wire il_last = il_word == il_words - 12'd1;
 assign in_cmd_valid = rst_n && il_busy && (!il_wait || (in_rsp_valid && !il_last)) && !il_hold;
 assign in_cmd_addr = il_issue_addr;
 wire il_wr = rst_n && il_busy && in_rsp_valid && !in_rsp_err;
 always @(posedge clk) begin
  if (!rst_n) begin
   il_busy<=0; il_wait<=0; il_err<=0; il_word<=0; il_words<=0; il_group<=0; il_addr<=0;
   cpa_count<=0; cpa_err<=0;
  end else begin
   if (take_block && cpa_cnt_cmd && legal_block) cpa_count<=icb_cmd_wdata[12:0];
   if (take_block && cpa_cmd && legal_block && phase==IDLE && icb_cmd_ready) cpa_err<=0;
   if (cp_async && ((phase==COPY && mem_rsp_valid && mem_rsp_err) || (cw_rsp_valid && cw_rsp_err))) cpa_err<=1;
   if (XPAIR && take_block && input_cmd && legal_block && !il_busy) begin
    il_busy<=1; il_wait<=0; il_err<=0; il_word<=0; il_addr<=icb_cmd_wdata;
    il_words<=input_full_cmd ? 12'd3168 : 12'd16;
    il_group<=input_full_cmd ? 8'd0 : (icb_cmd_addr-32'hf0000a00)>>2;
   end else begin
    if (in_rsp_valid && il_busy) begin
     il_wait<=0; il_word<=il_word+12'd1; il_addr<=il_addr+32'd4;
     if (in_rsp_err) il_err<=1;
     if (in_rsp_err || il_last) il_busy<=0;
    end
    if (in_cmd_valid && in_cmd_ready) il_wait<=1;
   end
  end
 end
 always @(posedge clk) begin
  if (!rst_n) begin
   phase<=IDLE; transfer_error<=0; cpu_outstanding<=0; load_block<=0;
   cp_rd<=0; cp_buf_v<=0; cp_err<=0; cw_out<=0; cp_buf<=0;
   dst_addr<=0; word_number<=0; loaded_word<=0;
   input_block<=0; batch_block<=0; input_group<=0; transfer_words<=16;
  end else begin
   if (cpu_rsp_valid && cpu_rsp_ready) cpu_outstanding<=0;
   if (cpu_cmd_valid && cpu_cmd_ready) cpu_outstanding<=1;
   case (phase)
    IDLE: if (take_block && icb_cmd_ready) begin
     transfer_error<=!legal_block;
     if (legal_block && !ctl_cmd) begin
      dst_addr<=icb_cmd_wdata; word_number<=0; load_block<=loading || cpa_cmd; cp_async<=cpa_cmd;
      input_block<=input_cmd; batch_block<=batch_cmd; input_group<=input_full_cmd ? 0 : (icb_cmd_addr-32'hf0000a00)>>2;
      transfer_words<=cpa_cmd ? cpa_count : input_full_cmd ? 3168 : stage256_cmd ? 256 : batch_cmd ? block_remaining : (loading || input_cmd) ? 16 : OROW_WORDS;
      phase<=(loading || cpa_cmd) ? COPY : input_cmd ? READ_CMD : WRITE_CMD;
      cp_rd<=0; cp_buf_v<=0; cp_err<=0;
     end
    end else if (aw_go) begin
     dst_addr<=aw_q0 + {16'b0, aw_bidx, 12'b0}; word_number<=0; load_block<=0;
     input_block<=0; batch_block<=1; transfer_words<={5'b0, block_remaining}; phase<=WRITE_CMD;
    end
    READ_CMD: if (blk_req && mem_cmd_ready) phase<=READ_RSP;
    READ_RSP: if (blk_rsp) begin
     loaded_word<=mem_rsp_rdata; transfer_error<=mem_rsp_err;
     if (input_block && XPAIR) begin
      // both halves were written this cycle; the next read already launched
      if (!mem_rsp_err) begin word_number<=word_number+1'b1; dst_addr<=dst_addr+4; end
      phase<=(mem_rsp_err || word_number==transfer_words-1) ? IDLE : (input_read_next && mem_cmd_ready ? READ_RSP : READ_CMD);
     end
     else if (input_block) phase<=mem_rsp_err ? IDLE : INPUT_HI;
     else phase<=mem_rsp_err ? IDLE : (stage_write_now && mem_cmd_ready ? WRITE_RSP : WRITE_CMD);
    end
    INPUT_HI: begin
     word_number<=word_number+1'b1; dst_addr<=dst_addr+4;
     phase<=word_number==transfer_words-1 ? IDLE : (mem_cmd_ready ? READ_RSP : READ_CMD);
    end
    WRITE_CMD: if (blk_req && mem_cmd_ready) phase<=WRITE_RSP;
    WRITE_RSP: if (blk_rsp) begin
     transfer_error<=mem_rsp_err; word_number<=word_number+1'b1; dst_addr<=dst_addr+(batch_block && row_last_word ? row_jump : 32'd4);
     if (mem_rsp_err || word_number==transfer_words-1) phase<=IDLE;
     else if (load_block) phase<=stage_read_next && mem_cmd_ready ? READ_RSP : READ_CMD;
     else phase<=output_write_next && mem_cmd_ready ? WRITE_RSP : WRITE_CMD;
    end
    COPY: begin
     if (cp_read && mem_cmd_ready) cp_rd<=cp_rd+1'b1;
     if (cp_rsp && mem_rsp_err) begin transfer_error<=1; cp_err<=1; end
     if (cp_rsp_ok && !cw_fire) begin cp_buf<=mem_rsp_rdata; cp_buf_v<=1; end
     else if (cp_buf_v && cw_fire) cp_buf_v<=0;
     if (cw_fire) word_number<=word_number+1'b1;
     if ((cw_fire && word_number==transfer_words-1) || (cp_rsp && mem_rsp_err)) phase<=CP_DRAIN;
    end
    CP_DRAIN: if (!cw_out || cw_rsp_valid) phase<=IDLE;
    default: phase<=IDLE;
   endcase
   if (cw_fire) cw_out<=1; else if (cw_rsp_valid) cw_out<=0;
   if (cw_rsp_valid && cw_rsp_err) transfer_error<=1;
  end
 end
 // Independent weight prefetch: one shared-memory read per idle bus cycle,
 // written straight into the accelerator's idle W bank.
 always @(posedge clk) begin
  if (!rst_n) begin
   wl_busy<=0; wl_wait<=0; wl_word<=0; wl_addr<=0; wl_tile<=0; wl_pair<=0; wl_error<=0;
  end else begin
   if (take_block && weight_cmd && legal_block && !st_hold_weight && !wl_busy) begin
    wl_busy<=1; wl_wait<=0; wl_word<=0; wl_addr<=icb_cmd_wdata; wl_error<=0;
    wl_tile<=weight_tile_cmd; wl_pair<=icb_cmd_addr[6:2];
   end
   if (wl_rsp) begin
    wl_wait<=0;
    wl_word<=wl_word+10'd1;
    wl_addr<=wl_addr_next;
    // A failed background read must surface on the command's ICB response:
    // the weight command still owns the bus (pending) until wl_busy drops.
    if (ld_rsp_err) wl_error<=1;
    if (ld_rsp_err || wl_last) wl_busy<=0;
   end
   if (wl_req && ld_cmd_ready) wl_wait<=1;
  end
 end
  // Metadata block engine: started by 0xf00000a0 (arg = column base).  The
  // per-layer 0xf00000a4/0xf00000a8 commands set the live shift/bias bases.
  // One gather runs per tile and overlaps the previous tile's MAC work; the
  // next START is stalled until it completes (meta_busy).
  always @(posedge clk) begin
   if (!rst_n) begin
    meta_busy<=0; meta_state<=M_IDLE; meta_lane<=0; meta_seg<=0;
    meta_bias_base<=0; meta_shift_base<=0; meta_bias_cur<=0; meta_shift_cur<=0;
    meta_lo_w<=0; meta_hi_w<=0; meta_shift_w<=0;
   end else if (take_block && legal_block && meta_cmd && !meta_busy && !(meta_blk_cmd && meta_pre_overlap)) begin
    if (meta_shift_cmd) meta_shift_base<=icb_cmd_wdata;
    else if (meta_bias_cmd) meta_bias_base<=icb_cmd_wdata;
    else begin
     meta_bias_cur<=meta_bias_base+{21'b0,icb_cmd_wdata[7:0],3'b000};
     meta_shift_cur<=meta_shift_base+{24'b0,icb_cmd_wdata[7:0]};
     meta_lane<=0; meta_seg<=0; meta_state<=M_SHIFT_REQ; meta_busy<=1;
    end
   end else begin
    case (meta_state)
     M_SHIFT_REQ: if (meta_req && ld_cmd_ready) meta_state<=M_SHIFT_RSP;
     M_SHIFT_RSP: if (meta_rsp) begin meta_shift_w<=ld_rsp_rdata; meta_state<=M_LO_REQ; end
     M_LO_REQ: if (meta_req && ld_cmd_ready) meta_state<=M_LO_RSP;
     M_LO_RSP: if (meta_rsp) begin meta_lo_w<=ld_rsp_rdata; meta_state<=M_HI_REQ; end
     M_HI_REQ: if (meta_req && ld_cmd_ready) meta_state<=M_HI_RSP;
     M_HI_RSP: if (meta_rsp) begin meta_hi_w<=ld_rsp_rdata; meta_seg<=0; meta_state<=M_WR; end
     M_WR: if (!accel_meta_phase) begin
      meta_seg<=meta_seg+2'd1;
      if (meta_seg==2'd3) begin
       if (meta_lane==4'd15) begin meta_busy<=0; meta_state<=M_IDLE; end
       else begin
        meta_lane<=meta_lane+4'd1;
        meta_state<=(meta_lane[1:0]==2'd3) ? M_SHIFT_REQ : M_LO_REQ;
       end
      end
     end
     default: meta_state<=M_IDLE;
    endcase
   end
  end
  always @(posedge clk)
   if (!rst_n) begin rsp_is_wl<=0; rsp_is_meta<=0; end
   else if (ld_cmd_valid && ld_cmd_ready) begin rsp_is_wl<=wl_req; rsp_is_meta<=meta_req; end
  // Staging engine (opt5): pair-major copy of W pairs start..7 from the staging
  // image (live + 0x40000) into the live W buffer.  st_p advances when the
  // last word of a pair has been written, so it is a completion pointer.
  always @(posedge clk) begin
   if (!rst_n) begin
    st_busy<=0; st_rd_done<=0; st_buf_v<=0; st_wbase<=0; st_buf<=0;
    st_error<=0; st_last_pending<=0;
    st_p<=0; st_k<=0; st_w<=0; st_rp<=0; st_rk<=0; st_rw<=0;
    pre_base<=0; pre_words<=0; pre_rc<=0; pre_wc<=0; rd_pre<=0; wr_pre<=0;
   end else if (st_fault) begin
    // The merger admits one global DMA transaction at a time. On a failed
    // response neither staging port issues a successor; discard buffered data.
    st_error<=1; st_busy<=0; st_rd_done<=1; st_buf_v<=0;
    st_last_pending<=0; rd_pre<=0; wr_pre<=0;
   end else if (take_block && st_pre_cmd && legal_block && !st_busy) begin
    pre_base<={icb_cmd_wdata[31:6],6'b0}; pre_words<={2'b0,icb_cmd_wdata[5:0],4'b0};
   end else if (take_block && st_cnt_cmd && legal_block && !st_busy) begin
    pre_words<=icb_cmd_wdata[11:0];
   end else if (take_block && st_cmd && legal_block && !st_busy) begin
    rd_pre<=pre_words!=0; wr_pre<=pre_words!=0; pre_rc<=0; pre_wc<=0; pre_words<=pre_words;
    st_busy<=1; st_rd_done<=0; st_buf_v<=0; st_wbase<={icb_cmd_wdata[31:9],9'b0};
    st_error<=0; st_last_pending<=0;
    st_p<=icb_cmd_wdata[8:6]; st_k<=0; st_w<=0;
    st_rp<=icb_cmd_wdata[8:6]; st_rk<=0; st_rw<=0;
   end else begin
    if (sr_fire && rd_pre) begin
     pre_rc<=pre_rc+12'd1;
     if (pre_rc==pre_words-12'd1) rd_pre<=0;
    end else if (sr_fire) begin
     st_rw<=st_rw+4'd1;
     if (st_rw==4'd15) begin st_rk<=st_rk+6'd1; if (st_rk==6'd63) st_rp<=st_rp+3'd1; end
     if (st_rp==3'd7 && st_rk==6'd63 && st_rw==4'd15) st_rd_done<=1;
    end
    if (st_rsp && !sr_rsp_err && !sw_fire) begin st_buf<=sr_rsp_rdata; st_buf_v<=1; end
    else if (st_buf_v && sw_fire) st_buf_v<=0;
    if (sw_fire && wr_pre) begin
     pre_wc<=pre_wc+12'd1;
     if (pre_wc==pre_words-12'd1) begin wr_pre<=0; pre_words<=0; end
    end else if (sw_fire) begin
     st_w<=st_w+4'd1;
     if (st_w==4'd15) begin
      st_k<=st_k+6'd1;
      if (st_k==6'd63) begin st_p<=st_p+3'd1; if (st_p==3'd7) st_last_pending<=1; end
     end
    end
    if (sw_rsp_valid && st_last_pending) begin st_busy<=0; st_last_pending<=0; end
   end
  end
 reg owner_block, owner_aw_wait, owner_wait;
 always @(posedge clk)
  if (!rst_n) begin owner_block<=0; owner_aw_wait<=0; owner_wait<=0; owner_imm<=0; ctl_err<=0; end
  else if (icb_cmd_valid && icb_cmd_ready) begin
   owner_block<=block_cmd; owner_aw_wait<=aw_wait_cmd; owner_wait<=wait_cmd;
   owner_imm<=block_cmd && imm_cmd; ctl_err<=!legal_block;
  end
`else
 wire acc_selected=select_accel;
 assign icb_cmd_ready = !pending && (select_accel ? acc_cmd_ready : 1'b1);
 assign icb_rsp_valid = pending && (owner_accel ? acc_rsp_valid : 1'b1);
`endif
 assign icb_rsp_rdata = owner_accel ? acc_rsp_data : local_data;
`ifdef QINGYU_BLOCK_COPY
 assign icb_rsp_err = owner_imm ? (ctl_err || (owner_aw_wait && aw_error) || ((owner_aw_wait || owner_wait) && st_error)) :
                      owner_block ? (transfer_error || (wl_pending_rsp && wl_error) || (owner_aw_wait && aw_error)) :
                      owner_accel ? (acc_rsp_err || start_wl_err) : local_error;
`else
 assign icb_rsp_err = owner_accel ? acc_rsp_err : local_error;
`endif
 `ifdef QINGYU_READ_AHEAD
`ifdef QINGYU_OUT16
 qingyu_accel #(.LANES(16), .STREAM_MAC(1), .DOUBLE_BUFFER(1), .PIPE_MAC(1), .READ_AHEAD(1), .WEIGHT_STREAM(1), .OUT16(1)) u_accel(
`else
 qingyu_accel #(.LANES(16), .STREAM_MAC(1), .DOUBLE_BUFFER(1), .PIPE_MAC(1), .READ_AHEAD(1), .WEIGHT_STREAM(1)) u_accel(
`endif
 `elsif QINGYU_PIPE_MAC
 qingyu_accel #(.LANES(16), .STREAM_MAC(1), .DOUBLE_BUFFER(1), .PIPE_MAC(1)) u_accel(
 `elsif QINGYU_DOUBLE_BUFFER
 qingyu_accel #(.LANES(16), .STREAM_MAC(1), .DOUBLE_BUFFER(1)) u_accel(
 `elsif QINGYU_FAST_TASK
 qingyu_accel #(.LANES(16), .STREAM_MAC(1)) u_accel(
 `else
 qingyu_accel u_accel(
 `endif
  .clk(clk), .rst_n(rst_n),
  `ifdef QINGYU_BLOCK_COPY
  .input_write(il_wr || (rst_n && input_block && ((phase==READ_RSP && blk_rsp && !mem_rsp_err) || phase==INPUT_HI))),
  .input_pair(XPAIR==1), .input_data_hi(il_wr ? in_rsp_rdata[31:16] : mem_rsp_rdata[31:16]),
  .input_elem(il_wr ? {il_group,5'b0}+{il_word,1'b0} : {input_group,5'b0}+{word_number,1'b0}+(phase==INPUT_HI)),
  .input_data(il_wr ? in_rsp_rdata[15:0] : phase==INPUT_HI ? loaded_word[31:16] : mem_rsp_rdata[15:0]),
  .block_next_valid(block_next_valid), .block_next_data(block_next_data), .block_remaining(block_remaining), .block_pop(block_pop), .block_release(aw_release), .block_valid(block_valid), .block_slot(block_slot),
  .block_has_row(block_has_row), .block_data(block_data),
  .weight_load_ok(weight_load_ok), .weight_write(weight_write), .weight_pair(wl_word[2:0]),
  .weight_k(wl_tile ? wl_word[8:3] : {wl_pair,wl_word[3]}), .weight_word(ld_rsp_rdata),
  .meta_wr_en(meta_wr_en), .meta_wr_addr(meta_wr_addr), .meta_wr_data(meta_wr_data),
  .meta_read_phase(accel_meta_phase),
`endif
  .accel_busy(accel_busy),
  // The accelerator may only see a command the FIO actually accepted; the
  // prefetch gate must therefore also mask icb_cmd_valid, not just readiness.
  .icb_cmd_valid(icb_cmd_valid && !pending && acc_selected && accel_cmd_ok),
  .icb_cmd_ready(acc_cmd_ready), .icb_cmd_read(icb_cmd_read),
  .icb_cmd_addr(icb_cmd_addr[15:0]), .icb_cmd_wdata(icb_cmd_wdata),
  .icb_cmd_wmask(icb_cmd_wmask), .icb_rsp_valid(acc_rsp_valid),
  .icb_rsp_ready(pending && owner_accel && icb_rsp_ready),
  .icb_rsp_rdata(acc_rsp_data), .icb_rsp_err(acc_rsp_err)
 );
 always @(posedge clk) begin
  if (!rst_n) begin
   pending<=0; owner_accel<=0; local_error<=0; local_data<=0;
   host_valid<=0; host_code<=0; wl_pending_rsp<=0; start_wl_err<=0;
  end else begin
   host_valid<=0;
   if (icb_rsp_valid && icb_rsp_ready) begin pending<=0; wl_pending_rsp<=0; end
   if (icb_cmd_valid && icb_cmd_ready) begin
    pending<=1; owner_accel<=acc_selected;
    if (block_cmd && weight_cmd && legal_block && !WL_ASYNC) wl_pending_rsp<=1;
    start_wl_err<=WL_ASYNC && acc_selected && start_cmd && !icb_cmd_read && (wl_error || il_err || cpa_err || st_error);
    local_error<=!select_host || (icb_cmd_addr[1:0]!=0) ||
                 (!icb_cmd_read && icb_cmd_wmask!=4'hf);
    local_data<=host_code;
    if (select_host && !icb_cmd_read && icb_cmd_wmask==4'hf) begin
     host_code<=icb_cmd_wdata; host_valid<=1;
    end
   end
  end
 end
endmodule
