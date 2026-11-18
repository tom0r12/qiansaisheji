R = [
 ("wire gp_cmd_valid,gp_cmd_ready,gp_cmd_read;", "wire gp_cmd_valid,gp_cmd_ready,gp_cmd_read,gp_lock;"),
 (".gp_cmd_valid(gp_cmd_valid),", ".gp_cmd_valid(gp_cmd_valid),.gp_lock(gp_lock),"),
 (" .p_cmd_valid(gp_cmd_valid),", " .ppi_lock(gp_lock),\n .p_cmd_valid(gp_cmd_valid),"),
]
