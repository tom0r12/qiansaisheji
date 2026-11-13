"""Windows local E203/Q12 cold task through the original bus and real loader."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
CAND = EXP.parent
WORK = CAND.parents[2]
ROOT = WORK / 'output/github-qiansaisheji/qingyu'
VENDOR = WORK / 'qingyu/vendor/e203_hbirdv2'
VENDOR_ZIP = WORK / 'qingyu/vendor/e203_hbirdv2.zip'
FIXTURES = CAND / 'fixtures/q12_fixtures72.zip'
SOC = EXP / 'soc'
BASE = ROOT / 'experiments/h1500v/opt33_readcache/rtl'
MINGW = WORK / 'qingyu/tools/verilator/mingw64'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text())

def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')

def run(command, logfile, env, cwd=None, timeout=600):
    """Stop only this runner's newly created child tree on interruption."""
    command = [str(x) for x in command]
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    with Path(logfile).open('w') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                 cwd=cwd, env=env, creationflags=flags,
                                 start_new_session=(os.name != 'nt'))
        try:
            rc = child.wait(timeout=timeout)
        except BaseException:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/T', '/F', '/PID', str(child.pid)],
                               stdout=log, stderr=subprocess.STDOUT, check=False)
            else:
                import signal
                try: os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
            child.wait()
            raise
        if rc:
            raise RuntimeError('Command failed (%d): %s\n%s' %
                               (rc, command[0], Path(logfile).read_text(errors='replace')[-6000:]))

def validate_leaf_evidence():
    report = read_json(CAND / 'core/result.json')
    if not report.get('passed'): raise ValueError('core unit result not passing')
    for name in ['q12_task4.sv', 'q12_pair_acc.sv', 'q12_striped_sram.sv']:
        if sha(CAND / 'core' / name) != report['sources'][name]:
            raise ValueError('core source changed: ' + name)
    for name, evidence in [('q12_rice_decoder.sv', 'result.json'),
                           ('q13_rice_encoder.sv', 'encoder_result.json')]:
        r = read_json(CAND / 'codec' / evidence)
        if not r.get('passed') or sha(CAND / 'codec' / name) != r['rtl_sha256']:
            raise ValueError('codec source differs from passing test: ' + name)
    r = read_json(CAND / 'integration/overlap_result.json')
    if not r.get('passed'): raise ValueError('overlap engine result not passing')
    dependencies = r['dependencies_sha256']
    for p in [CAND/'integration/q12_stream_engine_overlap.sv',
              CAND/'integration/q12_rowpair_pack.sv', CAND/'integration/q12_icb_stream_prefix.sv',
              CAND.parent/'q11_candidate/overlap/q11_commit_gate.sv']:
        if sha(p) != dependencies[str(p)]:
            raise ValueError('overlap dependency changed: ' + str(p))
    mmio=read_json(CAND/'soc/mmio_result.json')
    if not mmio.get('passed'):raise ValueError('FIO unit result not passing')
    fio=SOC/'qingyu_q12_stream_fio.sv'
    baseline=CAND/'soc/qingyu_q12_stream_fio.sv'
    if sha(baseline)!=mmio['sources'][str(baseline)] or fio.read_text()!=baseline.read_text():raise ValueError('FIO source differs from unit evidence')
    combined=read_json(SOC/'mmio_result.json')
    if not combined.get('passed'):raise ValueError('Explicit loader FIO/mailbox combination not passed')
    for path,digest in combined['sources'].items():
        if sha(path)!=digest:raise ValueError('Combined FIO tested source changed: '+path)

