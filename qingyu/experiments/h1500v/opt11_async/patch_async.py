"""opt11: asynchronous staging + dedicated input-load port.
FIO
 - 0xbc: async copy length (words); 0xc8: async copy base -> COPY engine runs
   (staging read on mem_*, live write on cw_*) and the command answers at once.
   Copy errors are sticky and reported on the next START response.
 - input commands (XPAIR build) run on a new input engine with its own shared-
   SRAM port in_*: answers at once, each live word is read only after it was
   copied (COPY engine or staging-engine pre-copy); START waits for it.
 - control commands (no block-engine phase) answer at once instead of waiting
   for the block engine to be idle; their legality is kept in ctl_err.
SoC: 6-port shared SRAM (priority cw > sw > mem > ld > in > sr).
Environment: meta pre-copy + W pairs 0..7 on the staging engine, input copy
asynchronous; driver issues the input load first."""
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


patch("rtl/qingyu_fio.sv", [
    (""" input wire sw_rsp_valid, sw_rsp_err,
""", """ input wire sw_rsp_valid, sw_rsp_err,
 // opt11 input-load engine port
 output wire in_cmd_valid, input wire in_cmd_ready, output wire [31:0] in_cmd_addr,
 input wire in_rsp_valid, in_rsp_err, input wire [31:0] in_rsp_rdata,
"""),
    (""" wire st_cnt_cmd=icb_cmd_addr==32'hf00000b8;
""", """ wire st_cnt_cmd=icb_cmd_addr==32'hf00000b8;
 wire cpa_cnt_cmd=icb_cmd_addr==32'hf00000bc;
 wire cpa_cmd=icb_cmd_addr==32'hf00000c8;
 reg [12:0] cpa_count;
 reg cp_async, cpa_err;
 // opt11 input engine
 reg il_busy, il_wait, il_err;
 reg [11:0] il_word, il_words;
 reg [7:0] il_group;
 reg [31:0] il_addr;
"""),
    ("""                icb_cmd_addr==32'hf0000038 || weight_cmd || meta_cmd || st_cmd || st_pre_cmd || st_cnt_cmd ||""",
     """                icb_cmd_addr==32'hf0000038 || weight_cmd || meta_cmd || st_cmd || st_pre_cmd || st_cnt_cmd ||
                cpa_cnt_cmd || cpa_cmd ||"""),
    ("""    st_cnt_cmd ? icb_cmd_wdata[31:12]==0 && icb_cmd_wdata[11:0]!=0 &&""",
     """    cpa_cnt_cmd ? icb_cmd_wdata[31:13]==0 && icb_cmd_wdata[12:0]!=0 :
    cpa_cmd ? icb_cmd_wdata[5:0]==0 && icb_cmd_wdata>=32'ha0000000 && cpa_count!=0 &&
              icb_cmd_wdata + {17'b0, cpa_count, 2'b00} <= 32'ha0040000 :
    st_cnt_cmd ? icb_cmd_wdata[31:12]==0 && icb_cmd_wdata[11:0]!=0 &&"""),
    (""" wire accel_cmd_ok=(!wl_busy || icb_cmd_read || batch_release_cmd) && (!meta_busy || !start_cmd);""",
     """ wire accel_cmd_ok=(!wl_busy || icb_cmd_read || batch_release_cmd) && (!meta_busy || !start_cmd) &&
                   (!il_busy || !start_cmd);
 // commands that never use the block-engine phase (answered at once)
 wire ctl_cmd = weight_cmd || meta_cmd || st_cmd || st_pre_cmd || st_cnt_cmd || aw_cmd || aw_wait_cmd ||
                cpa_cnt_cmd || (XPAIR && input_cmd);
 wire imm_cmd = ctl_cmd || cpa_cmd;"""),
    ("""                                                (weight_cmd || meta_cmd || st_cmd || st_pre_cmd || st_cnt_cmd || aw_cmd || aw_wait_cmd || phase==IDLE)) :""",
     """                                                (!(XPAIR && input_cmd) || !il_busy) &&
                                                (ctl_cmd || phase==IDLE)) :"""),
    (""" assign icb_rsp_valid=pending && (owner_accel ? acc_rsp_valid : (wl_pending_rsp ? !wl_busy : passthru));""",
     """ assign icb_rsp_valid=pending && (owner_accel ? acc_rsp_valid : (wl_pending_rsp ? !wl_busy : (owner_imm || passthru)));"""),
    ("""     if (legal_block && !weight_cmd && !meta_cmd && !st_cmd && !st_pre_cmd && !st_cnt_cmd && !aw_cmd && !aw_wait_cmd) begin
      dst_addr<=icb_cmd_wdata; word_number<=0; load_block<=loading;""",
     """     if (legal_block && !ctl_cmd) begin
      dst_addr<=icb_cmd_wdata; word_number<=0; load_block<=loading || cpa_cmd; cp_async<=cpa_cmd;"""),
    ("""      transfer_words<=input_full_cmd ? 3168 : stage256_cmd ? 256 : batch_cmd ? block_remaining : (loading || input_cmd) ? 16 : OROW_WORDS;
      phase<=loading ? COPY : input_cmd ? READ_CMD : WRITE_CMD;""",
     """      transfer_words<=cpa_cmd ? cpa_count : input_full_cmd ? 3168 : stage256_cmd ? 256 : batch_cmd ? block_remaining : (loading || input_cmd) ? 16 : OROW_WORDS;
      phase<=(loading || cpa_cmd) ? COPY : input_cmd ? READ_CMD : WRITE_CMD;"""),
    (""" wire weight_write=rst_n && wl_rsp_ok;""", """ wire weight_write=rst_n && wl_rsp_ok;
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
 end"""),
    ("""  .input_write(rst_n && input_block && ((phase==READ_RSP && blk_rsp && !mem_rsp_err) || phase==INPUT_HI)),
  .input_pair(XPAIR==1), .input_data_hi(mem_rsp_rdata[31:16]),
  .input_elem({input_group,5'b0}+{word_number,1'b0}+(phase==INPUT_HI)),
  .input_data(phase==INPUT_HI ? loaded_word[31:16] : mem_rsp_rdata[15:0]),""",
     """  .input_write(il_wr || (rst_n && input_block && ((phase==READ_RSP && blk_rsp && !mem_rsp_err) || phase==INPUT_HI))),
  .input_pair(XPAIR==1), .input_data_hi(il_wr ? in_rsp_rdata[31:16] : mem_rsp_rdata[31:16]),
  .input_elem(il_wr ? {il_group,5'b0}+{il_word,1'b0} : {input_group,5'b0}+{word_number,1'b0}+(phase==INPUT_HI)),
  .input_data(il_wr ? in_rsp_rdata[15:0] : phase==INPUT_HI ? loaded_word[31:16] : mem_rsp_rdata[15:0]),"""),
    (""" reg cp_async, cpa_err;
""", """ reg cp_async, cpa_err;
 reg owner_imm, ctl_err; // response owner: command answered at once
"""),
    ("""  if (!rst_n) begin owner_block<=0; owner_aw_wait<=0; end
  else if (icb_cmd_valid && icb_cmd_ready) begin owner_block<=block_cmd; owner_aw_wait<=aw_wait_cmd; end""",
     """  if (!rst_n) begin owner_block<=0; owner_aw_wait<=0; owner_imm<=0; ctl_err<=0; end
  else if (icb_cmd_valid && icb_cmd_ready) begin
   owner_block<=block_cmd; owner_aw_wait<=aw_wait_cmd;
   owner_imm<=block_cmd && imm_cmd; ctl_err<=!legal_block;
  end"""),
    (""" assign icb_rsp_err = owner_block ? (transfer_error || (wl_pending_rsp && wl_error) || (owner_aw_wait && aw_error)) :""",
     """ assign icb_rsp_err = owner_imm ? (ctl_err || (owner_aw_wait && aw_error)) :
                      owner_block ? (transfer_error || (wl_pending_rsp && wl_error) || (owner_aw_wait && aw_error)) :"""),
    ("""    start_wl_err<=WL_ASYNC && acc_selected && start_cmd && !icb_cmd_read && wl_error;""",
     """    start_wl_err<=WL_ASYNC && acc_selected && start_cmd && !icb_cmd_read && (wl_error || il_err || cpa_err);"""),
])

