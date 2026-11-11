"""opt10: word-interleaved banks + background input staging overlapped with the
input load.
 - shared SRAM bank = word address mod 32 (addr[6:2]); row in bank = addr[18:7]
 - FIO 0xb8: pre-copy length in words (overrides the 0xb4 unit count)
 - input load (0x90) reads a live word only after the staging engine wrote it
 - metadata gather waits for the pre-copy only if the regions overlap
 - environment: staging engine copies the input (pre-copy) and W pairs 1..7;
   the CPU copies bias/shift and W pair 0 meanwhile."""
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


patch("qingyu_shared_sram_mp.sv", [
    ("""// Functional model of the project's 512 KiB shared SRAM with NP ICB ports.
// The physical memory is 32 independent 16 KiB banks (2 x RAMSP4096X16 each,
// see rtl/asic/qingyu_shared_sram_mp.sv).""",
     """// Functional model of the project's 512 KiB shared SRAM with NP ICB ports.
// The physical memory is 32 independent 16 KiB banks (2 x RAMSP4096X16 each,
// see rtl/asic/qingyu_shared_sram_mp.sv), word-interleaved: bank = word
// address mod 32, so sequential streams spread over all banks."""),
    ("""   assign bank[p] = a[18:14];""", """   assign bank[p] = a[6:2];"""),
])
patch("asic/qingyu_shared_sram_mp.sv", [
    ("""// Macro implementation of qingyu_shared_sram_mp: 512 KiB = 32 banks x 16 KiB,""",
     """// Macro implementation of qingyu_shared_sram_mp: 512 KiB = 32 word-interleaved
// banks (bank = addr[6:2], row = addr[18:7]) x 16 KiB,"""),
    ("""   assign bank[p] = a[18:14];""", """   assign bank[p] = a[6:2];"""),
    ("""      sel=1'b1; we=!cmd_read[j]; addr=cmd_addr[32*j+2+:12];""",
     """      sel=1'b1; we=!cmd_read[j]; addr=cmd_addr[32*j+7+:12];"""),
])

patch("qingyu_fio.sv", [
    (""" reg [9:0] pre_words, pre_rc, pre_wc;""", """ reg [11:0] pre_words, pre_rc, pre_wc;"""),
    (""" wire st_pre_cmd=icb_cmd_addr==32'hf00000b4;
""", """ wire st_pre_cmd=icb_cmd_addr==32'hf00000b4;
 wire st_cnt_cmd=icb_cmd_addr==32'hf00000b8;
 // opt10: pre-copy region bookkeeping for the read holds
 wire [31:0] pre_wr_addr = pre_base + {18'b0, pre_wc, 2'b00};
 wire [31:0] pre_end_addr = pre_base + {18'b0, pre_words, 2'b00};
 wire meta_pre_overlap = wr_pre &&
   ((pre_base < meta_bias_base + 32'h800 && meta_bias_base < pre_end_addr) ||
    (pre_base < meta_shift_base + 32'h100 && meta_shift_base < pre_end_addr));
"""),
    ("""                icb_cmd_addr==32'hf0000038 || weight_cmd || meta_cmd || st_cmd || st_pre_cmd ||""",
     """                icb_cmd_addr==32'hf0000038 || weight_cmd || meta_cmd || st_cmd || st_pre_cmd || st_cnt_cmd ||"""),
    ("""    st_pre_cmd ? icb_cmd_wdata[5:0]!=0 && icb_cmd_wdata>=32'ha0000000 &&""",
     """    st_cnt_cmd ? icb_cmd_wdata[31:12]==0 && icb_cmd_wdata[11:0]!=0 &&
                 pre_base + {18'b0, icb_cmd_wdata[11:0], 2'b00} <= 32'ha0040000 :
    st_pre_cmd ? icb_cmd_wdata[5:0]!=0 && icb_cmd_wdata>=32'ha0000000 &&"""),
    ("""                                                (!meta_cmd || (!meta_busy && !(meta_blk_cmd && wr_pre))) &&
                                                (!(st_cmd || st_pre_cmd) || !st_busy) &&""",
     """                                                (!meta_cmd || (!meta_busy && !(meta_blk_cmd && meta_pre_overlap))) &&
                                                (!(st_cmd || st_pre_cmd || st_cnt_cmd) || !st_busy) &&"""),
    ("""                                                (weight_cmd || meta_cmd || st_cmd || st_pre_cmd || aw_cmd || aw_wait_cmd || phase==IDLE)) :""",
     """                                                (weight_cmd || meta_cmd || st_cmd || st_pre_cmd || st_cnt_cmd || aw_cmd || aw_wait_cmd || phase==IDLE)) :"""),
    (""" wire input_read_next = XPAIR ? (phase==READ_RSP && input_block && blk_rsp && !mem_rsp_err && word_number!=transfer_words-1)""",
     """ // opt10: an input word is read only after the staging engine has written it
 wire hold_cur = input_block && wr_pre && dst_addr >= pre_wr_addr && dst_addr < pre_end_addr;
 wire hold_nxt = input_block && wr_pre && (dst_addr+32'd4) >= pre_wr_addr && (dst_addr+32'd4) < pre_end_addr;
 wire input_read_next = XPAIR ? (phase==READ_RSP && input_block && blk_rsp && !mem_rsp_err && word_number!=transfer_words-1 && !hold_nxt)"""),
    ("""                  phase==READ_CMD || (phase==WRITE_CMD && (load_block || block_valid)) ||""",
     """                  (phase==READ_CMD && !hold_cur) || (phase==WRITE_CMD && (load_block || block_valid)) ||"""),
    ("""      phase<=(mem_rsp_err || word_number==transfer_words-1) ? IDLE : (mem_cmd_ready ? READ_RSP : READ_CMD);""",
     """      phase<=(mem_rsp_err || word_number==transfer_words-1) ? IDLE : (input_read_next && mem_cmd_ready ? READ_RSP : READ_CMD);"""),
    ("""     if (legal_block && !weight_cmd && !meta_cmd && !st_cmd && !st_pre_cmd && !aw_cmd && !aw_wait_cmd) begin""",
     """     if (legal_block && !weight_cmd && !meta_cmd && !st_cmd && !st_pre_cmd && !st_cnt_cmd && !aw_cmd && !aw_wait_cmd) begin"""),
    ("""   end else if (take_block && legal_block && meta_cmd && !meta_busy && !(meta_blk_cmd && wr_pre)) begin""",
     """   end else if (take_block && legal_block && meta_cmd && !meta_busy && !(meta_blk_cmd && meta_pre_overlap)) begin"""),
    (""" assign sw_cmd_addr = wr_pre ? pre_base + {20'b0, pre_wc, 2'b00} : st_wbase + {17'b0, st_k, st_p, st_w, 2'b00};""",
     """ assign sw_cmd_addr = wr_pre ? pre_wr_addr : st_wbase + {17'b0, st_k, st_p, st_w, 2'b00};"""),
    (""" assign sr_cmd_addr = (rd_pre ? pre_base + {20'b0, pre_rc, 2'b00} : st_wbase + {17'b0, st_rk, st_rp, st_rw, 2'b00}) + 32'h40000;""",
     """ assign sr_cmd_addr = (rd_pre ? pre_base + {18'b0, pre_rc, 2'b00} : st_wbase + {17'b0, st_rk, st_rp, st_rw, 2'b00}) + 32'h40000;"""),
    ("""    pre_base<={icb_cmd_wdata[31:6],6'b0}; pre_words<={icb_cmd_wdata[5:0],4'b0};""",
     """    pre_base<={icb_cmd_wdata[31:6],6'b0}; pre_words<={2'b0,icb_cmd_wdata[5:0],4'b0};
   end else if (take_block && st_cnt_cmd && legal_block && !st_busy) begin
    pre_words<=icb_cmd_wdata[11:0];"""),
    ("""     pre_rc<=pre_rc+10'd1;
     if (pre_rc==pre_words-10'd1) rd_pre<=0;""", """     pre_rc<=pre_rc+12'd1;
     if (pre_rc==pre_words-12'd1) rd_pre<=0;"""),
    ("""     pre_wc<=pre_wc+10'd1;
     if (pre_wc==pre_words-10'd1) begin wr_pre<=0; pre_words<=0; end""",
     """     pre_wc<=pre_wc+12'd1;
     if (pre_wc==pre_words-12'd1) begin wr_pre<=0; pre_words<=0; end"""),
])

