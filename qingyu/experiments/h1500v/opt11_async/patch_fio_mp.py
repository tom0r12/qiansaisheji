"""opt5: split the FIO shared-memory access into separate ports.
 mem_*  (existing): CPU passthrough + block engine reads / output writes
 cw_*   : block staging copy writes  (copy runs 1 word/cycle: read on mem, write on cw)
 ld_*   : weight prefetch + metadata gather reads
 sr_*/sw_*: background W staging engine read / write (pipelined, 1 word/cycle)
"""
import sys, pathlib

p = pathlib.Path(sys.argv[1])
raw = p.read_bytes().decode()
crlf = "\r\n" in raw
s = raw.replace("\r\n", "\n")


def rep(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        raise SystemExit(f"anchor count {n} != {count}: {old[:90]!r}")
    s = s.replace(old, new)


rep(""" input wire [31:0] mem_rsp_rdata,
`endif""", """ input wire [31:0] mem_rsp_rdata,
 // opt5 multi-port shared SRAM: extra masters (see header comment of patch)
 output wire cw_cmd_valid, input wire cw_cmd_ready, output wire [31:0] cw_cmd_addr, cw_cmd_wdata,
 input wire cw_rsp_valid, cw_rsp_err,
 output wire ld_cmd_valid, input wire ld_cmd_ready, output wire [31:0] ld_cmd_addr,
 input wire ld_rsp_valid, ld_rsp_err, input wire [31:0] ld_rsp_rdata,
 output wire sr_cmd_valid, input wire sr_cmd_ready, output wire [31:0] sr_cmd_addr,
 input wire sr_rsp_valid, sr_rsp_err, input wire [31:0] sr_rsp_rdata,
 output wire sw_cmd_valid, input wire sw_cmd_ready, output wire [31:0] sw_cmd_addr, sw_cmd_wdata,
 input wire sw_rsp_valid, sw_rsp_err,
`endif""")

rep("localparam IDLE=0, READ_CMD=1, READ_RSP=2, WRITE_CMD=3, WRITE_RSP=4, INPUT_HI=5;",
    "localparam IDLE=0, READ_CMD=1, READ_RSP=2, WRITE_CMD=3, WRITE_RSP=4, INPUT_HI=5, COPY=6, CP_DRAIN=7;")

# staging-engine state: separate read and write pointers
rep(""" reg st_busy, st_wait, st_out_w, st_have, rsp_is_st;
 reg [31:0] st_wbase, st_data;
 reg [2:0] st_p;
 reg [5:0] st_k;
 reg [3:0] st_w;
 wire st_req, st_rsp, st_nxt_w;
 wire [31:0] st_cur, st_cmd_addr, st_cmd_wdata;
""", """ // opt5: reads on sr_*, writes on sw_*; st_{p,k,w} is the write (completion)
 // pointer used by the weight-command hold, st_r{p,k,w} the read pointer.
 reg st_busy, st_rd_done, st_buf_v;
 reg [31:0] st_wbase, st_buf;
 reg [2:0] st_p, st_rp;
 reg [5:0] st_k, st_rk;
 reg [3:0] st_w, st_rw;
 wire st_rsp;
 // opt5 block staging copy: read pointer, one-word buffer, write outstanding
 reg [12:0] cp_rd;
 reg cp_buf_v, cp_err, cw_out;
 reg [31:0] cp_buf;
""")

# copy-engine wires, inserted before blk_req
rep(""" assign blk_req = passthru ? cpu_cmd_valid && !request_block :
                  phase==READ_CMD || (phase==WRITE_CMD && (load_block || block_valid)) ||
                  stage_write_now || stage_read_next || input_read_next || output_write_next;
 assign blk_addr = passthru ? cpu_cmd_addr :
""", """ // opt5 staging copy (0x38/0x84): read staging on mem_*, write live on cw_*.
 // cw_* has the highest bank priority, so its ready never depends on mem_*.
 wire cp_rsp = phase==COPY && mem_rsp_valid;
 wire cp_rsp_ok = cp_rsp && !mem_rsp_err;
 wire cp_have = cp_buf_v || cp_rsp_ok;
 assign cw_cmd_valid = rst_n && phase==COPY && cp_have;
 assign cw_cmd_addr = dst_addr + {18'b0, word_number, 2'b00};
 assign cw_cmd_wdata = cp_buf_v ? cp_buf : mem_rsp_rdata;
 wire cw_fire = cw_cmd_valid && cw_cmd_ready;
 wire cp_read = phase==COPY && !cp_err && !(cp_rsp && mem_rsp_err) &&
                cp_rd != transfer_words && (!cp_have || cw_fire);
 assign blk_req = passthru ? cpu_cmd_valid && !request_block :
                  phase==READ_CMD || (phase==WRITE_CMD && (load_block || block_valid)) ||
                  stage_write_now || stage_read_next || input_read_next || output_write_next || cp_read;
 assign blk_addr = passthru ? cpu_cmd_addr : cp_read ? dst_addr + 32'h40000 + {17'b0, cp_rd, 2'b00} :
""")
rep(" assign blk_read = passthru ? cpu_cmd_read : phase==READ_CMD || stage_read_next || input_read_next;",
    " assign blk_read = passthru ? cpu_cmd_read : phase==READ_CMD || stage_read_next || input_read_next || cp_read;")

rep(" assign blk_rsp = mem_rsp_valid && !rsp_is_wl && !rsp_is_meta && !rsp_is_st;\n assign st_rsp = mem_rsp_valid && rsp_is_st;\n assign wl_rsp = mem_rsp_valid && rsp_is_wl;\n assign meta_rsp = mem_rsp_valid && rsp_is_meta;\n assign wl_rsp_ok = wl_rsp && !mem_rsp_err;",
    " assign blk_rsp = mem_rsp_valid;\n assign st_rsp = sr_rsp_valid;\n assign wl_rsp = ld_rsp_valid && rsp_is_wl;\n assign meta_rsp = ld_rsp_valid && rsp_is_meta;\n assign wl_rsp_ok = wl_rsp && !ld_rsp_err;")

rep(" assign wl_req = wl_busy && (!wl_wait || (wl_rsp && !wl_last)) && !blk_req && rst_n;",
    " assign wl_req = wl_busy && (!wl_wait || (wl_rsp && !wl_last)) && rst_n;")
rep("(meta_state==M_SHIFT_REQ || meta_state==M_LO_REQ || meta_state==M_HI_REQ) && !blk_req && !wl_req;",
    "(meta_state==M_SHIFT_REQ || meta_state==M_LO_REQ || meta_state==M_HI_REQ) && !wl_req;")

# old single-port staging-engine wires -> pipelined two-port engine
start = s.index(" // Staging engine: next op is the write of the word just read, else a read.")
end = s.index(" assign mem_rsp_ready =")
end = s.index("\n", end) + 1
s = s[:start] + """ // Staging engine (opt5): pipelined copy, one read (sr_*) and one write (sw_*)
 // per cycle.  A read is issued only when the word it returns can be written
 // or buffered, so one buffer word suffices.
 wire st_have = st_buf_v || st_rsp;
 assign sw_cmd_valid = rst_n && st_busy && st_have;
 assign sw_cmd_addr = st_wbase + {17'b0, st_k, st_p, st_w, 2'b00};
 assign sw_cmd_wdata = st_buf_v ? st_buf : sr_rsp_rdata;
 wire sw_fire = sw_cmd_valid && sw_cmd_ready;
 assign sr_cmd_valid = rst_n && st_busy && !st_rd_done && (!st_have || sw_fire);
 assign sr_cmd_addr = st_wbase + {17'b0, st_rk, st_rp, st_rw, 2'b00} + 32'h40000;
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
""" + s[end:]

# block FSM: reset, take, COPY states, cw error
rep("""   phase<=IDLE; transfer_error<=0; cpu_outstanding<=0; load_block<=0;
""", """   phase<=IDLE; transfer_error<=0; cpu_outstanding<=0; load_block<=0;
   cp_rd<=0; cp_buf_v<=0; cp_err<=0; cw_out<=0; cp_buf<=0;
""")
rep("""      phase<=loading || input_cmd ? READ_CMD : WRITE_CMD;
""", """      phase<=loading ? COPY : input_cmd ? READ_CMD : WRITE_CMD;
      cp_rd<=0; cp_buf_v<=0; cp_err<=0;
""")
rep("""    default: phase<=IDLE;
   endcase
""", """    COPY: begin
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
""")

# weight prefetch / metadata gather on ld_*
rep("""    if (mem_rsp_err) wl_error<=1;
    if (mem_rsp_err || wl_last) wl_busy<=0;
   end
   if (wl_req && mem_cmd_ready) wl_wait<=1;""", """    if (ld_rsp_err) wl_error<=1;
    if (ld_rsp_err || wl_last) wl_busy<=0;
   end
   if (wl_req && ld_cmd_ready) wl_wait<=1;""")
rep("meta_req && mem_cmd_ready", "meta_req && ld_cmd_ready", 3)
rep("meta_shift_w<=mem_rsp_rdata", "meta_shift_w<=ld_rsp_rdata")
rep("meta_lo_w<=mem_rsp_rdata", "meta_lo_w<=ld_rsp_rdata")
rep("meta_hi_w<=mem_rsp_rdata", "meta_hi_w<=ld_rsp_rdata")
rep("""   if (!rst_n) begin rsp_is_wl<=0; rsp_is_meta<=0; rsp_is_st<=0; end
   else if (mem_cmd_valid && mem_cmd_ready) begin rsp_is_wl<=wl_req; rsp_is_meta<=meta_req; rsp_is_st<=st_req; end""",
    """   if (!rst_n) begin rsp_is_wl<=0; rsp_is_meta<=0; end
   else if (ld_cmd_valid && ld_cmd_ready) begin rsp_is_wl<=wl_req; rsp_is_meta<=meta_req; end""")

# staging engine sequential block
start = s.index("  // Staging engine: read staging word, write it to live in the cycle the")
end = s.index(" reg owner_block;")
s = s[:start] + """  // Staging engine (opt5): pair-major copy of W pairs start..7 from the staging
  // image (live + 0x40000) into the live W buffer.  st_p advances when the
  // last word of a pair has been written, so it is a completion pointer.
  always @(posedge clk) begin
   if (!rst_n) begin
    st_busy<=0; st_rd_done<=0; st_buf_v<=0; st_wbase<=0; st_buf<=0;
    st_p<=0; st_k<=0; st_w<=0; st_rp<=0; st_rk<=0; st_rw<=0;
   end else if (take_block && st_cmd && legal_block && !st_busy) begin
    st_busy<=1; st_rd_done<=0; st_buf_v<=0; st_wbase<={icb_cmd_wdata[31:9],9'b0};
    st_p<=icb_cmd_wdata[8:6]; st_k<=0; st_w<=0;
    st_rp<=icb_cmd_wdata[8:6]; st_rk<=0; st_rw<=0;
   end else begin
    if (sr_fire) begin
     st_rw<=st_rw+4'd1;
     if (st_rw==4'd15) begin st_rk<=st_rk+6'd1; if (st_rk==6'd63) st_rp<=st_rp+3'd1; end
     if (st_rp==3'd7 && st_rk==6'd63 && st_rw==4'd15) st_rd_done<=1;
    end
    if (st_rsp && !sw_fire) begin st_buf<=sr_rsp_rdata; st_buf_v<=1; end
    else if (st_buf_v && sw_fire) st_buf_v<=0;
    if (sw_fire) begin
     st_w<=st_w+4'd1;
     if (st_w==4'd15) begin
      st_k<=st_k+6'd1;
      if (st_k==6'd63) begin st_p<=st_p+3'd1; if (st_p==3'd7) st_busy<=0; end
     end
    end
   end
  end
""" + s[end:]

rep(".weight_word(mem_rsp_rdata)", ".weight_word(ld_rsp_rdata)")

for bad in ("st_req", "st_nxt_w", "st_cmd_addr", "st_cmd_wdata", "rsp_is_st", "st_wait", "st_out_w", "st_data"):
    if bad in s:
        raise SystemExit("leftover reference: " + bad)
if crlf:
    s = s.replace("\n", "\r\n")
p.write_bytes(s.encode())
print("fio patched")
