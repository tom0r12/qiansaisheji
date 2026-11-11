"""opt5: SoC top uses the 5-port shared SRAM.  Bank priority (low index wins):
 0 cw (block copy write) > 1 sw (staging write) > 2 mem (CPU / block engine)
 > 3 ld (weight + metadata read) > 4 sr (staging read)."""
import sys, pathlib

p = pathlib.Path(sys.argv[1])
raw = p.read_bytes().decode()
crlf = "\r\n" in raw
s = raw.replace("\r\n", "\n")
old_start = s.index("qingyu_shared_sram u_shared(")
old_end = s.index("qingyu_fio u_fio(")
new_shared = """`ifdef QINGYU_BLOCK_COPY
wire cw_cmd_valid, cw_cmd_ready, cw_rsp_valid, cw_rsp_err;
wire [31:0] cw_cmd_addr, cw_cmd_wdata;
wire ld_cmd_valid, ld_cmd_ready, ld_rsp_valid, ld_rsp_err;
wire [31:0] ld_cmd_addr, ld_rsp_rdata;
wire sr_cmd_valid, sr_cmd_ready, sr_rsp_valid, sr_rsp_err;
wire [31:0] sr_cmd_addr, sr_rsp_rdata;
wire sw_cmd_valid, sw_cmd_ready, sw_rsp_valid, sw_rsp_err;
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
assign ld_rsp_rdata = mp_rsp_rdata[127:96];
assign block_mem_rsp_rdata = mp_rsp_rdata[95:64];
`else
qingyu_shared_sram u_shared(
 .clk(qingyu_bus_clk), .rst_n(qingyu_bus_rst_n),
 .icb_cmd_valid(sysmem_icb_cmd_valid),
 .icb_cmd_ready(sysmem_icb_cmd_ready),
 .icb_cmd_read(sysmem_icb_cmd_read),
 .icb_cmd_addr(sysmem_icb_cmd_addr),
 .icb_cmd_wdata(sysmem_icb_cmd_wdata),
 .icb_cmd_wmask(sysmem_icb_cmd_wmask),
 .icb_rsp_valid(sysmem_icb_rsp_valid),
 .icb_rsp_ready(sysmem_icb_rsp_ready),
 .icb_rsp_err(sysmem_icb_rsp_err),
 .icb_rsp_rdata(sysmem_icb_rsp_rdata)
);
`endif
"""
s = s[:old_start] + new_shared + s[old_end:]
anchor = " .mem_rsp_rdata(block_mem_rsp_rdata),\n"
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + """ .cw_cmd_valid(cw_cmd_valid), .cw_cmd_ready(cw_cmd_ready), .cw_cmd_addr(cw_cmd_addr), .cw_cmd_wdata(cw_cmd_wdata),
 .cw_rsp_valid(cw_rsp_valid), .cw_rsp_err(cw_rsp_err),
 .ld_cmd_valid(ld_cmd_valid), .ld_cmd_ready(ld_cmd_ready), .ld_cmd_addr(ld_cmd_addr),
 .ld_rsp_valid(ld_rsp_valid), .ld_rsp_err(ld_rsp_err), .ld_rsp_rdata(ld_rsp_rdata),
 .sr_cmd_valid(sr_cmd_valid), .sr_cmd_ready(sr_cmd_ready), .sr_cmd_addr(sr_cmd_addr),
 .sr_rsp_valid(sr_rsp_valid), .sr_rsp_err(sr_rsp_err), .sr_rsp_rdata(sr_rsp_rdata),
 .sw_cmd_valid(sw_cmd_valid), .sw_cmd_ready(sw_cmd_ready), .sw_cmd_addr(sw_cmd_addr), .sw_cmd_wdata(sw_cmd_wdata),
 .sw_rsp_valid(sw_rsp_valid), .sw_rsp_err(sw_rsp_err),
""")
if crlf:
    s = s.replace("\n", "\r\n")
p.write_bytes(s.encode())
print("top patched")
