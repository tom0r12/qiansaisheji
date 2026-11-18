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
wire sysfio_icb_cmd_read, sysfio_icb_rsp_valid, sysfio_icb_rsp_ready, sysfio_icb_rsp_err;
wire [31:0] sysfio_icb_cmd_addr, sysfio_icb_cmd_wdata, sysfio_icb_rsp_rdata;
wire [3:0] sysfio_icb_cmd_wmask;
wire qingyu_bus_clk, qingyu_bus_rst_n;
wire dma_icb_cmd_valid, dma_icb_cmd_ready, dma_icb_cmd_read;
wire [31:0] dma_icb_cmd_addr, dma_icb_cmd_wdata;
wire [3:0] dma_icb_cmd_wmask;
wire dma_icb_rsp_valid, dma_icb_rsp_ready, dma_icb_rsp_err;
wire [31:0] dma_icb_rsp_rdata;
wire shared_cache_clear;
wire gp_cmd_valid,gp_cmd_ready,gp_cmd_read;
wire [31:0] gp_cmd_addr,gp_cmd_wdata;
wire [3:0] gp_cmd_wmask;
wire gp_rsp_valid,gp_rsp_ready,gp_rsp_err;
wire [31:0] gp_rsp_rdata;
wire copy_cmd_valid,copy_cmd_ready,copy_cmd_read;
wire [31:0] copy_cmd_addr,copy_cmd_wdata;
wire [3:0] copy_cmd_wmask;
wire copy_rsp_valid,copy_rsp_ready,copy_rsp_err;
wire [31:0] copy_rsp_rdata;
wire memdma_cmd_valid,memdma_cmd_ready,memdma_cmd_read;
wire [31:0] memdma_cmd_addr,memdma_cmd_wdata;
wire [3:0] memdma_cmd_wmask;
wire memdma_rsp_valid,memdma_rsp_ready,memdma_rsp_err;
wire [31:0] memdma_rsp_rdata;

