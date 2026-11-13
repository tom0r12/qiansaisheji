"""Independent grammar examples for literal hierarchy preservation and rejection."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'server'))
from saif_macro_bridge import build_macro_overlay,instance_spans

text='''(SAIFILE (SAIFVERSION "2.0") (TIMESCALE 1 ps) (DURATION 1000)
(INSTANCE tb_q12soc (INSTANCE dut
 (INSTANCE u_e203_subsys_top (INSTANCE u_e203_subsys_main (INSTANCE u_mem_merge (INSTANCE u_original (NET (ready (T0 300) (T1 700) (TX 0) (TC 7)))))))
 (INSTANCE storage (INSTANCE banks\\[0\\] (INSTANCE slices\\[0\\] (INSTANCE macro_ram
   (PORT (CLK (T0 500) (T1 500) (TX 0) (TC 10)) (A\\[0\\] (T0 100) (T1 900) (TX 0) (TC 2)))))))
)))'''
rows=[('storage/banks[0].slices[0].macro_ram','RAMSP128X16','lib/RAMSP128X16')]
overlay,record=build_macro_overlay(text,rows)
spans,_=instance_spans(overlay)
assert 'tb_q12soc/dut/storage/banks\\[0\\].slices\\[0\\].macro_ram'in spans
assert '(CLK (T0 500) (T1 500) (TX 0) (TC 10))'in overlay
assert '(DURATION 1000)'in overlay and record['macro_count']==1
for bad in [rows+rows,[('wrong/path','RAMSP128X16','lib/RAMSP128X16')]]:
 try:build_macro_overlay(text,bad)
 except ValueError:pass
 else:raise AssertionError('Invalid mapping was accepted')
print('PASS lossless generated hierarchy, exact body preservation, duplicate and missing source rejection')
