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
 localparam IDLE=0, READ_CMD=1, READ_RSP=2, WRITE_CMD=3, WRITE_RSP=4, INPUT_HI=5;
`ifdef QINGYU_OUT16
 // INT16 outputs: an output row is 8 words; output rows are 512 bytes apart.
 localparam [12:0] OROW_WORDS=8;
 localparam [32:0] OROW_BYTES=512;
`else
 localparam [12:0] OROW_WORDS=16;
 localparam [32:0] OROW_BYTES=1024;
`endif
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
 reg st_busy, st_wait, st_out_w, st_have, rsp_is_st;
 reg [31:0] st_wbase, st_data;
 reg [2:0] st_p;
 reg [5:0] st_k;
 reg [3:0] st_w;
 wire st_req, st_rsp, st_nxt_w;
 wire [31:0] st_cur, st_cmd_addr, st_cmd_wdata;
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
 // Weight source pair = wdata[8:6] (W rows are 512 bytes, 0x200-aligned base).
 wire st_hold_weight = st_busy && (icb_cmd_wdata[8:6] >= st_p);
 wire batch_release_cmd=!icb_cmd_read && icb_cmd_wmask==4'hf && icb_cmd_wdata==32'd1 &&
                        (icb_cmd_addr==32'hf0000020 || icb_cmd_addr==32'hf0000024);
 wire start_cmd=icb_cmd_addr==32'hf0000004;
 wire block_cmd=stage256_cmd || input_cmd || batch_cmd || icb_cmd_addr==32'hf0000030 || icb_cmd_addr==32'hf0000034 ||
                icb_cmd_addr==32'hf0000038 || weight_cmd || meta_cmd || st_cmd;
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
   (st_cmd ? icb_cmd_wdata[5:0]==0 && icb_cmd_wdata>=32'ha0000000 &&
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
 wire accel_cmd_ok=(!wl_busy || icb_cmd_read || batch_release_cmd) && (!meta_busy || !start_cmd);
 assign icb_cmd_ready=!pending && (block_cmd ? (!cpu_outstanding && (!weight_cmd || (!wl_busy && !st_hold_weight)) &&
                                                (!meta_cmd || !meta_busy) && (!st_cmd || !st_busy)) :
                                   (!acc_selected || acc_cmd_ready) && accel_cmd_ok);
 assign icb_rsp_valid=pending && (owner_accel ? acc_rsp_valid : (wl_pending_rsp ? !wl_busy : passthru));
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
 wire input_read_next = phase==INPUT_HI && word_number!=transfer_words-1;
 wire stage_write_now = phase==READ_RSP && load_block && blk_rsp && !mem_rsp_err;
 wire stage_read_next = phase==WRITE_RSP && load_block && word_number!=transfer_words-1 && blk_rsp && !mem_rsp_err;
 assign blk_req = passthru ? cpu_cmd_valid && !request_block :
                  phase==READ_CMD || (phase==WRITE_CMD && (load_block || block_valid)) ||
                  stage_write_now || stage_read_next || input_read_next || output_write_next;
 assign blk_addr = passthru ? cpu_cmd_addr :
                  output_write_next ? output_next_addr : input_read_next ? dst_addr+4 :
                  stage_read_next ? dst_addr+32'h40004 :
                  phase==READ_CMD && !input_block ? dst_addr+32'h40000 : dst_addr;
 assign blk_read = passthru ? cpu_cmd_read : phase==READ_CMD || stage_read_next || input_read_next;
 assign blk_wdata = passthru ? cpu_cmd_wdata : stage_write_now ? mem_rsp_rdata :
                  load_block ? loaded_word : output_write_next ? block_next_data : block_data;
 // The prefetch engine takes every bus cycle the copy engine leaves idle.
 assign blk_rsp = mem_rsp_valid && !rsp_is_wl && !rsp_is_meta && !rsp_is_st;
 assign st_rsp = mem_rsp_valid && rsp_is_st;
 assign wl_rsp = mem_rsp_valid && rsp_is_wl;
 assign meta_rsp = mem_rsp_valid && rsp_is_meta;
 assign wl_rsp_ok = wl_rsp && !mem_rsp_err;
 assign wl_last = wl_tile ? wl_word==10'd511 : wl_word==10'd15;
 // A request may launch in the same cycle its predecessor answers, in which
 // case the address must already be stepped.
 assign wl_addr_next = wl_addr+(wl_word[2:0]==7 ? 32'd484 : 32'd4);
 // The fill-in weight prefetcher outranks the metadata gatherer but never
 // preempts the CPU copy engine.  A weight command is a blocking MMIO write
 // (its response waits for the whole 512-word transfer), so stretching that
 // transfer with the 36-word background gather costs real cycles; the gather
 // still finishes long before the next START, which meta_busy gates anyway.
 assign wl_req = wl_busy && (!wl_wait || (wl_rsp && !wl_last)) && !blk_req && rst_n;
 assign meta_req = meta_busy && rst_n &&
                   (meta_state==M_SHIFT_REQ || meta_state==M_LO_REQ || meta_state==M_HI_REQ) && !blk_req && !wl_req;
 // Staging engine: next op is the write of the word just read, else a read.
 // st_have: a read word is held because the bus was taken when it returned.
 wire st_read_back = st_wait && st_rsp && !st_out_w;
 // v3: the next read may launch in the cycle a write answers (no bubble);
 // its address uses the already-stepped word counters.
 wire st_write_back = st_wait && st_rsp && st_out_w;
 wire st_last_word = st_p==3'd7 && st_k==6'd63 && st_w==4'd15;
 wire [3:0] st_w_n = st_w+4'd1;
 wire [5:0] st_k_n = st_w==4'd15 ? st_k+6'd1 : st_k;
 wire [2:0] st_p_n = (st_w==4'd15 && st_k==6'd63) ? st_p+3'd1 : st_p;
 wire [31:0] st_next = st_wbase + {17'b0, st_k_n, st_p_n, st_w_n, 2'b00};
 assign st_nxt_w = st_read_back || (!st_wait && st_have);
 assign st_cur = st_wbase + {17'b0, st_k, st_p, st_w, 2'b00};
 assign st_req = st_busy && rst_n && (!st_wait || st_read_back || (st_write_back && !st_last_word)) &&
                 !blk_req && !wl_req && !meta_req;
 assign st_cmd_addr = st_nxt_w ? st_cur : (st_write_back ? st_next : st_cur) + 32'h40000;
 assign st_cmd_wdata = st_read_back ? mem_rsp_rdata : st_data;
 assign mem_cmd_valid = blk_req || meta_req || wl_req || st_req;
 assign mem_cmd_addr = st_req ? st_cmd_addr : meta_req ? meta_rd_addr : (wl_req ? (wl_rsp ? wl_addr_next : wl_addr) : blk_addr);
 assign mem_cmd_read = st_req ? !st_nxt_w : meta_req ? 1'b1 : (wl_req ? 1'b1 : blk_read);
 assign mem_cmd_wmask = (meta_req || wl_req || st_req) ? 4'hf : (passthru ? cpu_cmd_wmask : 4'hf);
 assign mem_cmd_wdata = st_req ? st_cmd_wdata : (meta_req || wl_req) ? 32'b0 : blk_wdata;
 assign mem_rsp_ready = (rsp_is_wl || rsp_is_meta || rsp_is_st) ? 1'b1 : (passthru ? cpu_rsp_ready : phase==READ_RSP || phase==WRITE_RSP);
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
 wire weight_write=rst_n && wl_rsp_ok;
 always @(posedge clk) begin
  if (!rst_n) begin
   phase<=IDLE; transfer_error<=0; cpu_outstanding<=0; load_block<=0;
   dst_addr<=0; word_number<=0; loaded_word<=0;
   input_block<=0; batch_block<=0; input_group<=0; transfer_words<=16;
  end else begin
   if (cpu_rsp_valid && cpu_rsp_ready) cpu_outstanding<=0;
   if (cpu_cmd_valid && cpu_cmd_ready) cpu_outstanding<=1;
   case (phase)
    IDLE: if (take_block) begin
     transfer_error<=!legal_block;
     if (legal_block && !weight_cmd && !meta_cmd && !st_cmd) begin
      dst_addr<=icb_cmd_wdata; word_number<=0; load_block<=loading;
      input_block<=input_cmd; batch_block<=batch_cmd; input_group<=input_full_cmd ? 0 : (icb_cmd_addr-32'hf0000a00)>>2;
      transfer_words<=input_full_cmd ? 3168 : stage256_cmd ? 256 : batch_cmd ? block_remaining : loading ? 16 : OROW_WORDS;
      phase<=loading || input_cmd ? READ_CMD : WRITE_CMD;
     end
    end
    READ_CMD: if (blk_req && mem_cmd_ready) phase<=READ_RSP;
    READ_RSP: if (blk_rsp) begin
     loaded_word<=mem_rsp_rdata; transfer_error<=mem_rsp_err;
     if (input_block) phase<=mem_rsp_err ? IDLE : INPUT_HI;
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
    default: phase<=IDLE;
   endcase
  end
 end
 // Independent weight prefetch: one shared-memory read per idle bus cycle,
 // written straight into the accelerator's idle W bank.
 always @(posedge clk) begin
  if (!rst_n) begin
   wl_busy<=0; wl_wait<=0; wl_word<=0; wl_addr<=0; wl_tile<=0; wl_pair<=0; wl_error<=0;
  end else begin
   if (take_block && weight_cmd && legal_block && !st_hold_weight) begin
    wl_busy<=1; wl_wait<=0; wl_word<=0; wl_addr<=icb_cmd_wdata; wl_error<=0;
    wl_tile<=weight_tile_cmd; wl_pair<=icb_cmd_addr[6:2];
   end
   if (wl_rsp) begin
    wl_wait<=0;
    wl_word<=wl_word+10'd1;
    wl_addr<=wl_addr_next;
    // A failed background read must surface on the command's ICB response:
    // the weight command still owns the bus (pending) until wl_busy drops.
    if (mem_rsp_err) wl_error<=1;
    if (mem_rsp_err || wl_last) wl_busy<=0;
   end
   if (wl_req && mem_cmd_ready) wl_wait<=1;
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
   end else if (take_block && legal_block && meta_cmd) begin
    if (meta_shift_cmd) meta_shift_base<=icb_cmd_wdata;
    else if (meta_bias_cmd) meta_bias_base<=icb_cmd_wdata;
    else begin
     meta_bias_cur<=meta_bias_base+{21'b0,icb_cmd_wdata[7:0],3'b000};
     meta_shift_cur<=meta_shift_base+{24'b0,icb_cmd_wdata[7:0]};
     meta_lane<=0; meta_seg<=0; meta_state<=M_SHIFT_REQ; meta_busy<=1;
    end
   end else begin
    case (meta_state)
     M_SHIFT_REQ: if (meta_req && mem_cmd_ready) meta_state<=M_SHIFT_RSP;
     M_SHIFT_RSP: if (meta_rsp) begin meta_shift_w<=mem_rsp_rdata; meta_state<=M_LO_REQ; end
     M_LO_REQ: if (meta_req && mem_cmd_ready) meta_state<=M_LO_RSP;
     M_LO_RSP: if (meta_rsp) begin meta_lo_w<=mem_rsp_rdata; meta_state<=M_HI_REQ; end
     M_HI_REQ: if (meta_req && mem_cmd_ready) meta_state<=M_HI_RSP;
     M_HI_RSP: if (meta_rsp) begin meta_hi_w<=mem_rsp_rdata; meta_seg<=0; meta_state<=M_WR; end
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
   if (!rst_n) begin rsp_is_wl<=0; rsp_is_meta<=0; rsp_is_st<=0; end
   else if (mem_cmd_valid && mem_cmd_ready) begin rsp_is_wl<=wl_req; rsp_is_meta<=meta_req; rsp_is_st<=st_req; end
  // Staging engine: read staging word, write it to live in the cycle the
  // read returns (if the bus is free), then step to the next word. Pairs are
  // finished in order, so st_p is a monotonic completion pointer.
  always @(posedge clk) begin
   if (!rst_n) begin
    st_busy<=0; st_wait<=0; st_out_w<=0; st_have<=0; st_wbase<=0; st_data<=0; st_p<=0; st_k<=0; st_w<=0;
   end else begin
    if (take_block && st_cmd && legal_block && !st_busy) begin
     st_busy<=1; st_wait<=0; st_have<=0; st_wbase<={icb_cmd_wdata[31:9],9'b0}; st_p<=icb_cmd_wdata[8:6]; st_k<=0; st_w<=0;
    end
    if (st_rsp) begin
     st_wait<=0;
     if (!st_out_w) begin st_data<=mem_rsp_rdata; st_have<=1; end
     else begin
      st_w<=st_w+4'd1;
      if (st_w==4'd15) begin
       st_k<=st_k+6'd1;
       if (st_k==6'd63) begin
        st_p<=st_p+3'd1;
        if (st_p==3'd7) st_busy<=0;
       end
      end
     end
    end
    if (st_req && mem_cmd_ready) begin st_wait<=1; st_out_w<=st_nxt_w; if (st_nxt_w) st_have<=0; end
   end
  end
 reg owner_block;
 always @(posedge clk)
  if (!rst_n) owner_block<=0;
  else if (icb_cmd_valid && icb_cmd_ready) owner_block<=block_cmd;
`else
 wire acc_selected=select_accel;
 assign icb_cmd_ready = !pending && (select_accel ? acc_cmd_ready : 1'b1);
 assign icb_rsp_valid = pending && (owner_accel ? acc_rsp_valid : 1'b1);
`endif
 assign icb_rsp_rdata = owner_accel ? acc_rsp_data : local_data;
`ifdef QINGYU_BLOCK_COPY
 assign icb_rsp_err = owner_block ? (transfer_error || (wl_pending_rsp && wl_error)) : owner_accel ? acc_rsp_err : local_error;
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
  .input_write(rst_n && input_block && ((phase==READ_RSP && blk_rsp && !mem_rsp_err) || phase==INPUT_HI)),
  .input_elem({input_group,5'b0}+{word_number,1'b0}+(phase==INPUT_HI)),
  .input_data(phase==INPUT_HI ? loaded_word[31:16] : mem_rsp_rdata[15:0]),
  .block_next_valid(block_next_valid), .block_next_data(block_next_data), .block_remaining(block_remaining), .block_pop(block_pop), .block_valid(block_valid), .block_slot(block_slot),
  .block_has_row(block_has_row), .block_data(block_data),
  .weight_load_ok(weight_load_ok), .weight_write(weight_write), .weight_pair(wl_word[2:0]),
  .weight_k(wl_tile ? wl_word[8:3] : {wl_pair,wl_word[3]}), .weight_word(mem_rsp_rdata),
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
   host_valid<=0; host_code<=0; wl_pending_rsp<=0;
  end else begin
   host_valid<=0;
   if (icb_rsp_valid && icb_rsp_ready) begin pending<=0; wl_pending_rsp<=0; end
   if (icb_cmd_valid && icb_cmd_ready) begin
    pending<=1; owner_accel<=acc_selected;
    if (block_cmd && weight_cmd && legal_block) wl_pending_rsp<=1;
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
