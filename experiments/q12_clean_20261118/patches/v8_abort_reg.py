# v8: break the combinational loop datapath_fault -> abort_now -> transport.soft_abort
# -> wr_word_ready/encoder ready -> datapath_fault (DC OPT-150/314, Formality B failure).
# The transport now sees the abort one cycle later, in the first ABORT_DRAIN cycle
# (same mechanism the IDLE config-fault path already uses). Normal tasks never abort,
# so cycle counts are unchanged.
R = [
    (".soft_abort(abort_now || (state==ABORT_DRAIN && !abort_issued)),",
     ".soft_abort(state==ABORT_DRAIN && !abort_issued),", 1),
    ("    state<=ABORT_DRAIN;error<=1;abort_issued<=1;\n",
     "    state<=ABORT_DRAIN;error<=1;abort_issued<=0;\n", 1),
]