# phase-start: block the COPY's IDLE launch of an async copy only through ready (phase==IDLE)

patch("rtl/qingyu_e203_soc_top.v", [
    ("""wire sw_cmd_valid, sw_cmd_ready, sw_rsp_valid, sw_rsp_err;
wire [31:0] sw_cmd_addr, sw_cmd_wdata;
wire [159:0] mp_rsp_rdata;
wire [4:0] mp_rsp_valid, mp_rsp_err, mp_cmd_ready;
// Port order = bank priority: 0 cw, 1 sw, 2 mem(CPU/block), 3 ld, 4 sr.
qingyu_shared_sram_mp #(.NP(5)) u_shared(
 .clk(qingyu_bus_clk), .rst_n(qingyu_bus_rst_n),
 .cmd_valid({sr_cmd_valid, ld_cmd_valid, block_mem_cmd_valid, sw_cmd_valid, cw_cmd_valid}),
 .cmd_ready(mp_cmd_ready),
 .cmd_read({1'b1, 1'b1, block_mem_cmd_read, 1'b0, 1'b0}),
 .cmd_addr({sr_cmd_addr, ld_cmd_addr, block_mem_cmd_addr, sw_cmd_addr, cw_cmd_addr}),
 .cmd_wdata({32'b0, 32'b0, block_mem_cmd_wdata, sw_cmd_wdata, cw_cmd_wdata}),
 .cmd_wmask({4'h0, 4'h0, block_mem_cmd_wmask, 4'hf, 4'hf}),
 .rsp_valid(mp_rsp_valid),
 .rsp_ready({1'b1, 1'b1, block_mem_rsp_ready, 1'b1, 1'b1}),
 .rsp_rdata(mp_rsp_rdata),
 .rsp_err(mp_rsp_err)
);
assign {sr_cmd_ready, ld_cmd_ready, block_mem_cmd_ready, sw_cmd_ready, cw_cmd_ready} = mp_cmd_ready;
assign {sr_rsp_valid, ld_rsp_valid, block_mem_rsp_valid, sw_rsp_valid, cw_rsp_valid} = mp_rsp_valid;
assign {sr_rsp_err, ld_rsp_err, block_mem_rsp_err, sw_rsp_err, cw_rsp_err} = mp_rsp_err;
assign sr_rsp_rdata = mp_rsp_rdata[159:128];
assign ld_rsp_rdata = mp_rsp_rdata[127:96];""",
     """wire sw_cmd_valid, sw_cmd_ready, sw_rsp_valid, sw_rsp_err;
wire [31:0] sw_cmd_addr, sw_cmd_wdata;
wire in_cmd_valid, in_cmd_ready, in_rsp_valid, in_rsp_err;
wire [31:0] in_cmd_addr, in_rsp_rdata;
wire [191:0] mp_rsp_rdata;
wire [5:0] mp_rsp_valid, mp_rsp_err, mp_cmd_ready;
// Port order = bank priority: 0 cw, 1 sw, 2 mem(CPU/block), 3 ld, 4 in, 5 sr.
qingyu_shared_sram_mp #(.NP(6)) u_shared(
 .clk(qingyu_bus_clk), .rst_n(qingyu_bus_rst_n),
 .cmd_valid({sr_cmd_valid, in_cmd_valid, ld_cmd_valid, block_mem_cmd_valid, sw_cmd_valid, cw_cmd_valid}),
 .cmd_ready(mp_cmd_ready),
 .cmd_read({1'b1, 1'b1, 1'b1, block_mem_cmd_read, 1'b0, 1'b0}),
 .cmd_addr({sr_cmd_addr, in_cmd_addr, ld_cmd_addr, block_mem_cmd_addr, sw_cmd_addr, cw_cmd_addr}),
 .cmd_wdata({32'b0, 32'b0, 32'b0, block_mem_cmd_wdata, sw_cmd_wdata, cw_cmd_wdata}),
 .cmd_wmask({4'h0, 4'h0, 4'h0, block_mem_cmd_wmask, 4'hf, 4'hf}),
 .rsp_valid(mp_rsp_valid),
 .rsp_ready({1'b1, 1'b1, 1'b1, block_mem_rsp_ready, 1'b1, 1'b1}),
 .rsp_rdata(mp_rsp_rdata),
 .rsp_err(mp_rsp_err)
);
assign {sr_cmd_ready, in_cmd_ready, ld_cmd_ready, block_mem_cmd_ready, sw_cmd_ready, cw_cmd_ready} = mp_cmd_ready;
assign {sr_rsp_valid, in_rsp_valid, ld_rsp_valid, block_mem_rsp_valid, sw_rsp_valid, cw_rsp_valid} = mp_rsp_valid;
assign {sr_rsp_err, in_rsp_err, ld_rsp_err, block_mem_rsp_err, sw_rsp_err, cw_rsp_err} = mp_rsp_err;
assign sr_rsp_rdata = mp_rsp_rdata[191:160];
assign in_rsp_rdata = mp_rsp_rdata[159:128];
assign ld_rsp_rdata = mp_rsp_rdata[127:96];"""),
    (""" .sw_rsp_valid(sw_rsp_valid), .sw_rsp_err(sw_rsp_err),
""", """ .sw_rsp_valid(sw_rsp_valid), .sw_rsp_err(sw_rsp_err),
 .in_cmd_valid(in_cmd_valid), .in_cmd_ready(in_cmd_ready), .in_cmd_addr(in_cmd_addr),
 .in_rsp_valid(in_rsp_valid), .in_rsp_err(in_rsp_err), .in_rsp_rdata(in_rsp_rdata),
"""),
])