qingyu_e203_subsys_top u_e203_subsys_top(
 .qingyu_bus_clk(qingyu_bus_clk),
 .qingyu_bus_rst_n(qingyu_bus_rst_n),
 .gp_cmd_valid(gp_cmd_valid),
 .gp_cmd_ready(gp_cmd_ready),
 .gp_cmd_read(gp_cmd_read),
 .gp_cmd_addr(gp_cmd_addr),
 .gp_cmd_wdata(gp_cmd_wdata),
 .gp_cmd_wmask(gp_cmd_wmask),
 .gp_rsp_valid(gp_rsp_valid),
 .gp_rsp_ready(gp_rsp_ready),
 .gp_rsp_err(gp_rsp_err),
 .gp_rsp_rdata(gp_rsp_rdata),
 .dma_icb_cmd_valid(memdma_cmd_valid), .dma_icb_cmd_ready(memdma_cmd_ready),
 .dma_icb_cmd_read(memdma_cmd_read), .dma_icb_cmd_addr(memdma_cmd_addr),
 .dma_icb_cmd_wdata(memdma_cmd_wdata), .dma_icb_cmd_wmask(memdma_cmd_wmask),
 .dma_icb_rsp_valid(memdma_rsp_valid), .dma_icb_rsp_ready(memdma_rsp_ready),
 .dma_icb_rsp_err(memdma_rsp_err), .dma_icb_rsp_rdata(memdma_rsp_rdata),
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


// One DMA master goes through the existing CPU/DMA merger, then the
// unmodified official 32-bit memory fabric. Shared SRAM has one slave ingress.
qingyu_shared_sram u_shared(
 .clk(qingyu_bus_clk),.rst_n(qingyu_bus_rst_n),.cache_clear(shared_cache_clear),
 .icb_cmd_valid(sysmem_icb_cmd_valid),.icb_cmd_ready(sysmem_icb_cmd_ready),
 .icb_cmd_read(sysmem_icb_cmd_read),.icb_cmd_addr(sysmem_icb_cmd_addr),
 .icb_cmd_wdata(sysmem_icb_cmd_wdata),.icb_cmd_wmask(sysmem_icb_cmd_wmask),
 .icb_rsp_valid(sysmem_icb_rsp_valid),.icb_rsp_ready(sysmem_icb_rsp_ready),
 .icb_rsp_err(sysmem_icb_rsp_err),.icb_rsp_rdata(sysmem_icb_rsp_rdata)
);
wire fio_cmd_valid,fio_cmd_ready,fio_cmd_read;
wire [31:0] fio_cmd_addr,fio_cmd_wdata;
wire [3:0] fio_cmd_wmask;
wire fio_rsp_valid,fio_rsp_ready,fio_rsp_err;
wire [31:0] fio_rsp_rdata;
wire cfg_cmd_valid,cfg_cmd_ready,cfg_cmd_read;
wire [31:0] cfg_cmd_addr,cfg_cmd_wdata;
wire [3:0] cfg_cmd_wmask;
wire cfg_rsp_valid,cfg_rsp_ready,cfg_rsp_err;
wire [31:0] cfg_rsp_rdata;

wire copy_select = sysfio_icb_cmd_addr[31:4]==28'hf000008;
reg cfg_pending, cfg_owner;
wire selected_ready=copy_select?cfg_cmd_ready:fio_cmd_ready;
assign sysfio_icb_cmd_ready=!cfg_pending&&selected_ready;
assign fio_cmd_valid=sysfio_icb_cmd_valid&&!cfg_pending&&!copy_select;
assign cfg_cmd_valid=sysfio_icb_cmd_valid&&!cfg_pending&&copy_select;
assign sysfio_icb_rsp_valid=cfg_pending&&(cfg_owner?cfg_rsp_valid:fio_rsp_valid);
assign sysfio_icb_rsp_err=cfg_owner?cfg_rsp_err:fio_rsp_err;
assign sysfio_icb_rsp_rdata=cfg_owner?cfg_rsp_rdata:fio_rsp_rdata;
assign cfg_rsp_ready=cfg_pending&&cfg_owner&&sysfio_icb_rsp_ready;
assign fio_rsp_ready=cfg_pending&&!cfg_owner&&sysfio_icb_rsp_ready;
always @(posedge qingyu_bus_clk or negedge qingyu_bus_rst_n)
 if(!qingyu_bus_rst_n)begin cfg_pending<=0;cfg_owner<=0;end
 else begin
  if(sysfio_icb_cmd_valid&&sysfio_icb_cmd_ready)begin cfg_pending<=1;cfg_owner<=copy_select;end
  if(sysfio_icb_rsp_valid&&sysfio_icb_rsp_ready)cfg_pending<=0;
 end
q12_gpio_dma u_gpio_dma(
 .clk(qingyu_bus_clk),.rst_n(qingyu_bus_rst_n),
 .c_valid(cfg_cmd_valid),.c_ready(cfg_cmd_ready),.c_read(sysfio_icb_cmd_read),
 .c_addr(sysfio_icb_cmd_addr[3:0]),.c_data(sysfio_icb_cmd_wdata),.c_mask(sysfio_icb_cmd_wmask),
 .r_valid(cfg_rsp_valid),.r_ready(cfg_rsp_ready),.r_error(cfg_rsp_err),.r_data(cfg_rsp_rdata),
 .p_cmd_valid(gp_cmd_valid),
 .p_cmd_ready(gp_cmd_ready),
 .p_cmd_read(gp_cmd_read),
 .p_cmd_addr(gp_cmd_addr),
 .p_cmd_wdata(gp_cmd_wdata),
 .p_cmd_wmask(gp_cmd_wmask),
 .p_rsp_valid(gp_rsp_valid),
 .p_rsp_ready(gp_rsp_ready),
 .p_rsp_err(gp_rsp_err),
 .p_rsp_rdata(gp_rsp_rdata),
 .m_cmd_valid(copy_cmd_valid),
 .m_cmd_ready(copy_cmd_ready),
 .m_cmd_read(copy_cmd_read),
 .m_cmd_addr(copy_cmd_addr),
 .m_cmd_wdata(copy_cmd_wdata),
 .m_cmd_wmask(copy_cmd_wmask),
 .m_rsp_valid(copy_rsp_valid),
 .m_rsp_ready(copy_rsp_ready),
 .m_rsp_err(copy_rsp_err),
 .m_rsp_rdata(copy_rsp_rdata)
);
qingyu_icb_merge #(.NP(2),.OUTSTANDING(4),.ONE_PER_PORT(2'b00)) u_dma_channels(
 .clk(qingyu_bus_clk),.rst_n(qingyu_bus_rst_n),
 .s_cmd_valid({copy_cmd_valid,dma_icb_cmd_valid}),
 .s_cmd_ready({copy_cmd_ready,dma_icb_cmd_ready}),
 .s_cmd_read({copy_cmd_read,dma_icb_cmd_read}),
 .s_cmd_addr({copy_cmd_addr,dma_icb_cmd_addr}),
 .s_cmd_wdata({copy_cmd_wdata,dma_icb_cmd_wdata}),
 .s_cmd_wmask({copy_cmd_wmask,dma_icb_cmd_wmask}),
 .s_rsp_valid({copy_rsp_valid,dma_icb_rsp_valid}),
 .s_rsp_ready({copy_rsp_ready,dma_icb_rsp_ready}),
 .s_rsp_err({copy_rsp_err,dma_icb_rsp_err}),
 .s_rsp_rdata({copy_rsp_rdata,dma_icb_rsp_rdata}),
 .m_cmd_valid(memdma_cmd_valid),
 .m_cmd_ready(memdma_cmd_ready),
 .m_cmd_read(memdma_cmd_read),
 .m_cmd_addr(memdma_cmd_addr),
 .m_cmd_wdata(memdma_cmd_wdata),
 .m_cmd_wmask(memdma_cmd_wmask),
 .m_rsp_valid(memdma_rsp_valid),
 .m_rsp_ready(memdma_rsp_ready),
 .m_rsp_err(memdma_rsp_err),
 .m_rsp_rdata(memdma_rsp_rdata)
);
qingyu_q12_stream_fio u_fio(
 .clk(qingyu_bus_clk),.rst_n(qingyu_bus_rst_n),.shared_cache_clear(shared_cache_clear),
 .icb_cmd_valid(fio_cmd_valid),.icb_cmd_ready(fio_cmd_ready),
 .icb_cmd_read(sysfio_icb_cmd_read),.icb_cmd_addr(sysfio_icb_cmd_addr),
 .icb_cmd_wdata(sysfio_icb_cmd_wdata),.icb_cmd_wmask(sysfio_icb_cmd_wmask),
 .icb_rsp_valid(fio_rsp_valid),.icb_rsp_ready(fio_rsp_ready),
 .icb_rsp_err(fio_rsp_err),.icb_rsp_rdata(fio_rsp_rdata),
 .dma_cmd_valid(dma_icb_cmd_valid),.dma_cmd_ready(dma_icb_cmd_ready),
 .dma_cmd_read(dma_icb_cmd_read),.dma_cmd_addr(dma_icb_cmd_addr),
 .dma_cmd_wdata(dma_icb_cmd_wdata),.dma_cmd_wmask(dma_icb_cmd_wmask),
 .dma_rsp_valid(dma_icb_rsp_valid),.dma_rsp_ready(dma_icb_rsp_ready),
 .dma_rsp_err(dma_icb_rsp_err),.dma_rsp_rdata(dma_icb_rsp_rdata),
 .host_valid(qingyu_host_valid),.host_code(qingyu_host_code)
);
endmodule