def prepare_sources(out, loader, mailbox_wait=False, blocking_wait=False, overrides=None):
    validate_leaf_evidence()
    wait_variant = mailbox_wait or blocking_wait
    variant = EXP/'blocking_wait' if blocking_wait else EXP/'mailbox_wait' if mailbox_wait else EXP
    variant_evidence = {}
    if wait_variant:
        for evidence_path in [variant/'unit_result.json',variant/'candidate_record.json']:
            record=read_json(evidence_path)
            if not (record.get('passed') or record.get('prepared')):raise ValueError('Mailbox wait evidence not ready')
            for p,h in record['sources_sha256'].items():
                if sha(p)!=h:raise ValueError('Mailbox wait tested source changed: '+p)
            variant_evidence[str(evidence_path)]=sha(evidence_path)
        origin=read_json(variant/'candidate_record.json').get('baseline_tb')
        if origin and sha(origin['path'])!=origin['sha256']:raise ValueError('Mailbox wait baseline TB changed')
    template = ROOT / 'scripts/fixtures/e203_soc_sources.f'
    generated = out / 'generated'
    generated.mkdir()
    cfg = generated / 'config.v'
    cfg.write_text('`timescale 1ns/1ps\n')
    top_base = EXP/'hardware/qingyu_e203_soc_top.v'
    main_base = EXP/'hardware/qingyu_e203_subsys_main.v'
    subsys_base = EXP/'hardware/qingyu_e203_subsys_top.v'
    top,main = top_base,main_base
    for evidence_path in [EXP/'unit_result.json',SOC/'loader_result.json']:
        evidence=read_json(evidence_path)
        if not evidence.get('passed'):raise ValueError('Explicit loader unit evidence not passed: '+str(evidence_path))
        for p,h in evidence['sources_sha256'].items():
            if sha(p)!=h:raise ValueError('Explicit loader tested source changed: '+p)
    derivation=read_json(EXP/'derivation.json')
    for p,h in derivation['sources'].items():
        if sha(p)!=h:raise ValueError('Hardware derivation source changed: '+p)
    if 'q12_loader_bus_merge' not in main.read_text() or 'q12_chunk_loader_merge_fixture' in main.read_text():
        raise ValueError('Not the explicit hardware master attachment')
    if re.search(r'cpu_cmd|cpu_rsp|`MAIN|\bforce\s', (SOC/'q12_loader_master_bfm.sv').read_text()):
        raise ValueError('External loader must not spy on/substitute CPU outputs')
    replacements = {
        'build/block_config.v': cfg, 'build/timescale.v': None,
        'generated/qingyu_e203_soc_top.v': top,
        'generated/qingyu_e203_subsys_main.v': main,
        'generated/qingyu_e203_subsys_top.v': subsys_base,
        'build/dual_row_study/qingyu_accel.sv': None,
        'rtl/qingyu_fio.sv': SOC/'qingyu_q12_loader_fio.sv',
        'rtl/qingyu_shared_sram.sv': BASE/'qingyu_shared_sram.sv',
        'tb/tb_qingyu_soc.sv': (variant/'soc' if wait_variant else SOC)/'tb_q12soc.sv',
        'tb/tb_qingyu_soc_performance.sv': None}
    sources = []
    for row in template.read_text().splitlines():
        row = row.strip()
        if not row: continue
        if row in replacements: p = replacements[row]
        elif row.startswith('vendor/e203_hbirdv2/'):
            p = VENDOR / row[len('vendor/e203_hbirdv2/'):]
        else: p = ROOT / row
        if p is not None: sources.append(p.resolve())
    sources += [CAND/'integration'/n for n in
                ['q12_stream_engine_overlap.sv','q12_icb_stream_prefix.sv','q12_rowpair_pack.sv']]
    sources += [CAND/'codec'/n for n in ['q12_rice_decoder.sv','q13_rice_encoder.sv']]
    sources += [CAND/'core'/n for n in ['q12_task4.sv','q12_pair_acc.sv','q12_striped_sram.sv']]
    sources += [CAND.parent/'q11_candidate/overlap/q11_commit_gate.sv', BASE/'qingyu_icb_merge.sv',
                SOC/'q12_loader_master_bfm.sv',SOC/'qingyu_q12_stream_fio.sv',
                EXP/'q12_loader_bus_merge.sv',variant/'q12_loader_request.sv']
    override_records=[]
    for name,source,evidence in overrides or []:
        if name=='core':
            source,evidence=source.resolve(),evidence.resolve()
            if not source.is_relative_to(CAND) or not evidence.is_relative_to(CAND) or source==CAND/'core' or not source.is_dir():raise ValueError('Core override requires independent Q12 source directory')
            unit=read_json(evidence)
            core_names=['q12_task4.sv','q12_pair_acc.sv','q12_striped_sram.sv']
            if not unit.get('passed') or len(unit.get('runs',[]))<10 or not all(x.get('passed')for x in unit['runs']):raise ValueError('Core override requires complete whole-core passing miter')
            if unit.get('baseline_evidence_sha256')!=sha(CAND/'core/result.json'):raise ValueError('Core miter baseline evidence changed')
            for filename in core_names:
                canonical=CAND/'core'/filename;candidate=source/filename
                if unit.get('baseline_sources',{}).get(filename)!=sha(canonical) or unit.get('candidate_sources',{}).get(filename)!=sha(candidate):raise ValueError('Core miter source identity mismatch: '+filename)
                if len(re.findall(r'\bmodule\s+'+candidate.stem+r'\b',candidate.read_text()))!=1 or sources.count(canonical)!=1:raise ValueError('Core module identity mismatch: '+filename)
                sources[sources.index(canonical)]=candidate
                override_records.append({'component':'core/'+filename,'original':str(canonical),'original_sha256':sha(canonical),'source':str(candidate),'source_sha256':sha(candidate),'evidence':str(evidence),'evidence_sha256':sha(evidence)})
            continue
        canonical={'decoder':CAND/'codec/q12_rice_decoder.sv','encoder':CAND/'codec/q13_rice_encoder.sv','rowpair':CAND/'integration/q12_rowpair_pack.sv'}[name]
        module=canonical.stem
        source,evidence=source.resolve(),evidence.resolve()
        if not source.is_relative_to(CAND) or not evidence.is_relative_to(CAND) or source==canonical:raise ValueError('Experimental override must be a separate Q12 candidate')
        unit=read_json(evidence)
        digest=unit.get('rtl_sha256',unit.get('candidate_sha256'))
        if not unit.get('passed') or digest!=sha(source) or len(unit.get('runs',[]))!=3 or not all(x.get('passed')for x in unit['runs']):raise ValueError('Override requires matching three-seed passing evidence: '+name)
        if name=='encoder' and unit.get('baseline_sha256')!=sha(canonical):raise ValueError('Encoder override must have original-baseline miter evidence')
        if len(re.findall(r'\bmodule\s+'+module+r'\b',source.read_text()))!=1:raise ValueError('Experimental module identity mismatch')
        if sources.count(canonical)!=1:raise ValueError('Override target absent/duplicate')
        sources[sources.index(canonical)]=source
        override_records.append({'component':name,'original':str(canonical),'original_sha256':sha(canonical),'source':str(source),'source_sha256':sha(source),'evidence':str(evidence),'evidence_sha256':sha(evidence)})
    if len(sources) != len(set(sources)): raise ValueError('duplicate source')
    headers = [VENDOR/'rtl/e203'/s for s in
               ['core/e203_defines.v','core/config.v','perips/apb_i2c/i2c_master_defines.v']]
    verified = {}
    with zipfile.ZipFile(VENDOR_ZIP) as z:
        prefix = 'e203_hbirdv2-9f3e34f337f5d0a1236a285871ffa2032491617a/'
        for p in sources + headers:
            if not p.is_file(): raise FileNotFoundError(p)
            if p.is_relative_to(VENDOR):
                name = p.relative_to(VENDOR).as_posix()
                expected = hashlib.sha256(z.read(prefix+name)).hexdigest()
                if sha(p) != expected: raise ValueError('official archive mismatch: '+name)
                verified[name] = expected
    includes = [VENDOR/'rtl/e203'/s for s in ['core','perips','perips/apb_i2c']]
    (out/'sources.f').write_text('\n'.join(['+incdir+'+s.as_posix() for s in includes]+
                                          [s.as_posix() for s in sources])+'\n')
    def key(p):
        return '<generated>/'+p.name if p.parent == generated else p.relative_to(WORK).as_posix()
    identities = {key(p):sha(p) for p in sources+headers}
    return sources+headers, {'sources_sha256':identities, 'source_order':[key(p) for p in sources],
                            'template_sha256':sha(template), 'official_sources_verified':verified,
                            'vendor_archive_sha256':sha(VENDOR_ZIP),
                            'derived_from':{str(top_base):sha(top_base), str(main_base):sha(main_base),str(subsys_base):sha(subsys_base)},
                            'hardware_external_master':{'NP':3,'OUTSTANDING':4,'ONE_PER_PORT':'000','no_CPU_output_substitution':True},
                            'mailbox_wait':mailbox_wait,'blocking_wait':blocking_wait,'variant_evidence_sha256':variant_evidence,
                            'experimental_overrides':override_records,
                            'unit_evidence_sha256':{str(p):sha(p)for p in [EXP/'unit_result.json',SOC/'loader_result.json',SOC/'mmio_result.json',EXP/'derivation.json']}}

