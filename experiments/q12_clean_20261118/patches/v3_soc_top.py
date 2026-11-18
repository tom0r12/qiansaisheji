R = [
 ("wire gp_cmd_valid,gp_cmd_ready,gp_cmd_read,gp_lock;", "wire gp_cmd_valid,gp_cmd_ready,gp_cmd_read,gp_lock;\nwire [13:0] gp_acked_words;"),
 (" .ppi_lock(gp_lock),\n", " .ppi_lock(gp_lock),.acked_words(gp_acked_words),\n"),
 (" .clk(qingyu_bus_clk),.rst_n(qingyu_bus_rst_n),.shared_cache_clear(shared_cache_clear),",
  " .clk(qingyu_bus_clk),.rst_n(qingyu_bus_rst_n),.shared_cache_clear(shared_cache_clear),\n .hw_acked_words({18'b0,gp_acked_words}),"),
]