patch("tb/tb_qingyu_soc_performance.sv", [
    (" localparam integer NP=5;", " localparam integer NP=6;"),
    ("""     $display("QINGYU_PROFILE first_start=%0d last_busy=%0d tail=%0d idle_all_ports=%0d st_end=%0d port_cw=%0d port_sw=%0d port_mem=%0d port_ld=%0d port_sr=%0d",
      first_busy-start_tick,last_busy-start_tick,end_tick-last_busy,idle_cycles,
      st_end<0 ? -1 : st_end-start_tick,port_acc[0],port_acc[1],port_acc[2],port_acc[3],port_acc[4]);""",
     """     $display("QINGYU_PROFILE first_start=%0d last_busy=%0d tail=%0d idle_all_ports=%0d st_end=%0d port_cw=%0d port_sw=%0d port_mem=%0d port_ld=%0d port_in=%0d port_sr=%0d",
      first_busy-start_tick,last_busy-start_tick,end_tick-last_busy,idle_cycles,
      st_end<0 ? -1 : st_end-start_tick,port_acc[0],port_acc[1],port_acc[2],port_acc[3],port_acc[4],port_acc[5]);"""),
    ("""       `FIO.icb_cmd_addr==32'hf00000b0 || `FIO.icb_cmd_addr==32'hf00000b4)) begin""",
     """       `FIO.icb_cmd_addr==32'hf00000b0 || `FIO.icb_cmd_addr==32'hf00000b4 ||
       `FIO.icb_cmd_addr==32'hf00000bc || `FIO.icb_cmd_addr==32'hf00000c8)) begin"""),
])