def prepare_firmware(out,loader,record_path=None):
    record_path=record_path.resolve() if record_path else SOC/'firmware_result.json'
    if not record_path.is_relative_to(WORK):raise ValueError('firmware evidence outside workspace')
    record = read_json(record_path)
    if not record.get('compiled'): raise ValueError('firmware not compiled')
    for p, h in record['sources'].items():
        if sha(p) != h: raise ValueError('firmware source changed: '+p)
    firmware = Path(record['firmware_hex'])
    if sha(firmware) != record['firmware_hex_sha256']: raise ValueError('firmware artifact changed')
    shutil.copy2(firmware, out/'firmware64.hex')
    return record

def prepare_packets(out, tasks):
    result = read_json(CAND/'fixtures/result.json')
    engine_evidence = read_json(CAND/'integration/overlap_result.json')
    if not result.get('completed') or not engine_evidence.get('passed') or sha(FIXTURES) != engine_evidence['fixtures_zip_sha256'] or sha(FIXTURES)!=result['fixtures_zip_sha256']:
        raise ValueError('frozen packet archive changed')
    if sha(CAND/'fixtures/plan.json')!=result['plan_sha256']:raise ValueError('fixture plan changed')
    for name,digest in result['config_hashes'].items():
        if sha(CAND/'fixtures/frozen'/name)!=digest:raise ValueError('frozen numeric configuration changed')
    rows = []
    with zipfile.ZipFile(FIXTURES) as z:
        manifest = json.loads(z.read('manifest.json'))
        if manifest.get('format_version')!='q12_x12_w12_y13_h1':raise ValueError('wrong wire/numeric format')
        selection = sorted(manifest['tasks'], key=lambda row: (int(row['task'].split('/sample')[1]), row['task']))[:tasks]
        for row in selection:
            case = out / row['task'].replace('/', '_')
            case.mkdir()
            ip = z.read(row['task']+'/input.bin')
            op = z.read(row['task']+'/expected_output.bin')
            dense = z.read(row['task']+'/expected_dense16.bin')
            if hashlib.sha256(ip).hexdigest()!=row['input_sha256'] or hashlib.sha256(op).hexdigest()!=row['output_sha256'] or hashlib.sha256(dense).hexdigest()!=row['dense_sha256']:
                raise ValueError('fixture hash mismatch')
            if not 330<=len(ip)//4<=8873 or len(ip)//4!=row['input_words'] or len(op)!=10353*4 or len(dense)!=25344*2:
                raise ValueError('fixture dimensions')
            for name, data, width in [('input.hex', ip, 4), ('expected.hex', op, 4), ('dense.hex', dense, 2)]:
                (case/name).write_text(''.join(f'{int.from_bytes(data[i:i+width],"little"):0{width*2}x}\n' for i in range(0,len(data),width)))
            rows.append(dict(row, directory=case.name,
                             files_sha256={n:sha(case/n) for n in ['input.hex','expected.hex','dense.hex']}))
    return rows

