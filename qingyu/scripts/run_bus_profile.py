"""Profile a four-row production candidate without changing frozen validation runners.

The measured cold-task window begins at the first source parameter read and
ends when the originating DMA accepts the final output write response.
Testbench initialization of the source
staging region occurs before reset and is explicitly outside this window.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

from run_candidate_soc import (ROOT, DEFINES, sha, run, synthetic_images,
                               verify_images, normalized_build_arguments,
                               verify_build_arguments)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', default='opt30_fusedpipe4', help='Candidate directory (default: %(default)s)')
    parser.add_argument('--layers', type=int, default=1)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--seed', type=int, default=20261111)
    parser.add_argument('--images', type=Path)
    parser.add_argument('--data-kind', default='SYNTHETIC_ENGINEERING')
    parser.add_argument('--reuse-build', type=Path)
    args = parser.parse_args()
    if not 1 <= args.layers <= 12 or args.jobs < 1:
        parser.error('layers must be 1..12; jobs must be positive')
    if bool(args.images) != (args.data_kind != 'SYNTHETIC_ENGINEERING'):
        parser.error('External images require explicit provenance data-kind')
    provenance = verify_images(args.images, args.data_kind, args.layers) if args.images else None
    for tool in ['verilator', 'g++', 'make', 'riscv64-unknown-elf-gcc',
                 'riscv64-unknown-elf-objcopy', 'iverilog', 'vvp']:
        if not shutil.which(tool):
            parser.error('Missing tool: ' + tool)
    candidate = ROOT / 'experiments/h1500v' / args.candidate / 'rtl'
    if not candidate.is_dir():
        parser.error('Missing candidate: ' + str(candidate))
    work = ROOT/'build'/('bus_profile_' + args.candidate + '_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
    work.mkdir(parents=True)
    verification_path=candidate.parent/'verification_contract.json'
    verification_snapshot=sha(verification_path) if verification_path.exists() else None
    verification={'live_read_words':11936,'source_load_words':11936,
                  'live_write_words':11936,'private_input_words':3168,'private_weight_words':8192}
    if verification_path.exists():
        verification.update(json.loads(verification_path.read_text()))
    for k,v in [('source_load_words',11936),('live_write_words',11936),('private_input_words',3168),('private_weight_words',8192)]:
        if verification[k]!=v: raise ValueError('Unsupported verification contract: '+k)
    if verification['live_read_words'] not in [11936,576]:
        raise ValueError('Unsupported live-read contract')
    config = work/'config.v'
    config.write_text('`timescale 1ns/1ps\n' + ''.join('`define '+d+'\n' for d in DEFINES)+
                      '`define QINGYU_EXPECT_LIVE_READS '+str(verification['live_read_words'])+'\n')
    source_template=ROOT/'scripts/fixtures/e203_soc_sources.f'
    source_template_snapshot=sha(source_template)
    baseline=source_template.read_text().splitlines()
    replacements = {'build/block_config.v':config, 'build/timescale.v':None,
        'build/dual_row_study/qingyu_accel.sv':candidate/'qingyu_accel.sv',
        'rtl/qingyu_fio.sv':candidate/'qingyu_fio.sv',
        'rtl/qingyu_shared_sram.sv':candidate/'qingyu_shared_sram.sv',
        'tb/tb_qingyu_soc.sv':ROOT/'tb/tb_qingyu_bus_soc.sv',
        'tb/tb_qingyu_soc_performance.sv':ROOT/'tb/tb_qingyu_bus_queue_performance.sv'}
    for filename in ['qingyu_e203_soc_top.v','qingyu_e203_subsys_main.v','qingyu_e203_subsys_top.v']:
        replacements['generated/'+filename] = candidate/filename
    sources = [replacements.get(n,ROOT/n) for n in baseline if n.strip()]
    sources = [p for p in sources if p is not None] + [candidate/'qingyu_icb_merge.sv',ROOT/'tb/tb_qingyu_bus_profile.sv']
    for p in sources:
        if not p.is_file():
            raise FileNotFoundError(p)
    vendor_manifest_path=ROOT/'reports/e203-source-manifest.json'
    vendor_manifest=json.loads(vendor_manifest_path.read_text())
    if not vendor_manifest.get('ready') or vendor_manifest.get('commit')!='9f3e34f337f5d0a1236a285871ffa2032491617a':
        raise ValueError('Pinned E203 verification manifest missing or invalid; run setup_local.ps1 -CheckOnly')
    vendor_prefix=ROOT/'vendor/e203_hbirdv2'
    vendor_verified={}
    for p in sources:
        if p.is_relative_to(vendor_prefix):
            name=p.relative_to(vendor_prefix).as_posix()
            expected=vendor_manifest['files'][name]
            if not expected['matches_commit'] or sha(p)!=expected['sha256']:
                raise ValueError('Official E203 source changed: '+name)
            vendor_verified[name]=sha(p)
    for required in ['rtl/e203/subsys/e203_subsys_mems.v','rtl/e203/general/sirv_gnrl_icbs.v']:
        if required not in vendor_verified: raise ValueError('Official fabric source not selected: '+required)
    def snapshot(paths): return {str(p.relative_to(ROOT)):sha(p) for p in paths}
    source_snapshot=snapshot(sources)
    firmware_paths=[candidate/'soc_perf_main.c',candidate/'qingyu_accel.c',candidate/'qingyu_accel.h',ROOT/'sw/startup.S',ROOT/'sw/runtime.c',ROOT/'sw/linker.ld']
    firmware_snapshot=snapshot(firmware_paths)
    runner_snapshot=sha(Path(__file__))
    helper_snapshot=sha(ROOT/'scripts/run_candidate_soc.py')
    unit_snapshot=sha(ROOT/'tb/tb_icb_merge_queue.sv')
    filelist = work/'sources.f'
    filelist.write_text('\n'.join(str(p.relative_to(ROOT)) for p in sources)+'\n')

    # Exercise both deployed queue configurations with an independent target.
    protocol_runs=[]
    for ports,depth,mask in [(6,4,63),(2,4,1)]:
        name=f'merge_p{ports}_d{depth}_m{mask}'
        run(['iverilog','-g2012','-s','tb_icb_merge_queue',
             f'-Ptb_icb_merge_queue.NP={ports}',f'-Ptb_icb_merge_queue.DEPTH={depth}',
             f'-Ptb_icb_merge_queue.MASK={mask}','-o',work/(name+'.vvp'),
             candidate/'qingyu_icb_merge.sv',ROOT/'tb/tb_icb_merge_queue.sv'],work/(name+'_compile.log'))
        for seed in [17,20261111,90210]:
            log=work/(name+f'_{seed}.log')
            run(['vvp',work/(name+'.vvp'),'+SEED='+str(seed)],log)
            if 'PASS queue ' not in log.read_text():
                raise RuntimeError('Queue protocol checker did not pass')
            protocol_runs.append(dict(ports=ports,depth=depth,mask=mask,seed=seed,log=str(log.relative_to(ROOT))))

    obj = work/'obj'
    cmd = ['verilator','--binary','--timing','--autoflush','--timescale-override','1ns/1ps',
           '--top-module','tb_qingyu_bus_profile','--prefix','Vcandidate','--Mdir',obj,
           '-Wno-fatal','-DDISABLE_SV_ASSERTION=1','-j',str(args.jobs),'-CFLAGS','-O1','-f',filelist]
    cmd += ['-Ivendor/e203_hbirdv2/rtl/e203/'+d for d in ['core','perips','perips/apb_i2c']]
    contract = normalized_build_arguments(list(map(str,cmd[1:])),work)
    if args.reuse_build:
        previous = (ROOT/args.reuse_build).resolve()
        prior = json.loads((previous/'result.json').read_text())
        if prior.get('runner_kind') != 'official_fabric_four_row_profile' or prior['candidate'] != args.candidate:
            raise ValueError('Only a matching bus candidate build can be reused')
        def order(lines, directory):
            prefix=str(directory.relative_to(ROOT))+'/'
            return ['<run>/'+n[len(prefix):] if n.startswith(prefix) else n for n in lines if n.strip()]
        if order((previous/'sources.f').read_text().splitlines(),previous) != order(filelist.read_text().splitlines(),work):
            raise ValueError('Compiled source order changed')
        old=prior['sources_sha256']
        for name,value in old.items():
            if sha(ROOT/name)!=value: raise ValueError('Previously compiled source changed: '+name)
        old_stable={n:h for n,h in old.items() if not n.startswith(str(previous.relative_to(ROOT))+'/')}
        current_stable={str(p.relative_to(ROOT)):sha(p) for p in sources if not p.is_relative_to(work)}
        if old_stable != current_stable or sha(previous/'config.v') != sha(config):
            raise ValueError('Compiled source/configuration changed')
        obj=ROOT/prior['simulator_build_directory']/'obj'
        verify_build_arguments(prior,obj.parent,contract)
        if sha(obj/'Vcandidate')!=prior['simulator_sha256']:
            raise ValueError('Simulator binary changed')
        print('Reusing verified bus build: '+str(previous),flush=True)
    else:
        print('Building bus candidate: '+str(work),flush=True)
        run(cmd,work/'build.log',timeout=1200)
    if snapshot(sources)!=source_snapshot: raise ValueError('Source changed during compilation; discard this build and rebuild')
    if sha(ROOT/'tb/tb_icb_merge_queue.sv')!=unit_snapshot: raise ValueError('Unit checker changed during build')
    report={'runner_kind':'official_fabric_four_row_profile','candidate':args.candidate,
        'data_kind':args.data_kind,'passed':False,'clock_hz_assumed':150000000,'layers':[],
        'runner_sha256':runner_snapshot,'helper_sha256':helper_snapshot,
        'source_template_path':str(source_template.relative_to(ROOT)),
        'source_template_sha256':source_template_snapshot,
        'sources_sha256':source_snapshot,
        'verification_contract':verification,
        'verification_contract_sha256':verification_snapshot,
        'vendor_manifest_sha256':sha(vendor_manifest_path),'verified_e203_sources_sha256':vendor_verified,
        'simulator_sha256':sha(obj/'Vcandidate'),'simulator_build_directory':str(obj.parent.relative_to(ROOT)),
        'simulator_build_arguments':contract,
        'simulator_build_arguments_sha256':hashlib.sha256(json.dumps(contract,separators=(',',':')).encode()).hexdigest(),
        'firmware_sha256':firmware_snapshot,
        'merge_protocol_runs':protocol_runs,
        'merge_testbench_sha256':unit_snapshot,
        'limits':['behavioral SRAM, not official PPA','150 MHz is assumed, not STA-proven',
                  'source staging memory initialized by testbench before reset; external source loading is excluded',
                  'measured window retains parameter validation and all staging-to-live cold copies',
                  'selected local model tasks, not organizer 600-sample evaluation']}
    if provenance:
        report.update(images_manifest_sha256=provenance[1],image_source_commit=provenance[0].get('source_commit'),official_600_sample_evaluation=provenance[0].get('official_600_sample_evaluation',False))
        (work/'images_manifest.json').write_text(json.dumps(provenance[0],indent=2))
    result=work/'result.json'
    result.write_text(json.dumps(report,indent=2))
    for layer in range(args.layers):
        if snapshot(firmware_paths)!=firmware_snapshot: raise ValueError('Firmware changed during run')
        case=work/f'layer{layer:02d}';case.mkdir()
        cc=['riscv64-unknown-elf-gcc',f'-DQINGYU_TEST_LAYER={layer}',*['-D'+d for d in DEFINES],
            '-march=rv32imac','-misa-spec=2.2','-mabi=ilp32','-ffreestanding','-fno-builtin','-msmall-data-limit=0',
            '-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-nostdlib','-nostartfiles',
            '-O3','-flto','-funroll-loops','-I'+str(candidate),'-Isw','-Tsw/linker.ld','-Wl,--gc-sections',
            'sw/startup.S',candidate/'soc_perf_main.c',candidate/'qingyu_accel.c','sw/runtime.c','-lgcc','-o',case/'firmware.elf']
        run(cc,case/'compile.log')
        if snapshot(firmware_paths)!=firmware_snapshot: raise ValueError('Firmware changed during compilation')
        run(['riscv64-unknown-elf-objcopy','-O','binary',case/'firmware.elf',case/'firmware.bin'],case/'objcopy.log')
        raw=(case/'firmware.bin').read_bytes()
        if len(raw)>65536: raise ValueError('Firmware exceeds ITCM')
        raw=raw.ljust(65536,b'\0')
        (case/'firmware64.hex').write_text(''.join(f'{int.from_bytes(raw[i:i+8],"little"):016x}\n' for i in range(0,65536,8)))
        if provenance:
            for name in ['shared.hex','expected.hex']: shutil.copy2(args.images/f'layer{layer:02d}'/name,case/name)
        else: synthetic_images(case,args.seed+layer)
        hashes={p.name:sha(p) for p in case.glob('*.hex')}
        if provenance:
            exported=next(r for r in provenance[0]['layers'] if r['layer']==layer)['files']
            if any(hashes[n]!=exported[n] for n in ['shared.hex','expected.hex']): raise ValueError('Image changed during copy')
        run([obj/'Vcandidate','+FIRMWARE=firmware64.hex','+SHARED=shared.hex','+EXPECTED=expected.hex'],case/'simulation.log',cwd=case)
        log=(case/'simulation.log').read_text()
        if 'PASS real E203' not in log or 'PASS official fabric path' not in log:
            raise RuntimeError('Numerical or fabric path checker did not pass: '+str(case))
        metrics={}
        for tag in ['QINGYU_BUS_TASK','QINGYU_BUS_COUNTS','QINGYU_BUS_CLASSES','QINGYU_BUS_DMA','QINGYU_BUS_QUEUE']:
            lines=[line for line in log.splitlines() if line.startswith(tag+' ')]
            if len(lines)!=1: raise RuntimeError('Missing or duplicate '+tag)
            metrics[tag]={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',lines[0])}
        if hashes!={p.name:sha(p) for p in case.glob('*.hex')}: raise RuntimeError('Image changed during execution')
        profile={}
        for line in log.splitlines():
            if line.startswith('PROFILE_'):
                tag=line.split()[0]
                profile.setdefault(tag,[]).append({k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)})
        if not profile.get('PROFILE_SUMMARY'):raise RuntimeError('Missing independent profile')
        if profile['PROFILE_SUMMARY'][0]['elapsed']!=metrics['QINGYU_BUS_TASK']['cycles']:
            raise RuntimeError('Independent profiler and frozen monitor disagree on elapsed cycles')
        phases=profile['PROFILE_PHASE']
        if sum(p['cycles'] for p in phases)!=profile['PROFILE_SUMMARY'][0]['elapsed']:
            raise RuntimeError('Profile phase partition does not cover the measured interval')
        for phase in phases:
            if phase['reads']+phase['writes']+phase['idle']!=phase['cycles']:
                raise RuntimeError('SRAM active/idle partition mismatch')
        profile['interpretation']={
            'interval':'half-open first source validation offer to final originating DMA output ACK',
            'phase_ids':{'0':'validation/setup before first staging command','1':'staging/configuration before first compute busy','2':'accelerator busy (includes stalls)','3':'inactive after first compute; includes intertile control and final drain'},
            'counter_overlap':'CPU control waits, producer stalls and per-port pending counters overlap stage cycles; do not add them as exclusive costs',
            'gap_histogram':'31 includes all gaps of 31 cycles or more',
            'mac_layout':'four rows by sixteen output lanes; only accepted product accumulation cycles counted'}
        row={'profile':profile,'layer':layer,'outputs':25344,'complete_task_cycles':metrics['QINGYU_BUS_TASK']['cycles'],
             'metrics':metrics,'input_sha256':hashes}
        report['layers'].append(row);result.write_text(json.dumps(report,indent=2))
        print(json.dumps(row),flush=True)
    if snapshot(sources)!=source_snapshot or snapshot(firmware_paths)!=firmware_snapshot:
        raise ValueError('Source or firmware changed during run; results not accepted')
    if sha(Path(__file__))!=runner_snapshot or sha(ROOT/'scripts/run_candidate_soc.py')!=helper_snapshot:
        raise ValueError('Runner changed during run; results not accepted')
    if (sha(verification_path) if verification_path.exists() else None)!=verification_snapshot:
        raise ValueError('Verification contract changed during run; results not accepted')
    if sha(ROOT/'tb/tb_icb_merge_queue.sv')!=unit_snapshot:
        raise ValueError('Queue protocol checker changed during run; results not accepted')
    if sha(source_template)!=source_template_snapshot:
        raise ValueError('Source template changed during run; results not accepted')
    report['passed']=True
    report['mean_complete_cycles']=sum(r['complete_task_cycles'] for r in report['layers'])/args.layers
    report['tasks_per_second_at_assumed_150mhz']=150000000/report['mean_complete_cycles']
    result.write_text(json.dumps(report,indent=2))
    print('PASS '+str(result),flush=True)


if __name__=='__main__':main()