patch("qingyu_accel.h", [
    ("""#ifndef QINGYU_BG_META
""", """#ifndef QINGYU_BG_INPUT
/* Environment (opt10): staging engine copies the input and W pairs 1..7; the
 * CPU copies bias/shift and W pair 0; the input load trails the input copy. */
#define QINGYU_BG_INPUT 1
#endif
#ifndef QINGYU_BG_META
"""),
])

patch("soc_perf_main.c", [
    ("""#if QINGYU_BG_STAGE
#if QINGYU_BG_META
        /* opt6: bias (512 words) + shift (64 words) = 36 x 64-byte units,""",
     """#if QINGYU_BG_STAGE && QINGYU_BG_INPUT
        /* opt10: staging engine: input (3,168 words, pre-copy) then W pairs
         * 1..7; the CPU meanwhile copies bias/shift and W pair 0 (tiles 0,1). */
        *(volatile uint32_t *)(uintptr_t)0xf00000b4u = 0xa0000000u | 1u;
        *(volatile uint32_t *)(uintptr_t)0xf00000b8u = 99u * 64u / 2u;
        *(volatile uint32_t *)(uintptr_t)0xf00000b0u = 0xa0004000u | (1u << 6);
        load_words(0xc000u, 256u * 2u);
        load_words(0xc800u, 256u / 4u);
        for (uint32_t k = 0u; k < 64u; ++k)
            *(volatile uint32_t *)(uintptr_t)0xf0000038u = 0xa0004000u + k * 512u;
#else
#if QINGYU_BG_STAGE
#if QINGYU_BG_META
        /* opt6: bias (512 words) + shift (64 words) = 36 x 64-byte units,"""),
    ("""#if !(QINGYU_BG_STAGE && QINGYU_BG_META)
        load_words(0xc000u, 256u * 2u);
        load_words(0xc800u, 256u / 4u);
#endif""", """#if !(QINGYU_BG_STAGE && QINGYU_BG_META)
        load_words(0xc000u, 256u * 2u);
        load_words(0xc800u, 256u / 4u);
#endif
#endif /* QINGYU_BG_INPUT */"""),
])