def validate_decoded_output(words, case):
    import numpy as np
    sys.path.insert(0, str(CAND/'packing'))
    from packet_io import parse_output
    observed = parse_output(struct.pack('<'+'I'*len(words), *words))
    dense = np.asarray([int(x,16) for x in (case/'dense.hex').read_text().split()],dtype=np.uint16).view(np.int16).reshape(99,256)
    if not np.array_equal(observed,dense):
        raise ValueError('independent 25,344-value decoded output differs')
    return int(observed.size)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks',type=int,default=1)
    parser.add_argument('--jobs',type=int,default=2)
    parser.add_argument('--loader',choices=['explicit'],default='explicit')
    wait_group=parser.add_mutually_exclusive_group()
    wait_group.add_argument('--mailbox-wait',action='store_true',help='Independent tested mailbox status polling RTL/firmware variant')
    wait_group.add_argument('--blocking-wait',action='store_true',help='Independent tested bounded blocking mailbox WAIT RTL/firmware variant')
    for component in ['decoder','encoder','rowpair','core']:
        parser.add_argument('--'+component+'-source',type=Path,help='Explicit independently unit-tested RTL; core uses a directory of three modules')
        parser.add_argument('--'+component+'-evidence',type=Path,help='Passing three-seed source-bound evidence JSON')
    parser.add_argument('--firmware-record',type=Path,help='Explicit new compiled firmware evidence; HDL build reuse remains source-hash checked')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--lint-only',action='store_true')
    parser.add_argument('--reuse-build',type=Path)
    a=parser.parse_args()
    if not 1<=a.tasks<=72 or not 1<=a.jobs<=8: parser.error('tasks 1..72, jobs 1..8')
    if (a.mailbox_wait or a.blocking_wait) and a.firmware_record:parser.error('Wait variants have exact frozen firmware; do not override')
    overrides=[]
    for component in ['decoder','encoder','rowpair','core']:
        source=getattr(a,component+'_source');evidence=getattr(a,component+'_evidence')
        if bool(source)!=bool(evidence):parser.error('Both '+component+' source and evidence are required')
        if source:overrides.append((component,source,evidence))
    out=HERE/'runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True)
    shutil.copy2(__file__,out/'runner_snapshot.py')
    report={'passed':False,'phase':'prepare','scope':'Real E203 Q12 cold task with explicit independent loader ICB master, real mailbox, original System Bus and frozen custom shared-SRAM controller',
            'limits':['Historical frozen Q12 fixtures; not current official accuracy dataset',
                      'Behavioral synchronous SRAM, no manufacturer macro timing or power',
                      '150 MHz is assumed; no STA signoff',
                      'Each task launches a separate simulation with global reset; not an uninterrupted encoder chain',
                      'External loader input boundary is explicit hardware, but organizer acceptance of the added platform interface remains pending'],
            'measurement':{'start':'earliest task control/source command offer','end':'actual final output completion marker response ACK',
                           'includes':'source loading, CPU control, all arbitration/waits/compute/output writes',
                           'excludes':'host file read and format conversion; firmware preload/boot'},
            'runner_sha256':sha(__file__),'loader':a.loader,'mailbox_wait':a.mailbox_wait,'blocking_wait':a.blocking_wait,'commands':[],'tasks':[]}
    def save(): save_json(out/'result.json',report)
    save();print('Q12_SOC_RUN='+str(out),flush=True)
    env=dict(os.environ)
    env['PATH']=str(MINGW/'bin')+os.pathsep+'D:/Git/usr/bin;D:/Git/bin;'+env['PATH']
    env['VERILATOR_ROOT']=str(MINGW/'share/verilator')
    try:
        source_paths,identity=prepare_sources(out,a.loader,a.mailbox_wait,a.blocking_wait,overrides)
        fw_record=EXP/'blocking_wait/soc/firmware_result.json' if a.blocking_wait else EXP/'mailbox_wait/soc/firmware_result.json' if a.mailbox_wait else a.firmware_record
        firmware=prepare_firmware(out,a.loader,fw_record)
        packets=prepare_packets(out,a.tasks)
        report.update(source_identity=identity,firmware_record=firmware,packets=packets,
                      fixtures_zip_sha256=sha(FIXTURES))
        if a.firmware_record:report['firmware_record_override']={'path':str(a.firmware_record.resolve()),'sha256':sha(a.firmware_record)}
        save()
        if a.prepare_only:
            report['phase']='prepared';save();return
        verilator=MINGW/'bin/verilator_bin.exe'
        make=Path('D:/mingw/mingw64/bin/mingw32-make.exe')
        tool_identity={str(p):sha(p) for p in [verilator,make,MINGW/'bin/g++.exe']}
        report['tool_identity']=tool_identity
        build=out/'vbuild'
        top='tb_q12soc'
        common=['--timing','--autoflush','--timescale-override','1ns/1ps','-Wno-fatal',
                '-DDISABLE_SV_ASSERTION=1','--top-module',top,'--prefix','Vq12soc']
        if a.lint_only:
            command=[verilator,'--lint-only',*common,'-f',out/'sources.f']
            report['commands'].append([str(x) for x in command]);save()
            run(command,out/'lint.log',env,timeout=180)
            report.update(phase='lint_passed');save();return
        build_contract={'verilator_arguments':common,'make_flags':['CXX=g++','LINK=g++',
                        'CFG_CXXFLAGS_STD=-std=gnu++20','OPT_GLOBAL=-Os -fno-declone-ctor-dtor']}
        report['build_contract']=build_contract
        if a.reuse_build:
            prior_dir=a.reuse_build.resolve();prior=read_json(prior_dir/'result.json')
            if not prior.get('passed') or prior.get('phase')!='complete':raise ValueError('Only successful prior explicit-loader binary may be reused')
            if prior.get('source_identity')!=identity or prior.get('tool_identity')!=tool_identity or prior.get('build_contract')!=build_contract:
                raise ValueError('reuse source/tool/compiler identity mismatch')
            executable=Path(prior['executable'])
            if sha(executable)!=prior['executable_sha256']:raise ValueError('reuse binary changed')
            for p,h in prior['runtime_sha256'].items():
                if sha(p)!=h:raise ValueError('reuse runtime changed')
            report['reused_build']=str(prior_dir)
            report['runtime_sha256']=prior['runtime_sha256']
        else:
            commands=[[verilator,'--cc','--main','--exe',*common,'--Mdir',build,'-f',out/'sources.f'],
                      [make,'-C',build,'-f','Vq12soc.mk','-j'+str(a.jobs),'SHELL=D:/Git/bin/sh.exe',*build_contract['make_flags']]]
            report['phase']='build'
            for n,command in enumerate(commands):
                report['commands'].append([str(x) for x in command]);save()
                run(command,out/f'build_{n}.log',env,timeout=1200)
            executable=build/'Vq12soc.exe';report['runtime_sha256']={}
            for name in ['libgcc_s_seh-1.dll','libstdc++-6.dll','libwinpthread-1.dll']:
                shutil.copy2(MINGW/'bin'/name,build/name)
                report['runtime_sha256'][str(build/name)]=sha(build/name)
        report.update(executable=str(executable),executable_sha256=sha(executable),phase='simulation');save()
        for row in packets:
            case=out/row['directory']
            # Relative plusarg paths avoid 1024-bit SV string truncation at long Windows paths.
            command=[executable,'+FIRMWARE=../firmware64.hex','+INPUT=input.hex','+EXPECTED=expected.hex',
                     '+OUTPUT_DUMP=observed.hex','+INPUT_WORDS='+str(row['input_words']),
                     '+OUTPUT_WORDS='+str(row['output_actual_write_words']),'+LAYER='+row['task'][5:7]]
            report['commands'].append([str(x) for x in command]);save()
            run(command,case/'simulation.log',env,cwd=case,timeout=600)
            text=(case/'simulation.log').read_text()
            metrics=re.findall(r'^Q12SOC_METRICS (.+)$',text,re.M)
            if len(metrics)!=1 or len(re.findall(r'^PASS real E203 Q12 cold task; explicit independent loader and original System Bus;',text,re.M))!=1:
                raise ValueError('missing unique full-window success')
            def words(path): return [int(x,16) for x in re.sub(r'//[^\n]*','',path.read_text()).split()]
            observed=words(case/'observed.hex')
            if observed!=words(case/'expected.hex'):
                raise ValueError('independent full physical output readback differs')
            values_checked=validate_decoded_output(observed,case)
            parsed={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',metrics[0])}
            if parsed['reads']!=row['input_words'] or parsed['writes']!=row['output_actual_write_words'] or parsed['full_window_cycles']<=parsed['start_to_ack']:
                raise ValueError('invalid conservation or full-window metric')
            explicit_rows=re.findall(r'^Q12_EXPLICIT_LOADER (.+)$',text,re.M)
            if len(explicit_rows)!=1:raise ValueError('Missing independent loader/master evidence')
            explicit={k:int(v)for k,v in re.findall(r'(\w+)=(-?\d+)',explicit_rows[0])}
            mailbox_status=None
            if a.mailbox_wait or a.blocking_wait:
                status_tag='Q12_MAILBOX_WAIT' if a.blocking_wait else 'Q12_MAILBOX_STATUS'
                status_rows=re.findall(r'^'+status_tag+r' (.+)$',text,re.M)
                if len(status_rows)!=1:raise ValueError('Missing mailbox read/write accounting')
                mailbox_status={k:int(v)for k,v in re.findall(r'(\w+)=(-?\d+)',status_rows[0])}
                if a.blocking_wait:
                    if mailbox_status!={'writes':10,'reads':9,'commands':19,'responses':19,'timeouts':0}:raise ValueError('Invalid bounded WAIT/control/ACK accounting')
                elif set(mailbox_status)!={'writes','reads','commands','responses'} or mailbox_status['writes']!=10 or mailbox_status['reads']<9 or mailbox_status['commands']!=mailbox_status['reads']+10 or mailbox_status['responses']!=mailbox_status['commands']:
                    raise ValueError('Invalid mailbox STATUS/control/ACK conservation')
                commands=mailbox_status['commands']
            else:commands=10
            if explicit!={'masters':3,'requests':9,'mailbox_commands':commands,'mailbox_responses':commands,'independent_cpu':1}:raise ValueError('Invalid explicit loader/mailbox accounting')
            if parsed['loader_commands']!=row['input_words']+45:raise ValueError('Loader payload/control conservation differs')
            if re.search(r'^Fatal:|^Error-|\$fatal',text,re.M):raise ValueError('Simulator fatal found')
            task_report={'task':row['task'],'metrics':parsed,'explicit_loader':explicit,'log_sha256':sha(case/'simulation.log'),
                         'output_dump_sha256':sha(case/'observed.hex'),'decoded_values_checked':values_checked}
            if mailbox_status is not None:task_report['mailbox_status']=mailbox_status
            phases=re.findall(r'^Q12SOC_PHASES (.+)$',text,re.M)
            if len(phases)>1:raise ValueError('ambiguous stage metrics')
            if phases:task_report['phases']={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',phases[0])}
            if not phases:raise ValueError('missing phase metrics')
            for tag in ['Q12_PROFILE_BUS','Q12_PROFILE_CORE','Q12_PROFILE_EMPTY']:
                profile=re.findall(r'^'+tag+r' (.+)$',text,re.M)
                if len(profile)!=1:raise ValueError('missing/duplicate '+tag)
                task_report[tag]={k:int(v)for k,v in re.findall(r'(\w+)=(-?\d+)',profile[0])}
            report['tasks'].append(task_report)
            save();print('Q12_SOC_TASK '+json.dumps(report['tasks'][-1]),flush=True)
        # Mutations during compile/simulation invalidate this evidence.
        for p in source_paths:
            key='<generated>/'+p.name if p.parent==out/'generated' else p.relative_to(WORK).as_posix()
            if sha(p)!=identity['sources_sha256'][key]:raise ValueError('source changed during run: '+str(p))
        for p,h in firmware['sources'].items():
            if sha(p)!=h:raise ValueError('firmware source changed during run')
        for record in identity['experimental_overrides']:
            if sha(record['source'])!=record['source_sha256'] or sha(record['evidence'])!=record['evidence_sha256']:raise ValueError('Experimental override changed during run')
        total=sum(t['metrics']['full_window_cycles'] for t in report['tasks'])
        report.update(passed=True,phase='complete',mean_full_window_cycles=total/len(packets),
                      throughput_tasks_s_at_assumed_150mhz=150000000*len(packets)/total,
                      mean_full_window_ms_at_assumed_150mhz=total/len(packets)/150000)
        save();print('PASS Q12_SOC_FULL_WINDOW '+str(out/'result.json'),flush=True)
    except BaseException as error:
        report.update(phase='failed',failure=str(error));save();raise

if __name__=='__main__': main()
