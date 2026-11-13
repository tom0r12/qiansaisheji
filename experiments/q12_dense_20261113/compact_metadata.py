"""Store C-bias once, removing two private macro stripes and an output adder.

For 32 products of signed10 weights, -8372224 <= C <= 8388608.
For any accepted signed22 bias, C-bias fits signed25. Shift is in [0,47].
The 32-bit word therefore holds one pad bit, six shift bits and signed25 C-bias.
"""
def transform(core):
 def replace(old,new):
  nonlocal core
  assert core.count(old)==1,(old,core.count(old));core=core.replace(old,new)
 assert 'logic [319:0] wp_wdata;'in core,'requires signed10 private storage contract'
 replace('logic signed [21:0] bias_load_q [0:31], active_bias_q [0:15];','logic signed [21:0] bias_load_q [0:31];')
 replace('logic [63:0] m_wdata;', 'logic [31:0] m_wdata;\n    wire signed [28:0] metadata_c_minus_bias = c_acc_q[meta_write_q] - {{7{bias_load_q[meta_write_q][21]}},bias_load_q[meta_write_q]};')
 replace('wire [63:0] m_rdata;', 'wire [31:0] m_rdata;')
 replace('wire unused_cache_padding = ^{r_rdata[31:29],m_rdata[63:59]};','wire unused_cache_padding = ^{r_rdata[31:29],m_rdata[31]};')
 replace("m_wdata={5'b0,shift_load_q[meta_write_q],bias_load_q[meta_write_q],c_acc_q[meta_write_q]};",
         "m_wdata={1'b0,shift_load_q[meta_write_q][5:0],metadata_c_minus_bias[24:0]};")
 replace('q12_striped_sram #(.WIDTH(64),.DEPTH(128),.ADDR_W(7)) metadata_memory',
         'q12_striped_sram #(.WIDTH(32),.DEPTH(128),.ADDR_W(7)) metadata_memory')
 replace(".wmask(64'hffffffffffffffff),.rdata(m_rdata)",".wmask(32'hffffffff),.rdata(m_rdata)")
 replace('-{{3{active_c_q[lane][28]}},active_c_q[lane]}+{{10{active_bias_q[lane][21]}},active_bias_q[lane]};',
         '-{{3{active_c_q[lane][28]}},active_c_q[lane]};')
 replace('active_c_q[i]<=0; active_bias_q[i]<=0; active_shift_q[i]<=0;',
         'active_c_q[i]<=0; active_shift_q[i]<=0;')
 replace('active_c_q[rd_index_q[3:0]]<=m_rdata[28:0];',
         'active_c_q[rd_index_q[3:0]]<={{4{m_rdata[24]}},m_rdata[24:0]};')
 replace('active_bias_q[rd_index_q[3:0]]<=m_rdata[50:29]; active_shift_q[rd_index_q[3:0]]<=m_rdata[58:51];',
         "active_shift_q[rd_index_q[3:0]]<={2'b0,m_rdata[30:25]};")
 return core