patch("macro/tb_qingyu_soc_macros.sv", [
    ("""   force `SHARED.cmd_valid={4'b0,shared_cs};
   force `SHARED.cmd_read={4'b0,!shared_we};
   force `SHARED.cmd_addr={128'b0,13'h1400,shared_address,2'b00};
   force `SHARED.cmd_wdata={128'b0,shared_din};
   force `SHARED.cmd_wmask={16'b0,4'hf};
   force `SHARED.rsp_ready=5'b11111;""",
     """   force `SHARED.cmd_valid={5'b0,shared_cs};
   force `SHARED.cmd_read={5'b0,!shared_we};
   force `SHARED.cmd_addr={160'b0,13'h1400,shared_address,2'b00};
   force `SHARED.cmd_wdata={160'b0,shared_din};
   force `SHARED.cmd_wmask={20'b0,4'hf};
   force `SHARED.rsp_ready=6'b111111;"""),
    ("// Port 0 of the shared memory carries the loader; ports 1..4 are idle.",
     "// Port 0 of the shared memory carries the loader; ports 1..5 are idle."),
])

patch("rtl/qingyu_accel.h", [
    ("""#ifndef QINGYU_BG_INPUT
""", """#ifndef QINGYU_ASYNC_STAGE
/* Environment (opt11): bias/shift pre-copy + W pairs 0..7 on the staging
 * engine, the input copy is an asynchronous FIO copy (0xbc/0xc8). */
#define QINGYU_ASYNC_STAGE 1
#endif
#ifndef QINGYU_INPUT_FIRST
/* Driver: the (asynchronous) input load is issued before tile 0's prefetch. */
#ifdef QINGYU_OUT16
#define QINGYU_INPUT_FIRST 1
#else
#define QINGYU_INPUT_FIRST 0
#endif
#endif
#ifndef QINGYU_BG_INPUT
"""),
])

