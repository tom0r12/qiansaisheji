"""Derive the manufacturer-memory (vendor) testbench from the local clean tb.

Reuses the reviewed physical-port preload/readback transformation of the
frozen Q12 flow (output/eda/q12_final_20261113/vendor/make_vendor_tb.py) and
the reviewed GPIO-variant adjustments; only lexical anchors that differ in the
clean tb are adapted here. No vendor storage array name appears in the result.
"""
from pathlib import Path
WORK = Path(__file__).resolve().parents[4]
OLD = WORK / 'output/eda/q12_final_20261113/vendor/make_vendor_tb.py'
LEGACY = WORK / 'output/github-qiansaisheji/qingyu/experiments/integration/int8soc_compact_server/tb_int8soc_macro.sv'
CLEAN_PASS = ('PASS real E203 Q12 GPIO cold task; original GPIOA/B pins, internal peripheral DMA, NP2 original System Bus, '
              'fixed12 input (no entropy coding), plain shared SRAM (no readcache); 12689 dense words/source/guards verified')


def make_testbench(base, n128=30):
    import re
    found = re.findall(r'PASS real E203 Q12 GPIO cold task;[^"]*', base)
    if len(found) != 1: raise ValueError('clean PASS line not unique')
    clean_pass = found[0]
    helper = OLD.read_text().replace('\r\n', '\n')
    helper = helper.replace('dut.u_fio.u_engine_fio.engine_done', 'dut.u_fio.engine_done')
    helper = helper.replace('if(cycles>1000000)', 'if(cycles>20000000)')
    old = 'PASS real E203 Q12 cold task; explicit independent loader and original System Bus; 10353 slots/source/guards verified'
    helper = helper.replace(old, clean_pass)
    helper = helper.replace('explicit independent loader and original System Bus; manufacturer SRAM',
                            'GPIO burst, fixed12 input, plain shared SRAM, original System Bus; manufacturer SRAM')
    helper = helper.replace('output_slots=10353', 'output_words=12689')
    # The clean shared SRAM has no cache_clear port: drop those fixture lines.
    helper = helper.replace("tasks=tasks.replace('   force `SHARED.cache_clear=loader_clear;',\n                        '   fixture_attached=1;\\n   force `SHARED.cache_clear=loader_clear;')",
                            "tasks=tasks.replace('   force `SHARED.cache_clear=loader_clear;\\n','   fixture_attached=1;\\n')")
    helper = helper.replace("tasks=tasks.replace('   release `SHARED.rst_n; release `SHARED.clk;',",
                            "tasks=tasks.replace('   release `SHARED.cache_clear;\\n','');tasks=tasks.replace('   release `SHARED.rst_n; release `SHARED.clk;',")
    ns = {}
    exec(compile(helper, str(OLD), 'exec'), ns)
    base = base.replace('\r\n', '\n')
    base = base.replace('if(`ITCM.mem_r[i]!==firmware[i])', 'if(itcm_readback[i]!==firmware[i])')
    base = base.replace("last_ack=cycles;last_ack_ps=longint'($realtime*1000.0);$display", 'last_ack=cycles;$display')
    text = ns['make_testbench'](base, LEGACY.read_text().replace('\r\n', '\n'))
    text = text.replace('last_ack=cycles;$display', "last_ack=cycles;last_ack_ps=longint'($realtime*1000.0);$display")
    text = text.replace(' reg activity_enabled=0;', ''' reg activity_enabled=0;
 reg[63:0]itcm_readback[0:8191];
 event fullwindow_dump_stop;
 always @(fullwindow_dump_stop)begin #0.001;$dumpoff;end''')
    text = text.replace('if(activity_enabled)$dumpoff;', 'if(activity_enabled)->fullwindow_dump_stop;')
    marker = '  $display("Q12_MACRO_READBACK_COMPLETE words=131072'
    assert text.count(marker) == 1
    check = '''  tcm_fixture_attached=1;
  force `ITCM.clk=clk;force `ITCM.cs=itcm_cs;force `ITCM.we=1'b0;
  force `ITCM.addr=itcm_address;
  for(integer a=0;a<8192;a++)begin
   @(negedge clk);itcm_cs=1;itcm_address=13'(a);
   @(posedge clk);@(posedge clk);#1;itcm_readback[a]=`ITCM.dout;
  end
  @(negedge clk);itcm_cs=0;
  release `ITCM.clk;release `ITCM.cs;release `ITCM.we;release `ITCM.addr;
  tcm_fixture_attached=0;
'''
    text = text.replace(marker, check + marker)
    if 'cache_clear' in text.split('task attach_shared_loader;')[1].split('endtask')[0]:
        raise ValueError('cache_clear fixture remains')
    if 'PASS real E203 Q12 vendor task;' not in text:
        raise ValueError('vendor PASS anchor missing')
    if text.count('macro128_count!=30') != 1:
        raise ValueError('macro count anchor')
    text = text.replace('macro128_count!=30', 'macro128_count!=%d' % n128)
    return text, ns['MACRO_BIND']


if __name__ == '__main__':
    import sys
    t, b = make_testbench(Path(sys.argv[1]).read_text())
    Path(sys.argv[2]).write_text(t, newline='\n')
    Path(sys.argv[3]).write_text(b, newline='\n')
    print('VENDOR_TB_OK')
