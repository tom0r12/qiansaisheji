R = [
 ("  input wire gp_cmd_valid,gp_cmd_read,", "  input wire gp_cmd_valid,gp_cmd_read,gp_lock,"),
 (" .clk(hfclk),.rst_n(bus_rst_n),\n .s_cmd_valid({gp_cmd_valid,ppi_icb_cmd_valid}),",
  " .clk(hfclk),.rst_n(bus_rst_n),.dma_lock(gp_lock),\n .s_cmd_valid({gp_cmd_valid,ppi_icb_cmd_valid}),"),
]
