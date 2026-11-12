#!/usr/bin/env python3
"""Validate or execute an immutable bus bundle in a fresh directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def verify_recorded_artifact(path, review_digest, result_digest):
    actual=digest(path)
    if actual!=review_digest or actual!=result_digest:
        raise ValueError('Activity artifact differs from its passed simulation record: '+str(path))
    return actual


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['validate','behavioral','macro','synth','sta','formal','power'],default='validate')
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--activity',action='store_true')
    parser.add_argument('--tasks',type=int,help='Run the first N explicitly listed sample/layer tasks; default all')
    parser.add_argument('--config',type=Path,help='Reviewed server-local Tcl configuration for assessment modes')
    parser.add_argument('--mapped-run',type=Path,help='This bundle\'s completed synthesis directory')
    parser.add_argument('--activity-review',type=Path,help='Power: reviewed activity provenance JSON')
    parser.add_argument('--macro-model-manifest',type=Path,help='Reviewed identity and hashes of the external manufacturer SRAM models')
    args=parser.parse_args()
    bundle=Path(__file__).resolve().parent
    manifest=json.loads((bundle/'manifest.json').read_text())
    if manifest.get('required_macro_references')!=['RAMSP128X16','RAMSP4096X16'] or manifest.get('private_mapping',{}).get('valid_words') not in [352,416]:
        raise ValueError('Unknown compact macro composition')
    if digest(bundle/'assessment/private_x_config.v')!=manifest['private_mapping']['configuration_sha256']:
        raise ValueError('Private configuration differs from passed four-state compilation')
    checker=manifest['checker']
    if checker['top']!='tb_int8soc':
        raise ValueError('Unknown scoreboard top')
    task_count=args.tasks if args.tasks is not None else len(manifest['tasks'])
    if not 1<=task_count<=len(manifest['tasks']):parser.error('tasks outside packaged list')
    for name,wanted in manifest['files_sha256'].items():
        if digest(bundle/name)!=wanted:raise RuntimeError('Bundle content changed: '+name)
    if args.mode=='validate':
        print('PASS immutable official-bus bundle; no EDA executed');return
    assess=args.mode in ['synth','sta','formal','power']
    if assess and (not args.config or not args.config.is_file()):parser.error('Assessment requires --config with real libraries and full-SoC constraints')
    if args.mode in ['sta','formal','power'] and (not args.mapped_run or not (args.mapped_run/'assessment_provenance.tcl').is_file()):
        parser.error('Use --mapped-run from this bundle synthesis, never a historical netlist')
    toolname={'synth':'dc_shell','sta':'pt_shell','formal':'fm_shell','power':'pt_shell'}.get(args.mode,'vcs')
    tool=os.environ.get('QINGYU_'+toolname.upper()) or shutil.which(toolname)
    if not tool:raise RuntimeError('Missing '+toolname+'; configure QINGYU_'+toolname.upper())
    macros=[]
    if args.mode=='macro':
        identity_path=args.macro_model_manifest or Path(os.environ.get('QINGYU_SRAM_MODEL_IDENTITY',''))
        if not identity_path.is_file():
            raise RuntimeError('Macro simulation requires --macro-model-manifest from reviewed manufacturer files; no stand-in is accepted')
        identity=json.loads(identity_path.read_text())
        if identity.get('review')!='accepted' or identity.get('model_kind')!='official_manufacturer' or identity.get('source_library')!='SRAM_Lib_2025':
            raise ValueError('Manufacturer SRAM model identity is not reviewed')
        root=Path(os.environ.get('QINGYU_SRAM_MODELS','/storage1/admin_public_dir/SRAM_Lib_2025'))
        macros=[root/n/'verilog'/(n+'.v') for n in manifest['required_macro_references']]
        for p in macros:
            if not p.is_file():raise RuntimeError('Missing official macro model: '+str(p))
            if identity.get('files',{}).get(p.stem)!=digest(p):raise ValueError('Manufacturer model hash differs: '+p.stem)
        if not identity.get('origin_review'):raise ValueError('Record the reviewed official source of the manufacturer models')
    review=None
    if args.mode=='power':
        if not args.activity_review:parser.error('Power requires --activity-review; RTL VCD alone is not mapped power evidence')
        review=json.loads(args.activity_review.read_text())
        required=['activity_file','activity_sha256','netlist_sha256','start_ps','end_ps','strip_path','mapping_review','sram_power_review','measurement_scope',
                  'source_run','source_task','source_result_sha256','source_log_sha256','source_vcd_sha256','power_scope']
        if any(k not in review for k in required):raise ValueError('Incomplete activity review')
        activity=Path(review['activity_file'])
        if activity.suffix!='.saif':raise ValueError('Power entry requires reviewed, window-trimmed SAIF; convert and audit RTL VCD separately')
        if digest(activity)!=review['activity_sha256']:raise ValueError('Activity hash differs')
        if digest(args.mapped_run/'qingyu_e203_soc_top_mapped.v')!=review['netlist_sha256']:raise ValueError('Activity is not reviewed against this netlist')
        if review['mapping_review']!='accepted' or review['sram_power_review']!='accepted':raise ValueError('Mapping and SRAM power review must be accepted explicitly')
        if review['power_scope']!='full_digital_soc':raise ValueError('Power must include CPU, fabric, all SRAM, interfaces and peripherals')
        if review['strip_path'].strip('/')!=checker['top']+'/dut':raise ValueError('Activity mapping must start at the complete SoC instance')
        if review['end_ps']<=review['start_ps']:raise ValueError('Invalid activity window')
        saif=activity.read_text(errors='strict')
        unit=re.search(r'\(TIMESCALE\s+([0-9.]+)\s+(fs|ps|ns|us|ms|s)\s*\)',saif)
        duration=re.search(r'\(DURATION\s+([0-9.]+)\s*\)',saif)
        if not unit or not duration:raise ValueError('SAIF timescale/duration missing')
        duration_ps=float(duration[1])*float(unit[1])*{'fs':.001,'ps':1,'ns':1000,'us':1e6,'ms':1e9,'s':1e12}[unit[2]]
        if abs(duration_ps-(review['end_ps']-review['start_ps']))>1:raise ValueError('SAIF duration differs from measured window')
        source_run=Path(review['source_run']);source_result=source_run/'result.json'
        if digest(source_result)!=review['source_result_sha256']:raise ValueError('Activity simulation result changed')
        simulation=json.loads(source_result.read_text())
        if not simulation.get('passed') or simulation.get('mode')!='macro' or simulation.get('manifest_sha256')!=digest(bundle/'manifest.json'):
            raise ValueError('Activity must originate from this bundle\'s passed official-macro simulation')
        row=next(r for r in simulation['layers'] if r['task_id']==review['source_task'])
        name=review['source_task']
        verify_recorded_artifact(source_run/(name+'.log'),review['source_log_sha256'],row.get('log_sha256'))
        verify_recorded_artifact(source_run/(name+'.vcd'),review['source_vcd_sha256'],row.get('vcd_sha256'))
        if digest(source_run/(name+'.log'))!=review['source_log_sha256'] or digest(source_run/(name+'.vcd'))!=review['source_vcd_sha256']:
            raise ValueError('Measured log/VCD provenance mismatch')
        if row['metrics']['QINGYU_ACTIVITY_START']['time_ps']!=review['start_ps'] or row['metrics']['QINGYU_ACTIVITY_END']['time_ps']!=review['end_ps']:
            raise ValueError('Review window differs from measured simulation timestamps')
    print('PASS file/tool preflight mode='+args.mode,flush=True)
    if assess:print('Library identity, configuration values and complete clocks are checked by the tool before compilation, not by this file preflight.',flush=True)
    if args.preflight:return
    parent=Path(os.environ.get('QINGYU_RUN_PARENT',str(Path.home()/'Desktop'))).resolve()
    if not parent.is_dir():raise RuntimeError('Run parent must exist')
    work=Path(tempfile.mkdtemp(prefix='qingyu_verify_'+manifest['candidate']+'_'+args.mode+'_',dir=str(parent)))
    inputs=work/'inputs';shutil.copytree(bundle,inputs)
    print('QINGYU_RUN_DIRECTORY='+str(work),flush=True)
    result=dict(passed=False,mode=args.mode,candidate=manifest['candidate'],manifest_sha256=digest(bundle/'manifest.json'),
                runner_kind=manifest['runner_kind'],checker_top=checker['top'],
                limits=['No official loader integration','No PPA or signoff inferred from simulation'],layers=[])
    def save(): (work/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    def run(command,log,environment=None):
        result['last_command']=command;save()
        with (work/log).open('w') as stream:
            subprocess.run(command,cwd=work,env=environment,stdout=stream,stderr=subprocess.STDOUT,check=True)
    save()
    if assess:
        environment=os.environ.copy()
        environment.update(QINGYU_BUNDLE=str(inputs),QINGYU_WORK=str(work),QINGYU_PLATFORM_CONFIG=str(args.config.resolve()),
                           QINGYU_STAGE=args.mode,QINGYU_BUNDLE_SHA256=result['manifest_sha256'])
        if args.mapped_run:
            mapped_manifest=json.loads((args.mapped_run/'result.json').read_text())
            if mapped_manifest.get('manifest_sha256')!=result['manifest_sha256']:raise ValueError('Mapped run belongs to another bundle')
            environment['QINGYU_MAPPED_RUN']=str(args.mapped_run.resolve())
        if review:
            (work/'activity_review.json').write_text(json.dumps(review,indent=2)+'\n')
            environment.update(QINGYU_ACTIVITY_FILE=str(Path(review['activity_file']).resolve()),
                               QINGYU_ACTIVITY_STRIP=review['strip_path'],QINGYU_ACTIVITY_START_PS=str(review['start_ps']),
                               QINGYU_ACTIVITY_END_PS=str(review['end_ps']))
        script='synth.tcl' if args.mode=='synth' else 'formal.tcl' if args.mode=='formal' else 'sta_power.tcl'
        run([tool,'-f',str(inputs/'assessment'/script)],args.mode+'.log',environment)
        for name,wanted in manifest['files_sha256'].items():
            if digest(inputs/name)!=wanted:raise RuntimeError('Assessment input changed: '+name)
        result['tool_completed']=True
        result['status']='artifacts_generated_pending_report_review'
        # Tool exit zero does not establish timing, equivalence or power coverage.
        save();print('EDA artifacts retained; review reports before acceptance: '+str(work));return
    lines=[str(inputs/x) for x in (inputs/'filelists'/(args.mode+'.f')).read_text().splitlines()]+list(map(str,macros))
    if any('"' in x or '\n' in x for x in lines):raise ValueError('Unsupported source pathname')
    (work/'sources.f').write_text('\n'.join('"'+x+'"' for x in lines)+'\n')
    includes=['+incdir+'+str(inputs/'vendor/e203_hbirdv2/rtl/e203'/d) for d in ['core','perips','perips/apb_i2c']]
    command=[tool,'-full64','-sverilog','-timescale=1ns/1ps','+define+DISABLE_SV_ASSERTION=1',
             '+define+QINGYU_X_VALID_WORDS='+str(manifest['private_mapping']['valid_words']),
             '-top',checker['top'],*includes,'-f',str(work/'sources.f'),'-Mdir='+str(work/'csrc'),'-o',str(work/'simv')]
    if args.mode=='macro':command.append('+define+ARM_UD_MODEL')
    if args.activity:command.append('-debug_access+all')
    result['macro_model_sha256']={str(p):digest(p) for p in macros}
    if args.mode=='macro':
        result['macro_model_identity_sha256']=digest(identity_path)
        (work/'macro_model_identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    run(command,'compile.log')
    for task in manifest['tasks'][:task_count]:
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
            metrics[tag]={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',found[0])}
        if metrics['INT8SOC_METRICS']!=task['expected_metrics']:raise RuntimeError('Same-input physical/behavioral task metrics differ')
        if metrics['QINGYU_ACTIVITY_END']['cycle']-metrics['QINGYU_ACTIVITY_START']['cycle']!=metrics['INT8SOC_METRICS']['cpu_setup_to_ack']:
            raise RuntimeError('Activity interval does not equal inclusive CPU setup window')
        if args.mode=='macro' and metrics['QINGYU_MACRO_READBACK_COMPLETE']['words']!=131072:raise RuntimeError('Incomplete physical guard/source/output readback')
        row=dict(task_id=name,layer=task['layer'],sample_index=task['sample_index'],metrics=metrics,output_allocation_words=6385,log_sha256=digest(work/(name+'.log')))
        if args.activity:row['vcd_sha256']=digest(work/(name+'.vcd'))
        result['layers'].append(row);save()
        print('PASS task='+name+' cycles='+str(metrics['INT8SOC_METRICS']['cpu_setup_to_ack']),flush=True)
    for name,wanted in manifest['files_sha256'].items():
        if digest(inputs/name)!=wanted:raise RuntimeError('Execution input changed: '+name)
    if any(digest(p)!=result['macro_model_sha256'][str(p)] for p in macros):raise RuntimeError('Manufacturer macro model changed during execution')
    result['passed']=True;save();print('PASS numerical and official-bus validation '+str(work/'result.json'))


if __name__=='__main__':main()
