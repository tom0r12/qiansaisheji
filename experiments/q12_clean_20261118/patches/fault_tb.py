# Test-only TB hook (NOT shipped): overwrite one GPIO source word to exercise the engine abort path.
R = [
    ("  if(layout_words!=input_words)$fatal(1,\"fixed12 input packet length mismatch\");\n",
     "  if(layout_words!=input_words)$fatal(1,\"fixed12 input packet length mismatch\");\n"
     "  if($value$plusargs(\"FAULT_WORD=%d\",fault_word))begin\n"
     "   if(!$value$plusargs(\"FAULT_VALUE=%h\",fault_value))fault_value=32'hffffffff;\n"
     "   source_image[fault_word]=fault_value;$display(\"FAULT_INJECT word=%0d value=%h\",fault_word,fault_value);\n"
     "   #1 u_source.image[fault_word]=fault_value;\n"
     "  end\n", 1),
    (" integer dump_requested=0,dump_fd;\n",
     " integer dump_requested=0,dump_fd;\n integer fault_word;reg [31:0] fault_value;\n", 1),
    (" always @(negedge dut.qingyu_bus_clk)if(dut.qingyu_bus_rst_n&&dut.u_fio.engine_done)done_cycle=cycles;\n",
     " always @(negedge dut.qingyu_bus_clk)if(dut.qingyu_bus_rst_n&&dut.u_fio.engine_done)begin done_cycle=cycles;"
     "$display(\"ENGINE_DONE cycle=%0d error_code=%h\",cycles,dut.u_fio.engine_error_code);end\n", 1),
]
