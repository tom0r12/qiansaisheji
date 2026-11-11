"""opt6 FIO: staging engine pre-copy region (command 0xb4 = base | 64-byte units),
copied before the W pairs; the metadata gather (0xa0) waits for it.
Also gate engine starts on their own busy flags (a held command is presented
for several cycles while take_block is high)."""
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


rep(""" reg [3:0] st_w, st_rw;
 wire st_rsp;
""", """ reg [3:0] st_w, st_rw;
 wire st_rsp;
 // opt6 pre-copy (bias/shift) ahead of the W pairs
 reg [31:0] pre_base;
 reg [9:0] pre_words, pre_rc, pre_wc;
 reg rd_pre, wr_pre;
""")
rep(""" wire st_cmd=icb_cmd_addr==32'hf00000b0;
""", """ wire st_cmd=icb_cmd_addr==32'hf00000b0;
 wire st_pre_cmd=icb_cmd_addr==32'hf00000b4;
""")
rep("""                icb_cmd_addr==32'hf0000038 || weight_cmd || meta_cmd || st_cmd;""",
    """                icb_cmd_addr==32'hf0000038 || weight_cmd || meta_cmd || st_cmd || st_pre_cmd;""")
rep("""   (st_cmd ? icb_cmd_wdata[5:0]==0 && icb_cmd_wdata>=32'ha0000000 &&""",
    """   (st_pre_cmd ? icb_cmd_wdata[5:0]!=0 && icb_cmd_wdata>=32'ha0000000 &&
                 ({icb_cmd_wdata[31:6],6'b0}+{20'b0,icb_cmd_wdata[5:0],6'b0})<=32'ha0040000 :
    st_cmd ? icb_cmd_wdata[5:0]==0 && icb_cmd_wdata>=32'ha0000000 &&""")
rep("""                                                (!meta_cmd || !meta_busy) && (!st_cmd || !st_busy)) :""",
    """                                                (!meta_cmd || (!meta_busy && !(meta_blk_cmd && wr_pre))) &&
                                                (!(st_cmd || st_pre_cmd) || !st_busy)) :""")
rep("if (legal_block && !weight_cmd && !meta_cmd && !st_cmd) begin",
    "if (legal_block && !weight_cmd && !meta_cmd && !st_cmd && !st_pre_cmd) begin")
# engine-start gating
rep("""   if (take_block && weight_cmd && legal_block && !st_hold_weight) begin""",
    """   if (take_block && weight_cmd && legal_block && !st_hold_weight && !wl_busy) begin""")
rep("""   end else if (take_block && legal_block && meta_cmd) begin""",
    """   end else if (take_block && legal_block && meta_cmd && !meta_busy && !(meta_blk_cmd && wr_pre)) begin""")
# addresses
rep(""" assign sw_cmd_addr = st_wbase + {17'b0, st_k, st_p, st_w, 2'b00};""",
    """ assign sw_cmd_addr = wr_pre ? pre_base + {20'b0, pre_wc, 2'b00} : st_wbase + {17'b0, st_k, st_p, st_w, 2'b00};""")
rep(""" assign sr_cmd_addr = st_wbase + {17'b0, st_rk, st_rp, st_rw, 2'b00} + 32'h40000;""",
    """ assign sr_cmd_addr = (rd_pre ? pre_base + {20'b0, pre_rc, 2'b00} : st_wbase + {17'b0, st_rk, st_rp, st_rw, 2'b00}) + 32'h40000;""")
# sequential
rep("""    st_p<=0; st_k<=0; st_w<=0; st_rp<=0; st_rk<=0; st_rw<=0;
   end else if (take_block && st_cmd && legal_block && !st_busy) begin
    st_busy<=1; st_rd_done<=0; st_buf_v<=0; st_wbase<={icb_cmd_wdata[31:9],9'b0};""",
    """    st_p<=0; st_k<=0; st_w<=0; st_rp<=0; st_rk<=0; st_rw<=0;
    pre_base<=0; pre_words<=0; pre_rc<=0; pre_wc<=0; rd_pre<=0; wr_pre<=0;
   end else if (take_block && st_pre_cmd && legal_block && !st_busy) begin
    pre_base<={icb_cmd_wdata[31:6],6'b0}; pre_words<={icb_cmd_wdata[5:0],4'b0};
   end else if (take_block && st_cmd && legal_block && !st_busy) begin
    rd_pre<=pre_words!=0; wr_pre<=pre_words!=0; pre_rc<=0; pre_wc<=0; pre_words<=pre_words;
    st_busy<=1; st_rd_done<=0; st_buf_v<=0; st_wbase<={icb_cmd_wdata[31:9],9'b0};""")
rep("""    if (sr_fire) begin
     st_rw<=st_rw+4'd1;""", """    if (sr_fire && rd_pre) begin
     pre_rc<=pre_rc+10'd1;
     if (pre_rc==pre_words-10'd1) rd_pre<=0;
    end else if (sr_fire) begin
     st_rw<=st_rw+4'd1;""")
rep("""    if (sw_fire) begin
     st_w<=st_w+4'd1;""", """    if (sw_fire && wr_pre) begin
     pre_wc<=pre_wc+10'd1;
     if (pre_wc==pre_words-10'd1) begin wr_pre<=0; pre_words<=0; end
    end else if (sw_fire) begin
     st_w<=st_w+4'd1;""")
if crlf:
    s = s.replace("\n", "\r\n")
p.write_bytes(s.encode())
print("fio pre-copy patched")
