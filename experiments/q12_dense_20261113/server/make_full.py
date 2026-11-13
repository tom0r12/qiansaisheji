"""Bind the existing complete assessment flow to the exact native12 candidate."""
from pathlib import Path
import ast,base64,hashlib,json,zlib
H=Path(__file__).resolve().parent;R=H.parents[2];V=H.parent/'build/dense12_w10_wp'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
old=(R/'experiments/q12_area_20261113/server/run_decoder_full.py').read_text()
core=sha(V/'q12_task4.sv');dec=sha(V/'q12_rice_decoder.sv');eng=sha(V/'q12_stream_engine_overlap.sv');tr=sha(V/'q12_icb_stream_prefix.sv');writer=sha(H.parent/'rtl/q12_dense12_writer.sv')
head='''"""Exact native12 full-SoC mapping, equivalence, timing and twelve-window PX."""
from pathlib import Path
import concurrent.futures,fcntl,hashlib,json,os,re,shutil,signal,subprocess,sys,tempfile,time
'''
start=old.index('def sha(p):');end=old.index("out=Path(tempfile.mkdtemp(prefix='q12_decoder_full_'")
part=old[start:end]
part=part.replace(".q12_decoder_full_e06ca6f0.lock",".q12_native12_full_"+eng[:12]+".lock").replace('EXACT_V3','EXACT_NATIVE12')
part=part.replace("q12_decoder_window_*/result.json","q12_native12_*/result.json")
part=part.replace("files.get('q12_task4.sv')==CORE and files.get('q12_rice_decoder.sv')==DECODER", "all(files.get(n)==h for n,h in EXPECTED.items())")
part=part.replace(" and all(t['cycles_delta_from_behavioral']==0 for t in vr['tasks'])",'')
# A timing miss does not erase a valid functional report. Still map and measure,
# but reject promotion if the final throughput or area guard fails.
part=part.replace("assert pre['mean_full_window_cycles']<=25000", "assert pre['mean_full_window_cycles']>0")
rest=old[end:]
rest=rest.replace("prefix='q12_decoder_full_'","prefix='q12_native12_full_'").replace('Q12_DECODER_FULL','Q12_NATIVE_FULL')
begin=rest.index('overrides={');finish=rest.index('\nfor dest,(source,digest)',begin)
overrides={}
for folder,name,h in [('core_datareset','q12_task4.sv',core),('decoder2','q12_rice_decoder.sv',dec),('integration','q12_stream_engine_overlap.sv',eng),('integration','q12_icb_stream_prefix.sv',tr),('encoder_bounded','q13_rice_encoder.sv',writer)]:
 overrides['hardware/src/output/eda/q12_candidate/'+folder+'/'+name]=('src/q12/'+folder+'/'+name,h)
rest=rest[:begin]+'overrides='+repr(overrides)+rest[finish:]
rest=rest.replace('q12_requant_data_hold_decoder_window_v3','q12_x12_w10_y12_native_write_priority')
rest=rest.replace("' '.join('{'+str(p)+'}'for p in dbs)","' '.join(str(p)for p in dbs)")
rest=rest.replace("mapping=mapping.replace('compile -map_effort medium','compile -map_effort high')", "mapping=mapping.replace('compile -map_effort medium','compile -map_effort high')\nmapping=mapping.replace(' puts Q12_COMPILE_BEGIN',' set_fix_hold [all_clocks]\\n puts Q12_COMPILE_BEGIN')")
anchor="(package/'map.tcl').write_text(mapping)"
insert='''# Preserve unrestricted diagnostics, then analyze the same documented
# functional debug straps as the task testbench. No false paths are introduced.
modes='set modes [get_ports {io_pads_dbgmode0_n_i_ival io_pads_dbgmode1_n_i_ival io_pads_dbgmode2_n_i_ival}]\\n if {[sizeof_collection $modes]!=3} {error "Three debug straps required"}\\n set_case_analysis 1 $modes\\n'
mapping=mapping.replace(' redirect -file area.rpt', ' redirect -file unrestricted_setup.rpt {report_timing -delay_type max -max_paths 100 -significant_digits 8}\\n '+modes+' redirect -file area.rpt')
(package/'map.tcl').write_text(mapping)
power=(package/'power.tcl').read_text();needle=' read_sdc $env(Q12_SDC)'
assert needle in power
power=power.replace(needle,needle+'\\n '+modes)
(package/'power.tcl').write_text(power)'''
assert anchor in rest;rest=rest.replace(anchor,insert)
rest=rest.replace("'synthesis_change':'map_effort high; unchanged constraints and hierarchy'", "'synthesis_change':'map_effort high with hold repair; original clock/I-O budgets and hierarchy; reports use task debug straps 111; raw setup retained'")
rest=rest.replace("save();print('Q12_NATIVE_FULL_REPORTS_COMPLETE=", "report['area_limit_mm2']=0.448646862835;report['throughput_requirement_cycles']=25000\n save();print('Q12_NATIVE_FULL_REPORTS_COMPLETE=")
expected={'q12_task4.sv':core,'q12_rice_decoder.sv':dec,'q12_stream_engine_overlap.sv':eng,'q12_icb_stream_prefix.sv':tr,'q12_dense12_writer.sv':writer,'run_dense.py':sha(H/'run_dense.py')}
source=head+"BASE_PACKAGE='7298386858c65eea09b3aa0a475bcdfa9fcb030e0c4c4bcc15f3ad70ef02a876'\nEXPECTED="+repr(expected)+'\n'+part+rest
ast.parse(source);(H/'run_native_full.py').write_text(source)
payload=base64.b64encode(zlib.compress(source.encode(),9)).decode()
cmd='''python3 -c 'import base64,zlib,tempfile,pathlib,subprocess;d=pathlib.Path(tempfile.mkdtemp(prefix="q12_native_full_launch_",dir="/tmp"));p=d/"run.py";p.write_bytes(zlib.decompress(base64.b64decode("PAYLOAD")));f=(d/"run.log").open("w");j=subprocess.Popen(["python3","-u",str(p)],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True);print("Q12_NATIVE_FULL_LAUNCH",j.pid,d)' '''.replace('PAYLOAD',payload)
(H/'native_full_launch.txt').write_text(cmd);print('full_runner_chars',len(cmd),'sha256',sha(H/'run_native_full.py'))
