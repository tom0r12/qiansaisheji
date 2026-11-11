"""opt8: automatic output write-back.
FIO command 0xc0 (wdata = output address of row 0 of a tile) queues one tile
(2-entry queue).  Whenever a batch is ready and the block engine is idle, the
FIO copies it to dst + batch*8 rows (same transfer as the 0x3c/0x40 batch
command) and releases the slot itself (block_release into the accelerator).
After 13 batches the next queued tile becomes current.  Command 0xc4 is held
until the queue is empty and answers with an error if any write-back failed.
The CPU therefore issues 2 commands per tile instead of ~4 MMIO per batch."""
import sys, pathlib

root = pathlib.Path(sys.argv[1])


def patch(name, pairs):
    p = root / name
    raw = p.read_bytes().decode()
    crlf = "\r\n" in raw
    s = raw.replace("\r\n", "\n")
    for old, new in pairs:
        n = s.count(old)
        if n != 1:
            raise SystemExit(f"{name}: anchor count {n}: {old[:90]!r}")
        s = s.replace(old, new)
    if crlf:
        s = s.replace("\n", "\r\n")
    p.write_bytes(s.encode())
    print("patched", name)


patch("qingyu_accel.sv", [
    ("""    input wire block_pop,
""", """    input wire block_pop,
    // opt8: FIO write-back engine releases the stream slot it just copied.
    input wire block_release,
"""),
    ("""    wire release_stream = command_fire && !icb_cmd_read && icb_cmd_wmask==4'hf &&
                          icb_cmd_wdata==1 && icb_cmd_addr== (stream_slot ? 16'h24 : 16'h20)
                          && batch_ready[stream_slot];""",
     """`ifdef QINGYU_BLOCK_COPY
    wire hw_release = block_release && batch_ready[stream_slot];
`else
    wire hw_release = 1'b0;
`endif
    wire release_stream = (command_fire && !icb_cmd_read && icb_cmd_wmask==4'hf &&
                          icb_cmd_wdata==1 && icb_cmd_addr== (stream_slot ? 16'h24 : 16'h20)
                          && batch_ready[stream_slot]) || hw_release;"""),
    ("""            if (!busy) sv<=0;""", """            if (!busy) sv<=0;
            if (hw_release) batch_ready[stream_slot]<=0;"""),
])

patch("qingyu_fio.sv", [
    (""" reg [31:0] cp_buf;
""", """ reg [31:0] cp_buf;
 // opt8 automatic write-back: destination queue (row 0 of a tile), batch index
 localparam [3:0] AW_BATCHES = 4'd13; // ceil(99/8)
 reg [31:0] aw_q0, aw_q1;
 reg [1:0] aw_cnt;
 reg [3:0] aw_bidx;
 reg aw_active, aw_error;
"""),
    (""" wire st_pre_cmd=icb_cmd_addr==32'hf00000b4;
""", """ wire st_pre_cmd=icb_cmd_addr==32'hf00000b4;
 wire aw_cmd=icb_cmd_addr==32'hf00000c0;
 wire aw_wait_cmd=icb_cmd_addr==32'hf00000c4;
"""),
    ("""                icb_cmd_addr==32'hf0000038 || weight_cmd || meta_cmd || st_cmd || st_pre_cmd;""",
     """                icb_cmd_addr==32'hf0000038 || weight_cmd || meta_cmd || st_cmd || st_pre_cmd ||
                aw_cmd || aw_wait_cmd;"""),
    ("""   (st_pre_cmd ? icb_cmd_wdata[5:0]!=0 && icb_cmd_wdata>=32'ha0000000 &&""",
     """   (aw_wait_cmd ? 1'b1 :
    aw_cmd ? icb_cmd_wdata[4:0]==0 && icb_cmd_wdata>=32'ha0000000 &&
             icb_cmd_wdata<=32'ha007ffe0-32'd50176 :
    st_pre_cmd ? icb_cmd_wdata[5:0]!=0 && icb_cmd_wdata>=32'ha0000000 &&"""),
    ("""                                                (!(st_cmd || st_pre_cmd) || !st_busy)) :""",
     """                                                (!(st_cmd || st_pre_cmd) || !st_busy) &&
                                                (!aw_cmd || aw_cnt!=2'd2) && (!aw_wait_cmd || aw_cnt==2'd0) &&
                                                // transfer commands start only from IDLE (the write-back
                                                // engine may own the block engine meanwhile)
                                                (weight_cmd || meta_cmd || st_cmd || st_pre_cmd || aw_cmd || aw_wait_cmd || phase==IDLE)) :"""),
    ("""     if (legal_block && !weight_cmd && !meta_cmd && !st_cmd && !st_pre_cmd) begin""",
     """     if (legal_block && !weight_cmd && !meta_cmd && !st_cmd && !st_pre_cmd && !aw_cmd && !aw_wait_cmd) begin"""),
    # start an automatic batch transfer from IDLE when nothing else is pending
    ("""    IDLE: if (take_block) begin""", """    IDLE: if (take_block && icb_cmd_ready) begin"""),
    ("""      cp_rd<=0; cp_buf_v<=0; cp_err<=0;
     end
    end
    READ_CMD:""", """      cp_rd<=0; cp_buf_v<=0; cp_err<=0;
     end
    end else if (aw_go) begin
     dst_addr<=aw_q0 + {16'b0, aw_bidx, 12'b0}; word_number<=0; load_block<=0;
     input_block<=0; batch_block<=1; transfer_words<={5'b0, block_remaining}; phase<=WRITE_CMD;
    end
    READ_CMD:"""),
    (""" wire block_pop=phase==WRITE_RSP && blk_rsp && !mem_rsp_err && !load_block;""",
     """ wire block_pop=phase==WRITE_RSP && blk_rsp && !mem_rsp_err && !load_block;
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
 end"""),
    (""".block_pop(block_pop),""", """.block_pop(block_pop), .block_release(aw_release),"""),
    (""" assign icb_rsp_err = owner_block ? (transfer_error || (wl_pending_rsp && wl_error)) : owner_accel ? (acc_rsp_err || start_wl_err) : local_error;""",
     """ assign icb_rsp_err = owner_block ? (transfer_error || (wl_pending_rsp && wl_error) || (owner_aw_wait && aw_error)) :
                      owner_accel ? (acc_rsp_err || start_wl_err) : local_error;"""),
    (""" reg owner_block;
 always @(posedge clk)
  if (!rst_n) owner_block<=0;
  else if (icb_cmd_valid && icb_cmd_ready) owner_block<=block_cmd;""",
     """ reg owner_block, owner_aw_wait;
 always @(posedge clk)
  if (!rst_n) begin owner_block<=0; owner_aw_wait<=0; end
  else if (icb_cmd_valid && icb_cmd_ready) begin owner_block<=block_cmd; owner_aw_wait<=aw_wait_cmd; end"""),
])
