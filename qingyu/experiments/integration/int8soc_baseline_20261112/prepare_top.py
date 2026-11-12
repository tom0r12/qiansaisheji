"""Derive an experimental top; keep the original official fabric untouched."""
from pathlib import Path
import hashlib
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
source=ROOT/'experiments/h1500v/opt33_readcache/rtl/qingyu_e203_soc_top.v'
text=source.read_text()
marker='`ifdef QINGYU_BLOCK_COPY\nwire cw_cmd_valid'
assert text.count(marker)==1
text=text[:text.index(marker)]
text,n=re.subn(r'`ifdef QINGYU_BLOCK_COPY\nwire (?:\[[^\n]+?\] )?block_mem_[^\n]+;\n`endif\n','',text)
assert n==10,n
text+='''// One DMA master goes through the existing CPU/DMA merger, then the
// unmodified official 32-bit memory fabric. Shared SRAM has one slave ingress.
wire shared_cache_clear;
qingyu_shared_sram u_shared(
 .clk(qingyu_bus_clk),.rst_n(qingyu_bus_rst_n),.cache_clear(shared_cache_clear),
 .icb_cmd_valid(sysmem_icb_cmd_valid),.icb_cmd_ready(sysmem_icb_cmd_ready),
 .icb_cmd_read(sysmem_icb_cmd_read),.icb_cmd_addr(sysmem_icb_cmd_addr),
 .icb_cmd_wdata(sysmem_icb_cmd_wdata),.icb_cmd_wmask(sysmem_icb_cmd_wmask),
 .icb_rsp_valid(sysmem_icb_rsp_valid),.icb_rsp_ready(sysmem_icb_rsp_ready),
 .icb_rsp_err(sysmem_icb_rsp_err),.icb_rsp_rdata(sysmem_icb_rsp_rdata)
);
qingyu_int8stream_fio u_fio(
 .clk(qingyu_bus_clk),.rst_n(qingyu_bus_rst_n),.shared_cache_clear(shared_cache_clear),
 .icb_cmd_valid(sysfio_icb_cmd_valid),.icb_cmd_ready(sysfio_icb_cmd_ready),
 .icb_cmd_read(sysfio_icb_cmd_read),.icb_cmd_addr(sysfio_icb_cmd_addr),
 .icb_cmd_wdata(sysfio_icb_cmd_wdata),.icb_cmd_wmask(sysfio_icb_cmd_wmask),
 .icb_rsp_valid(sysfio_icb_rsp_valid),.icb_rsp_ready(sysfio_icb_rsp_ready),
 .icb_rsp_err(sysfio_icb_rsp_err),.icb_rsp_rdata(sysfio_icb_rsp_rdata),
 .dma_cmd_valid(dma_icb_cmd_valid),.dma_cmd_ready(dma_icb_cmd_ready),
 .dma_cmd_read(dma_icb_cmd_read),.dma_cmd_addr(dma_icb_cmd_addr),
 .dma_cmd_wdata(dma_icb_cmd_wdata),.dma_cmd_wmask(dma_icb_cmd_wmask),
 .dma_rsp_valid(dma_icb_rsp_valid),.dma_rsp_ready(dma_icb_rsp_ready),
 .dma_rsp_err(dma_icb_rsp_err),.dma_rsp_rdata(dma_icb_rsp_rdata),
 .host_valid(qingyu_host_valid),.host_code(qingyu_host_code)
);
endmodule
'''
(HERE/'qingyu_e203_soc_top.v').write_text(text)
print('Generated top from opt33 SHA256 '+hashlib.sha256(source.read_bytes()).hexdigest())
