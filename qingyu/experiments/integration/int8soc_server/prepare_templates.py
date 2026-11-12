"""Create an isolated INT8 assessment flow from reviewed fail-closed gates."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OLD=ROOT/'scripts/server_bus_bundle'
def once(text,old,new):
 if text.count(old)!=1:raise ValueError('Template anchor differs: '+old)
 return text.replace(old,new)
def put(path,text):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,newline='\n')
def main():
 used={}
 def read(name):
  p=OLD/name;used[name]=hashlib.sha256(p.read_bytes()).hexdigest();return p.read_text()
 for name in ['library_identity.example.tcl','macro_models.example.json','platform_config.example.tcl']:
  put(HERE/'templates'/name,read(name))
 common=read('assessment/common.tcl')
 common=once(common,'set defines {DISABLE_SV_ASSERTION=1 QINGYU_BLOCK_COPY QINGYU_READ_AHEAD QINGYU_FAST_TASK QINGYU_DOUBLE_BUFFER QINGYU_PIPE_MAC QINGYU_OUT16}','set defines {DISABLE_SV_ASSERTION=1}')
 common=once(common,'set frozen_inputs [dict create]','''set include_headers {}
set f [open [file join $bundle filelists includes.f] r]
foreach line [split [read $f] \\n] {if {[string trim $line] ne ""} {lappend include_headers [file join $bundle $line]}}
close $f
set frozen_inputs [dict create]''')
 common=once(common,'foreach p [concat $sources $STD_CELL_LIBS','foreach p [concat $sources $include_headers $STD_CELL_LIBS')
 common=once(common,'  return included_fio_accelerator_logic','''  if {[below $name u_fio/engine/compute]} {return included_compute_logic}
  if {[below $name u_fio/engine/transport]} {return included_transport_logic}
  if {[below $name u_fio/engine/decoder] || [below $name u_fio/engine/encoder]} {return included_codec_logic}
  if {[below $name u_fio/engine/reorder]} {return included_reorder_logic}
  if {[below $name u_fio/engine]} {return included_engine_control_logic}
  return included_fio_mmio_logic''')
 put(HERE/'templates/assessment/common.tcl',common)
 synth=read('assessment/synth.tcl')
 synth=once(synth,'included_new_bus_merges included_fio_accelerator_logic included_private_macro','included_new_bus_merges included_compute_logic included_transport_logic included_codec_logic included_reorder_logic included_engine_control_logic included_fio_mmio_logic included_private_macro')
 put(HERE/'templates/assessment/synth.tcl',synth)
 put(HERE/'templates/assessment/formal.tcl',read('assessment/formal.tcl'))
 power=read('assessment/sta_power.tcl').replace('CPU, both new merges, original bus, accelerator','CPU, new CPU/DMA merge, original bus, INT8 accelerator')
 put(HERE/'templates/assessment/sta_power.tcl',power)
 runner=read('run_bus_server.py')
 runner=once(runner,'def main():','''def verify_recorded_artifact(path, review_digest, result_digest):
    actual=digest(path)
    if actual!=review_digest or actual!=result_digest:
        raise ValueError('Activity artifact differs from its passed simulation record: '+str(path))
    return actual


def main():''')
 runner=runner.replace('run_bus_server.py','run_int8_server.py')
 runner=once(runner,"parser.add_argument('--layers',type=int,default=12)","parser.add_argument('--tasks',type=int,help='Run the first N explicitly listed sample/layer tasks; default all')")
 runner=once(runner,"if not re.fullmatch(r'tb_qingyu_bus_[a-z_]+performance',checker['top']):","if checker['top']!='tb_int8soc':")
 runner=once(runner,"    if not 1<=args.layers<=12:parser.error('layers must be 1..12')", "    task_count=args.tasks if args.tasks is not None else len(manifest['tasks'])\n    if not 1<=task_count<=len(manifest['tasks']):parser.error('tasks outside packaged list')")
 runner=runner.replace("checker['top']+'/fixture/dut'","checker['top']+'/dut'")
 runner=runner.replace("'source_layer'","'source_task'")
 runner=once(runner,"row=next(r for r in simulation['layers'] if r['layer']==review['source_task'])","row=next(r for r in simulation['layers'] if r['task_id']==review['source_task'])")
 runner=once(runner,"name='layer%02d'%review['source_task']","name=review['source_task']")
 runner=once(runner,"        if digest(source_run/(name+'.log'))!=review['source_log_sha256'] or digest(source_run/(name+'.vcd'))!=review['source_vcd_sha256']:","        verify_recorded_artifact(source_run/(name+'.log'),review['source_log_sha256'],row.get('log_sha256'))\n        verify_recorded_artifact(source_run/(name+'.vcd'),review['source_vcd_sha256'],row.get('vcd_sha256'))\n        if digest(source_run/(name+'.log'))!=review['source_log_sha256'] or digest(source_run/(name+'.vcd'))!=review['source_vcd_sha256']:")
 runner=once(runner,"        result['tool_completed']=True","        for name,wanted in manifest['files_sha256'].items():\n            if digest(inputs/name)!=wanted:raise RuntimeError('Assessment input changed: '+name)\n        result['tool_completed']=True")
 begin=runner.index('    for layer in range(args.layers):')
 end=runner.index("    for name,wanted in manifest['files_sha256'].items():",begin)
 replacement='''    for task in manifest['tasks'][:task_count]:
        name=task['task_id'];base=Path('inputs')/'tasks'/name
        command=[str(work/'simv'),'+FIRMWARE=inputs/firmware64.hex','+INPUT='+str(base/'input.hex'),
                 '+EXPECTED='+str(base/'expected_output.hex'),'+INPUT_WORDS='+str(task['input_words']),
                 '+OUTPUT_WORDS='+str(task['output_written_words']),'+LAYER='+str(task['layer'])]
        if args.activity:command.append('+ACTIVITY='+name+'.vcd')
        run(command,name+'.log');text=(work/(name+'.log')).read_text(errors='replace')
        marker='PASS real E203 INT8 physical packet task complete;' if args.mode=='macro' else 'PASS real E203 INT8 packet task complete;'
        if marker not in text:raise RuntimeError('Missing complete physical/numerical/path PASS')
        metrics={}
        tags=['INT8SOC_METRICS','QINGYU_ACTIVITY_START','QINGYU_ACTIVITY_END']
        if args.mode=='macro':tags+=['QINGYU_MACRO_PRELOAD_COMPLETE','QINGYU_MACRO_READBACK_COMPLETE']
        for tag in tags:
            found=re.findall('^'+tag+r' (.*)$',text,re.M)
            if len(found)!=1:raise RuntimeError('Missing/duplicate '+tag)
            metrics[tag]={k:int(v) for k,v in re.findall(r'(\\w+)=(-?\\d+)',found[0])}
        if metrics['INT8SOC_METRICS']!=task['expected_metrics']:raise RuntimeError('Same-input physical/behavioral task metrics differ')
        if metrics['QINGYU_ACTIVITY_END']['cycle']-metrics['QINGYU_ACTIVITY_START']['cycle']!=metrics['INT8SOC_METRICS']['cpu_setup_to_ack']:
            raise RuntimeError('Activity interval does not equal inclusive CPU setup window')
        if args.mode=='macro' and metrics['QINGYU_MACRO_READBACK_COMPLETE']['words']!=131072:raise RuntimeError('Incomplete physical guard/source/output readback')
        row=dict(task_id=name,layer=task['layer'],sample_index=task['sample_index'],metrics=metrics,output_allocation_words=6385,log_sha256=digest(work/(name+'.log')))
        if args.activity:row['vcd_sha256']=digest(work/(name+'.vcd'))
        result['layers'].append(row);save()
        print('PASS task='+name+' cycles='+str(metrics['INT8SOC_METRICS']['cpu_setup_to_ack']),flush=True)
'''
 runner=runner[:begin]+replacement+runner[end:]
 put(HERE/'templates/run_int8_server.py',runner)
 put(HERE/'TEMPLATE_ORIGINS.json',json.dumps(dict(source='scripts/server_bus_bundle',files_sha256=used,scope='Copied fail-closed gates; INT8-specific metrics, accounting, source lists and fixture are independent'),indent=2)+'\n')
 print('Prepared isolated INT8 templates')
if __name__=='__main__':main()
