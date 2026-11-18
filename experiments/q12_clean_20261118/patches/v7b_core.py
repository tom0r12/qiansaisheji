R = [
 ("    logic [383:0] burst_data_q [0:2];", "    logic [319:0] burst_data_q [0:2];   // W10: 8 beats x 4 signed10"),
 ("                burst_data_q[burst_fill_q][int'(burst_fill_word_q)*48+:48]<=w_data;",
  "                burst_data_q[burst_fill_q][int'(burst_fill_word_q)*40+:40]<={w_data[45:36],w_data[33:24],w_data[21:12],w_data[9:0]};"),
 ("            w_wdata[c]=burst_data_q[burst_drain_q][c*24+:24];",
  "            w_wdata[c]={{2{burst_data_q[burst_drain_q][c*20+19]}},burst_data_q[burst_drain_q][c*20+10+:10],{2{burst_data_q[burst_drain_q][c*20+9]}},burst_data_q[burst_drain_q][c*20+:10]};"),
]
