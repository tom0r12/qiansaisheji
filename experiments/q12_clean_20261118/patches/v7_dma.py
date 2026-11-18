R = [
 (" reg[31:0]fifo[0:15];", " reg[31:0]fifo[0:7];"),
 (" assign m_cmd_wdata=fifo[mem_issued[3:0]];", " assign m_cmd_wdata=fifo[mem_issued[2:0]];"),
 (" wire fifo_full=(received-mem_issued)>=14'd16;", " wire fifo_full=(received-mem_issued)>=14'd8;"),
 ("      fifo[received[3:0]]<=p_rsp_rdata;received<=received+1'b1;", "      fifo[received[2:0]]<=p_rsp_rdata;received<=received+1'b1;"),
]
