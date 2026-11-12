`include "e203_defines.v"
 /*                                                                      
 Copyright 2018-2020 Nuclei System Technology, Inc.                
                                                                         
 Licensed under the Apache License, Version 2.0 (the "License");         
 you may not use this file except in compliance with the License.        
 You may obtain a copy of the License at                                 
                                                                         
     http://www.apache.org/licenses/LICENSE-2.0                          
                                                                         
  Unless required by applicable law or agreed to in writing, software    
 distributed under the License is distributed on an "AS IS" BASIS,       
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and     
 limitations under the License.                                          
 */                                                                      
                                                                         
                                                                         
                                                                         
module qingyu_e203_soc_top(
  output wire qingyu_host_valid, output wire [31:0] qingyu_host_code,


    // This clock should comes from the crystal pad generated high speed clock (16MHz)
  input  hfextclk,
  output hfxoscen,// The signal to enable the crystal pad generated clock

  // This clock should comes from the crystal pad generated low speed clock (32.768KHz)
  input  lfextclk,
  output lfxoscen,// The signal to enable the crystal pad generated clock


  // The JTAG TCK is input, need to be pull-up
  input   io_pads_jtag_TCK_i_ival,

  // The JTAG TMS is input, need to be pull-up
  input   io_pads_jtag_TMS_i_ival,

  // The JTAG TDI is input, need to be pull-up
  input   io_pads_jtag_TDI_i_ival,

  // The JTAG TDO is output have enable
  output  io_pads_jtag_TDO_o_oval,
  output  io_pads_jtag_TDO_o_oe,

  // The GPIO are all bidir pad have enables
  input  [32-1:0] io_pads_gpioA_i_ival,
  output [32-1:0] io_pads_gpioA_o_oval,
  output [32-1:0] io_pads_gpioA_o_oe,

  input  [32-1:0] io_pads_gpioB_i_ival,
  output [32-1:0] io_pads_gpioB_o_oval,
  output [32-1:0] io_pads_gpioB_o_oe,

  //QSPI0 SCK and CS is output without enable
  output  io_pads_qspi0_sck_o_oval,
  output  io_pads_qspi0_cs_0_o_oval,

  //QSPI0 DQ is bidir I/O with enable, and need pull-up enable
  input   io_pads_qspi0_dq_0_i_ival,
  output  io_pads_qspi0_dq_0_o_oval,
  output  io_pads_qspi0_dq_0_o_oe,
  input   io_pads_qspi0_dq_1_i_ival,
  output  io_pads_qspi0_dq_1_o_oval,
  output  io_pads_qspi0_dq_1_o_oe,
  input   io_pads_qspi0_dq_2_i_ival,
  output  io_pads_qspi0_dq_2_o_oval,
  output  io_pads_qspi0_dq_2_o_oe,
  input   io_pads_qspi0_dq_3_i_ival,
  output  io_pads_qspi0_dq_3_o_oval,
  output  io_pads_qspi0_dq_3_o_oe,
  
  // Erst is input need to be pull-up by default
  input   io_pads_aon_erst_n_i_ival,

  // dbgmode are inputs need to be pull-up by default
  input  io_pads_dbgmode0_n_i_ival,
  input  io_pads_dbgmode1_n_i_ival,
  input  io_pads_dbgmode2_n_i_ival,

  // BootRom is input need to be pull-up by default
  input  io_pads_bootrom_n_i_ival,


  // dwakeup is input need to be pull-up by default
  input  io_pads_aon_pmu_dwakeup_n_i_ival,

      // PMU output is just output without enable
  output io_pads_aon_pmu_padrst_o_oval,
  output io_pads_aon_pmu_vddpaden_o_oval 
);


 
 wire sysper_icb_cmd_valid;
 wire sysper_icb_cmd_ready;

 wire sysfio_icb_cmd_valid;
 wire sysfio_icb_cmd_ready;

 wire sysmem_icb_cmd_valid;
 wire sysmem_icb_cmd_ready;

 wire sysmem_icb_cmd_read, sysmem_icb_rsp_valid, sysmem_icb_rsp_ready, sysmem_icb_rsp_err;
wire [31:0] sysmem_icb_cmd_addr, sysmem_icb_cmd_wdata, sysmem_icb_rsp_rdata;
wire [3:0] sysmem_icb_cmd_wmask;
`ifdef QINGYU_BLOCK_COPY
wire block_mem_cmd_valid;
`endif
`ifdef QINGYU_BLOCK_COPY
wire block_mem_cmd_ready;
`endif
`ifdef QINGYU_BLOCK_COPY
wire block_mem_cmd_read;
`endif
`ifdef QINGYU_BLOCK_COPY
wire [31:0] block_mem_cmd_addr;
`endif
`ifdef QINGYU_BLOCK_COPY
wire [31:0] block_mem_cmd_wdata;
`endif
`ifdef QINGYU_BLOCK_COPY
wire [3:0] block_mem_cmd_wmask;
`endif
`ifdef QINGYU_BLOCK_COPY
wire block_mem_rsp_valid;
`endif
`ifdef QINGYU_BLOCK_COPY
wire block_mem_rsp_ready;
`endif
`ifdef QINGYU_BLOCK_COPY
wire block_mem_rsp_err;
`endif
`ifdef QINGYU_BLOCK_COPY
wire [31:0] block_mem_rsp_rdata;
`endif
wire sysfio_icb_cmd_read, sysfio_icb_rsp_valid, sysfio_icb_rsp_ready, sysfio_icb_rsp_err;
wire [31:0] sysfio_icb_cmd_addr, sysfio_icb_cmd_wdata, sysfio_icb_rsp_rdata;
wire [3:0] sysfio_icb_cmd_wmask;
wire qingyu_bus_clk, qingyu_bus_rst_n;
wire dma_icb_cmd_valid, dma_icb_cmd_ready, dma_icb_cmd_read;
wire [31:0] dma_icb_cmd_addr, dma_icb_cmd_wdata;
wire [3:0] dma_icb_cmd_wmask;
wire dma_icb_rsp_valid, dma_icb_rsp_ready, dma_icb_rsp_err;
wire [31:0] dma_icb_rsp_rdata;
qingyu_e203_subsys_top u_e203_subsys_top(
 .qingyu_bus_clk(qingyu_bus_clk),
 .qingyu_bus_rst_n(qingyu_bus_rst_n),
 .dma_icb_cmd_valid(dma_icb_cmd_valid), .dma_icb_cmd_ready(dma_icb_cmd_ready),
 .dma_icb_cmd_read(dma_icb_cmd_read), .dma_icb_cmd_addr(dma_icb_cmd_addr),
 .dma_icb_cmd_wdata(dma_icb_cmd_wdata), .dma_icb_cmd_wmask(dma_icb_cmd_wmask),
 .dma_icb_rsp_valid(dma_icb_rsp_valid), .dma_icb_rsp_ready(dma_icb_rsp_ready),
 .dma_icb_rsp_err(dma_icb_rsp_err), .dma_icb_rsp_rdata(dma_icb_rsp_rdata),
    .core_mhartid      (1'b0),
  



  `ifdef E203_HAS_ITCM_EXTITF //{
    .ext2itcm_icb_cmd_valid  (1'b0),
    .ext2itcm_icb_cmd_ready  (),
    .ext2itcm_icb_cmd_addr   (`E203_ITCM_ADDR_WIDTH'b0 ),
    .ext2itcm_icb_cmd_read   (1'b0 ),
    .ext2itcm_icb_cmd_wdata  (32'b0),
    .ext2itcm_icb_cmd_wmask  (4'b0),
    
    .ext2itcm_icb_rsp_valid  (),
    .ext2itcm_icb_rsp_ready  (1'b0),
    .ext2itcm_icb_rsp_err    (),
    .ext2itcm_icb_rsp_rdata  (),
  `endif//}

  `ifdef E203_HAS_DTCM_EXTITF //{
    .ext2dtcm_icb_cmd_valid  (1'b0),
    .ext2dtcm_icb_cmd_ready  (),
    .ext2dtcm_icb_cmd_addr   (`E203_DTCM_ADDR_WIDTH'b0 ),
    .ext2dtcm_icb_cmd_read   (1'b0 ),
    .ext2dtcm_icb_cmd_wdata  (32'b0),
    .ext2dtcm_icb_cmd_wmask  (4'b0),
    
    .ext2dtcm_icb_rsp_valid  (),
    .ext2dtcm_icb_rsp_ready  (1'b0),
    .ext2dtcm_icb_rsp_err    (),
    .ext2dtcm_icb_rsp_rdata  (),
  `endif//}

  .sysper_icb_cmd_valid (sysper_icb_cmd_valid),
  .sysper_icb_cmd_ready (sysper_icb_cmd_ready),
  .sysper_icb_cmd_read  (), 
  .sysper_icb_cmd_addr  (), 
  .sysper_icb_cmd_wdata (), 
  .sysper_icb_cmd_wmask (), 
  
  .sysper_icb_rsp_valid (sysper_icb_cmd_valid),
  .sysper_icb_rsp_ready (sysper_icb_cmd_ready),
  .sysper_icb_rsp_err   (1'b0  ),
  .sysper_icb_rsp_rdata (32'b0),


  .sysfio_icb_cmd_valid(sysfio_icb_cmd_valid),
  .sysfio_icb_cmd_ready(sysfio_icb_cmd_ready),
  .sysfio_icb_cmd_read(sysfio_icb_cmd_read), 
  .sysfio_icb_cmd_addr(sysfio_icb_cmd_addr), 
  .sysfio_icb_cmd_wdata(sysfio_icb_cmd_wdata), 
  .sysfio_icb_cmd_wmask(sysfio_icb_cmd_wmask), 
   
  .sysfio_icb_rsp_valid(sysfio_icb_rsp_valid),
  .sysfio_icb_rsp_ready(sysfio_icb_rsp_ready),
  .sysfio_icb_rsp_err(sysfio_icb_rsp_err),
  .sysfio_icb_rsp_rdata(sysfio_icb_rsp_rdata),

  .sysmem_icb_cmd_valid(sysmem_icb_cmd_valid),
  .sysmem_icb_cmd_ready(sysmem_icb_cmd_ready),
  .sysmem_icb_cmd_read(sysmem_icb_cmd_read), 
  .sysmem_icb_cmd_addr(sysmem_icb_cmd_addr), 
  .sysmem_icb_cmd_wdata(sysmem_icb_cmd_wdata), 
  .sysmem_icb_cmd_wmask(sysmem_icb_cmd_wmask), 

  .sysmem_icb_rsp_valid(sysmem_icb_rsp_valid),
  .sysmem_icb_rsp_ready(sysmem_icb_rsp_ready),
  .sysmem_icb_rsp_err(sysmem_icb_rsp_err),
  .sysmem_icb_rsp_rdata(sysmem_icb_rsp_rdata),

  .io_pads_jtag_TCK_i_ival    (io_pads_jtag_TCK_i_ival    ),
  .io_pads_jtag_TCK_o_oval    (),
  .io_pads_jtag_TCK_o_oe      (),
  .io_pads_jtag_TCK_o_ie      (),
  .io_pads_jtag_TCK_o_pue     (),
  .io_pads_jtag_TCK_o_ds      (),

  .io_pads_jtag_TMS_i_ival    (io_pads_jtag_TMS_i_ival    ),
  .io_pads_jtag_TMS_o_oval    (),
  .io_pads_jtag_TMS_o_oe      (),
  .io_pads_jtag_TMS_o_ie      (),
  .io_pads_jtag_TMS_o_pue     (),
  .io_pads_jtag_TMS_o_ds      (),

  .io_pads_jtag_TDI_i_ival    (io_pads_jtag_TDI_i_ival    ),
  .io_pads_jtag_TDI_o_oval    (),
  .io_pads_jtag_TDI_o_oe      (),
  .io_pads_jtag_TDI_o_ie      (),
  .io_pads_jtag_TDI_o_pue     (),
  .io_pads_jtag_TDI_o_ds      (),

  .io_pads_jtag_TDO_i_ival    (1'b1    ),
  .io_pads_jtag_TDO_o_oval    (io_pads_jtag_TDO_o_oval    ),
  .io_pads_jtag_TDO_o_oe      (io_pads_jtag_TDO_o_oe      ),
  .io_pads_jtag_TDO_o_ie      (),
  .io_pads_jtag_TDO_o_pue     (),
  .io_pads_jtag_TDO_o_ds      (),

  .io_pads_jtag_TRST_n_i_ival (1'b1 ),
  .io_pads_jtag_TRST_n_o_oval (),
  .io_pads_jtag_TRST_n_o_oe   (),
  .io_pads_jtag_TRST_n_o_ie   (),
  .io_pads_jtag_TRST_n_o_pue  (),
  .io_pads_jtag_TRST_n_o_ds   (),

  .test_mode(1'b0),
  .test_iso_override(1'b0),

  .io_pads_gpioA_i_ival       (io_pads_gpioA_i_ival),
  .io_pads_gpioA_o_oval       (io_pads_gpioA_o_oval),
  .io_pads_gpioA_o_oe         (io_pads_gpioA_o_oe), 

  .io_pads_gpioB_i_ival       (io_pads_gpioB_i_ival),
  .io_pads_gpioB_o_oval       (io_pads_gpioB_o_oval),
  .io_pads_gpioB_o_oe         (io_pads_gpioB_o_oe), 

  .io_pads_qspi0_sck_i_ival   (1'b1),
  .io_pads_qspi0_sck_o_oval   (io_pads_qspi0_sck_o_oval),
  .io_pads_qspi0_sck_o_oe     (),
  .io_pads_qspi0_dq_0_i_ival  (io_pads_qspi0_dq_0_i_ival),
  .io_pads_qspi0_dq_0_o_oval  (io_pads_qspi0_dq_0_o_oval),
  .io_pads_qspi0_dq_0_o_oe    (io_pads_qspi0_dq_0_o_oe),
  .io_pads_qspi0_dq_1_i_ival  (io_pads_qspi0_dq_1_i_ival),
  .io_pads_qspi0_dq_1_o_oval  (io_pads_qspi0_dq_1_o_oval),
  .io_pads_qspi0_dq_1_o_oe    (io_pads_qspi0_dq_1_o_oe),
  .io_pads_qspi0_dq_2_i_ival  (io_pads_qspi0_dq_2_i_ival),
  .io_pads_qspi0_dq_2_o_oval  (io_pads_qspi0_dq_2_o_oval),
  .io_pads_qspi0_dq_2_o_oe    (io_pads_qspi0_dq_2_o_oe),
  .io_pads_qspi0_dq_3_i_ival  (io_pads_qspi0_dq_3_i_ival),
  .io_pads_qspi0_dq_3_o_oval  (io_pads_qspi0_dq_3_o_oval),
  .io_pads_qspi0_dq_3_o_oe    (io_pads_qspi0_dq_3_o_oe),
  .io_pads_qspi0_cs_0_i_ival  (1'b1),
  .io_pads_qspi0_cs_0_o_oval  (io_pads_qspi0_cs_0_o_oval),
  .io_pads_qspi0_cs_0_o_oe    (), 

    .hfextclk        (hfextclk),
    .hfxoscen        (hfxoscen),
    .lfextclk        (lfextclk),
    .lfxoscen        (lfxoscen),

  .io_pads_aon_erst_n_i_ival        (io_pads_aon_erst_n_i_ival       ), 
  .io_pads_aon_erst_n_o_oval        (),
  .io_pads_aon_erst_n_o_oe          (),
  .io_pads_aon_erst_n_o_ie          (),
  .io_pads_aon_erst_n_o_pue         (),
  .io_pads_aon_erst_n_o_ds          (),
  .io_pads_aon_pmu_dwakeup_n_i_ival (io_pads_aon_pmu_dwakeup_n_i_ival),
  .io_pads_aon_pmu_dwakeup_n_o_oval (),
  .io_pads_aon_pmu_dwakeup_n_o_oe   (),
  .io_pads_aon_pmu_dwakeup_n_o_ie   (),
  .io_pads_aon_pmu_dwakeup_n_o_pue  (),
  .io_pads_aon_pmu_dwakeup_n_o_ds   (),
  .io_pads_aon_pmu_vddpaden_i_ival  (1'b1 ),
  .io_pads_aon_pmu_vddpaden_o_oval  (io_pads_aon_pmu_vddpaden_o_oval ),
  .io_pads_aon_pmu_vddpaden_o_oe    (),
  .io_pads_aon_pmu_vddpaden_o_ie    (),
  .io_pads_aon_pmu_vddpaden_o_pue   (),
  .io_pads_aon_pmu_vddpaden_o_ds    (),

  
    .io_pads_aon_pmu_padrst_i_ival    (1'b1 ),
    .io_pads_aon_pmu_padrst_o_oval    (io_pads_aon_pmu_padrst_o_oval ),
    .io_pads_aon_pmu_padrst_o_oe      (),
    .io_pads_aon_pmu_padrst_o_ie      (),
    .io_pads_aon_pmu_padrst_o_pue     (),
    .io_pads_aon_pmu_padrst_o_ds      (),

    .io_pads_bootrom_n_i_ival       (io_pads_bootrom_n_i_ival),
    .io_pads_bootrom_n_o_oval       (),
    .io_pads_bootrom_n_o_oe         (),
    .io_pads_bootrom_n_o_ie         (),
    .io_pads_bootrom_n_o_pue        (),
    .io_pads_bootrom_n_o_ds         (),

    .io_pads_dbgmode0_n_i_ival       (io_pads_dbgmode0_n_i_ival),

    .io_pads_dbgmode1_n_i_ival       (io_pads_dbgmode1_n_i_ival),

    .io_pads_dbgmode2_n_i_ival       (io_pads_dbgmode2_n_i_ival) 


  );


`ifdef QINGYU_BLOCK_COPY
wire cw_cmd_valid, cw_cmd_ready, cw_rsp_valid, cw_rsp_err;
wire [31:0] cw_cmd_addr, cw_cmd_wdata;
wire ld_cmd_valid, ld_cmd_ready, ld_rsp_valid, ld_rsp_err;
wire [31:0] ld_cmd_addr, ld_rsp_rdata;
wire sr_cmd_valid, sr_cmd_ready, sr_rsp_valid, sr_rsp_err;
wire [31:0] sr_cmd_addr, sr_rsp_rdata;
wire sw_cmd_valid, sw_cmd_ready, sw_rsp_valid, sw_rsp_err;
wire [31:0] sw_cmd_addr, sw_cmd_wdata;
wire in_cmd_valid, in_cmd_ready, in_rsp_valid, in_rsp_err;
wire [31:0] in_cmd_addr, in_rsp_rdata;
// Round-robin DMA arbitration. Every accepted data word enters mem_fab.
// Port order: 0 cw, 1 sw, 2 mem/block, 3 ld, 4 in, 5 sr.
 qingyu_icb_merge #(.NP(6), .OUTSTANDING(4), .ONE_PER_PORT(6'b111011)) u_dma_merge (
 .clk(qingyu_bus_clk), .rst_n(qingyu_bus_rst_n),
 .s_cmd_valid({sr_cmd_valid,in_cmd_valid,ld_cmd_valid,block_mem_cmd_valid,sw_cmd_valid,cw_cmd_valid}),
 .s_cmd_ready({sr_cmd_ready,in_cmd_ready,ld_cmd_ready,block_mem_cmd_ready,sw_cmd_ready,cw_cmd_ready}),
 .s_cmd_read({1'b1,1'b1,1'b1,block_mem_cmd_read,1'b0,1'b0}),
 .s_cmd_addr({sr_cmd_addr,in_cmd_addr,ld_cmd_addr,block_mem_cmd_addr,sw_cmd_addr,cw_cmd_addr}),
 .s_cmd_wdata({32'b0,32'b0,32'b0,block_mem_cmd_wdata,sw_cmd_wdata,cw_cmd_wdata}),
 .s_cmd_wmask({4'h0,4'h0,4'h0,block_mem_cmd_wmask,4'hf,4'hf}),
 .s_rsp_valid({sr_rsp_valid,in_rsp_valid,ld_rsp_valid,block_mem_rsp_valid,sw_rsp_valid,cw_rsp_valid}),
 .s_rsp_ready({1'b1,1'b1,1'b1,block_mem_rsp_ready,1'b1,1'b1}),
 .s_rsp_err({sr_rsp_err,in_rsp_err,ld_rsp_err,block_mem_rsp_err,sw_rsp_err,cw_rsp_err}),
 .s_rsp_rdata({sr_rsp_rdata,in_rsp_rdata,ld_rsp_rdata,block_mem_rsp_rdata,dma_unused_sw_data,dma_unused_cw_data}),
 .m_cmd_valid(dma_icb_cmd_valid), .m_cmd_ready(dma_icb_cmd_ready),
 .m_cmd_read(dma_icb_cmd_read), .m_cmd_addr(dma_icb_cmd_addr),
 .m_cmd_wdata(dma_icb_cmd_wdata), .m_cmd_wmask(dma_icb_cmd_wmask),
 .m_rsp_valid(dma_icb_rsp_valid), .m_rsp_ready(dma_icb_rsp_ready),
 .m_rsp_err(dma_icb_rsp_err), .m_rsp_rdata(dma_icb_rsp_rdata)
);
wire [31:0] dma_unused_sw_data, dma_unused_cw_data;
`else
assign dma_icb_cmd_valid=1'b0;
assign dma_icb_cmd_read=1'b0;
assign dma_icb_cmd_addr=32'b0;
assign dma_icb_cmd_wdata=32'b0;
assign dma_icb_cmd_wmask=4'b0;
assign dma_icb_rsp_ready=1'b1;
`endif
// This is the only shared SRAM ingress: the official decoder's sysmem slave.
// Accepted software reset invalidates only speculative cache state. Already
// accepted shared responses still drain according to the slave protocol.
wire shared_cache_clear=sysfio_icb_cmd_valid && sysfio_icb_cmd_ready &&
 !sysfio_icb_cmd_read && sysfio_icb_cmd_addr==32'hf0000004 &&
 sysfio_icb_cmd_wmask==4'hf && sysfio_icb_cmd_wdata[2];
qingyu_shared_sram u_shared(
 .clk(qingyu_bus_clk), .rst_n(qingyu_bus_rst_n), .cache_clear(shared_cache_clear),
 .icb_cmd_valid(sysmem_icb_cmd_valid), .icb_cmd_ready(sysmem_icb_cmd_ready),
 .icb_cmd_read(sysmem_icb_cmd_read), .icb_cmd_addr(sysmem_icb_cmd_addr),
 .icb_cmd_wdata(sysmem_icb_cmd_wdata), .icb_cmd_wmask(sysmem_icb_cmd_wmask),
 .icb_rsp_valid(sysmem_icb_rsp_valid), .icb_rsp_ready(sysmem_icb_rsp_ready),
 .icb_rsp_err(sysmem_icb_rsp_err), .icb_rsp_rdata(sysmem_icb_rsp_rdata)
);
qingyu_fio u_fio(
 .clk(qingyu_bus_clk), .rst_n(qingyu_bus_rst_n),

`ifdef QINGYU_BLOCK_COPY
 .cpu_cmd_valid(1'b0),
 .cpu_cmd_ready(),
 .cpu_cmd_read(1'b0),
 .cpu_cmd_addr(32'b0),
 .cpu_cmd_wdata(32'b0),
 .cpu_cmd_wmask(4'b0),
 .cpu_rsp_valid(),
 .cpu_rsp_ready(1'b1),
 .cpu_rsp_err(),
 .cpu_rsp_rdata(),
 .mem_cmd_valid(block_mem_cmd_valid),
 .mem_cmd_ready(block_mem_cmd_ready),
 .mem_cmd_read(block_mem_cmd_read),
 .mem_cmd_addr(block_mem_cmd_addr),
 .mem_cmd_wdata(block_mem_cmd_wdata),
 .mem_cmd_wmask(block_mem_cmd_wmask),
 .mem_rsp_valid(block_mem_rsp_valid),
 .mem_rsp_ready(block_mem_rsp_ready),
 .mem_rsp_err(block_mem_rsp_err),
 .mem_rsp_rdata(block_mem_rsp_rdata),
 .cw_cmd_valid(cw_cmd_valid), .cw_cmd_ready(cw_cmd_ready), .cw_cmd_addr(cw_cmd_addr), .cw_cmd_wdata(cw_cmd_wdata),
 .cw_rsp_valid(cw_rsp_valid), .cw_rsp_err(cw_rsp_err),
 .ld_cmd_valid(ld_cmd_valid), .ld_cmd_ready(ld_cmd_ready), .ld_cmd_addr(ld_cmd_addr),
 .ld_rsp_valid(ld_rsp_valid), .ld_rsp_err(ld_rsp_err), .ld_rsp_rdata(ld_rsp_rdata),
 .sr_cmd_valid(sr_cmd_valid), .sr_cmd_ready(sr_cmd_ready), .sr_cmd_addr(sr_cmd_addr),
 .sr_rsp_valid(sr_rsp_valid), .sr_rsp_err(sr_rsp_err), .sr_rsp_rdata(sr_rsp_rdata),
 .sw_cmd_valid(sw_cmd_valid), .sw_cmd_ready(sw_cmd_ready), .sw_cmd_addr(sw_cmd_addr), .sw_cmd_wdata(sw_cmd_wdata),
 .sw_rsp_valid(sw_rsp_valid), .sw_rsp_err(sw_rsp_err),
 .in_cmd_valid(in_cmd_valid), .in_cmd_ready(in_cmd_ready), .in_cmd_addr(in_cmd_addr),
 .in_rsp_valid(in_rsp_valid), .in_rsp_err(in_rsp_err), .in_rsp_rdata(in_rsp_rdata),
`endif
 .icb_cmd_valid(sysfio_icb_cmd_valid),
 .icb_cmd_ready(sysfio_icb_cmd_ready),
 .icb_cmd_read(sysfio_icb_cmd_read),
 .icb_cmd_addr(sysfio_icb_cmd_addr),
 .icb_cmd_wdata(sysfio_icb_cmd_wdata),
 .icb_cmd_wmask(sysfio_icb_cmd_wmask),
 .icb_rsp_valid(sysfio_icb_rsp_valid),
 .icb_rsp_ready(sysfio_icb_rsp_ready),
 .icb_rsp_err(sysfio_icb_rsp_err),
 .icb_rsp_rdata(sysfio_icb_rsp_rdata),
 .host_valid(qingyu_host_valid), .host_code(qingyu_host_code)
);

endmodule
