"""Move the two late declaration lines of q12_stream_engine_overlap.sv before
first use (VCS/DC require declare-before-use). Line multiset unchanged."""
import sys, pathlib
for f in sys.argv[1:]:
    p = pathlib.Path(f); t = p.read_text()
    l1 = ' wire wr_desc_ready,wr_word_ready,wr_done_valid,wr_done_error;\n'
    l2 = ' reg rd_desc_valid,rd_word_ready,wr_desc_valid,wr_desc_prefix,wr_word_valid,wr_word_last;\n'
    anchor = ' wire transport_busy,transport_draining;\n'
    if t.index(l1) < t.index(anchor):
        print('already', f); continue
    before = sorted(t.splitlines())
    t = t.replace(l1, '', 1).replace(l2, '', 1).replace(anchor, l1 + l2 + anchor, 1)
    assert sorted(t.splitlines()) == before
    p.write_text(t); print('moved', f)
