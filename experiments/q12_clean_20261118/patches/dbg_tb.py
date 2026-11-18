R = [
 ("""   if(dut.u_fio.engine_commit_rsp_valid)begin""",
  """    if(`ENG.read_state!=dbg_read_state||`ENG.group!=dbg_group||`ENG.tile!=dbg_tile)begin
     $display("Q12DBG cycle=%0d read_state=%0d group=%0d tile=%0d write_state=%0d avail=%0d acked=%0d",
       cycles,`ENG.read_state,`ENG.group,`ENG.tile,`ENG.write_state,`ENG.gate_available,source_acked_prefix);
     dbg_read_state=`ENG.read_state;dbg_group=`ENG.group;dbg_tile=`ENG.tile;
    end
   if(dut.u_fio.engine_commit_rsp_valid)begin"""),
 (""" reg invalidation_acked=0,final_offered=0;""",
  """ reg invalidation_acked=0,final_offered=0;
 integer dbg_read_state=-1,dbg_group=-1,dbg_tile=-1;"""),
]

