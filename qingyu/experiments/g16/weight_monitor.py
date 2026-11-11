def instrument(data):
    text = data.replace(b"\r", b"").decode()
    decl = " integer ticks=0"
    assert text.count(decl) == 1
    text = text.replace(decl, " integer weight_commands=0, weight_reads=0, weight_writes=0;\n" + decl)
    marker = "  if (active) begin"
    assert text.count(marker) == 1
    text = text.replace(marker, marker + """
   if (fixture.dut.u_fio.take_block && fixture.dut.u_fio.weight_cmd)
    weight_commands++;
   if (`MEM.icb_cmd_valid && `MEM.icb_cmd_ready && `MEM.icb_cmd_read &&
       `MEM.icb_cmd_addr >= 32'ha0004000 && `MEM.icb_cmd_addr < 32'ha000c000) weight_reads++;
   if (fixture.dut.u_fio.weight_write) weight_writes++;
""")
    marker = "     end_tick=ticks;"
    assert text.count(marker) == 1
    text = text.replace(marker, marker + """
     if (weight_commands!=512 || weight_reads!=8192 || weight_writes!=8192)
      $fatal(1,"incomplete packed weight transfer commands=%0d reads=%0d writes=%0d",
             weight_commands,weight_reads,weight_writes);
     $display("QINGYU_WEIGHT_TRANSFER commands=%0d reads=%0d writes=%0d",
              weight_commands,weight_reads,weight_writes);
""")
    return text.encode()