patch("rtl/soc_perf_main.c", [
    ("""#if QINGYU_BG_STAGE && QINGYU_BG_INPUT
""", """#if QINGYU_BG_STAGE && QINGYU_ASYNC_STAGE
        /* opt11: nothing here waits.  Staging engine: bias+shift (36 x 64 B)
         * then W pairs 0..7; FIO copy engine: the 3,168 input words. */
        *(volatile uint32_t *)(uintptr_t)0xf00000b4u = 0xa000c000u | 36u;
        *(volatile uint32_t *)(uintptr_t)0xf00000b0u = 0xa0004000u;
        *(volatile uint32_t *)(uintptr_t)0xf00000bcu = 99u * 64u / 2u;
        *(volatile uint32_t *)(uintptr_t)0xf00000c8u = 0xa0000000u;
#elif QINGYU_BG_STAGE && QINGYU_BG_INPUT
"""),
])

patch("rtl/qingyu_accel.c", [
    ("""#if QINGYU_EARLY_TILE0
    if (deferred_input != 0u && weight_stream && meta_block) {""",
     """#if QINGYU_INPUT_FIRST
    /* opt11: the input load runs in its own FIO engine (it trails the input
     * copy word by word); start it before tile 0's weight/metadata commands. */
    if (deferred_input != 0u) write_register(device,0x90u,deferred_input);
#endif
#if QINGYU_EARLY_TILE0
    if (deferred_input != 0u && weight_stream && meta_block) {"""),
    ("""    if (deferred_input != 0u) write_register(device,0x90u,deferred_input);
#if QINGYU_CHAIN_ACTIVE""", """#if !QINGYU_INPUT_FIRST
    if (deferred_input != 0u) write_register(device,0x90u,deferred_input);
#endif
#if QINGYU_CHAIN_ACTIVE"""),
])
