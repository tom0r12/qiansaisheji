"""Prepare an isolated official-bus verification/assessment bundle; never upload."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = Path(__file__).parent/'server_bus_bundle'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding='utf-8', newline='\n')


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unexpected fixture structure: '+old)
    return text.replace(old, new)


CHECKERS = {
    'official_fabric_queued_single_port': {
        'source':'tb/tb_qingyu_bus_queue_performance.sv',
        'top':'tb_qingyu_bus_queue_performance','extra_metrics':[]},
    'official_fabric_zeroack_single_port': {
        'source':'tb/tb_qingyu_bus_zeroack_performance.sv',
        'top':'tb_qingyu_bus_zeroack_performance','extra_metrics':[]},
    'official_fabric_zeroack_outputqueue': {
        'source':'tb/tb_qingyu_bus_outputqueue_performance.sv',
        'top':'tb_qingyu_bus_outputqueue_performance',
        'extra_metrics':['QINGYU_OUTPUT_QUEUE']},
    'official_fabric_readcache_outputqueue': {
        'source':'tb/tb_qingyu_bus_readcache_performance.sv',
        'top':'tb_qingyu_bus_readcache_performance',
        'extra_metrics':['QINGYU_OUTPUT_QUEUE','QINGYU_READCACHE']},
}
SUPPORTED_CANDIDATES = {'opt28_queuewait4','opt30_fusedpipe4','opt31_fastwrite','opt32_outputqueue','opt33_readcache'}


def fixtures(bundle, checker):
    behavior=(ROOT/'tb/tb_qingyu_bus_soc.sv').read_text()
    behavior=replace_once(behavior,' integer i, mismatches=0, cycles=0;',
                          ' reg [31:0] shared_image[0:131071];\n reg assessment_done=0, runtime_enabled=1;\n integer i, mismatches=0, cycles=0;')
    behavior=replace_once(behavior,'  $readmemh(shared_path,dut.u_shared.mem);',
                          '  $readmemh(shared_path,dut.u_shared.mem);\n  $readmemh(shared_path,shared_image);')
    behavior=replace_once(behavior,'  if(host_valid) begin','  if(host_valid) begin\n   assessment_done=1;')
    put(bundle/'common/tb_behavior.sv',behavior)
    physical=(TEMPLATES/'fixtures/tb_macro.sv').read_text()
    if checker['top']=='tb_qingyu_bus_readcache_performance':
        # The CPU/AON clock domains have not yet observed boot reset while
        # the simulation-only physical loader is active. Its MMIO reset decode
        # must not inject X into cache_clear during that preload/readback.
        # Both forces are released before the CPU runtime measurement begins.
        physical=replace_once(physical,'   force `SHARED.clk=clk;',
                              '   force `SHARED.cache_clear=1\'b0;\n   force `SHARED.clk=clk;')
        physical=replace_once(physical,'   release `SHARED.rst_n; release `SHARED.clk;',
                              '   release `SHARED.cache_clear;\n   release `SHARED.rst_n; release `SHARED.clk;')
    put(bundle/'common/tb_macro.sv',physical)
    monitor=(ROOT/checker['source']).read_text()
    monitor=monitor.replace('`MEM.mem[','fixture.shared_image[')
    monitor=replace_once(monitor, 'if(!`DUT.qingyu_bus_rst_n) begin', 'if(!`DUT.qingyu_bus_rst_n || !fixture.runtime_enabled) begin')
    monitor=replace_once(monitor,' integer ticks=0,', ''' reg dump_enabled=0;
 reg [2047:0] activity_path;
 initial begin
  if($value$plusargs("ACTIVITY=%s",activity_path)) begin
   dump_enabled=1;$dumpfile(activity_path);$dumpvars(0,fixture.dut);$dumpoff;
  end
 end
 integer ticks=0,''')
    monitor=replace_once(monitor,'  end else begin\n   // Include arbitration',
                          '  end else if(!fixture.assessment_done) begin\n   // Include arbitration')
    monitor=replace_once(monitor,'source_data(`MERGE.s_cmd_addr[32*p+:32])) task_start=ticks;',
                          '''source_data(`MERGE.s_cmd_addr[32*p+:32])) begin
     task_start=ticks;
     $display("QINGYU_ACTIVITY_START cycle=%0d time_ps=%0t",ticks,$realtime);
     if(dump_enabled)$dumpon;
    end''')
    monitor=replace_once(monitor,'       task_end=ticks;', '''       task_end=ticks;
       if(dump_enabled)$dumpoff;
       $display("QINGYU_ACTIVITY_END cycle=%0d time_ps=%0t",ticks,$realtime);''')
    put(bundle/'common/monitor.sv',monitor)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True)
    parser.add_argument('--run',required=True,type=Path,help='Passed twelve-layer official queued-bus run')
    parser.add_argument('--images',required=True,type=Path)
    parser.add_argument('--provenance',required=True,type=Path,action='append')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not re.fullmatch(r'opt[0-9]+_[a-z0-9_]+',args.candidate):parser.error('Invalid candidate name')
    candidate=ROOT/'experiments/h1500v'/args.candidate
    report=json.loads((args.run/'result.json').read_text())
    if args.candidate not in SUPPORTED_CANDIDATES:
        raise ValueError('Candidate needs an independently reviewed physical fixture')
    if not report.get('passed') or report.get('runner_kind') not in CHECKERS or report['candidate']!=args.candidate:
        raise ValueError('Run does not validate the requested official-bus candidate')
    checker=CHECKERS[report['runner_kind']]
    if report['sources_sha256'].get(checker['source'])!=sha(ROOT/checker['source']):
        raise ValueError('Passed run does not bind the selected independent scoreboard')
    if sorted(x['layer'] for x in report['layers'])!=list(range(12)):raise ValueError('Twelve passed layers required')
    for table in ['sources_sha256','firmware_sha256']:
        for name,digest in report[table].items():
            if sha(ROOT/name)!=digest:raise ValueError('Validated source changed: '+name)
    frozen=json.loads((candidate/'SOURCE_SHA256.json').read_text())
    for name,digest in frozen['files'].items():
        if sha(candidate/name)!=digest:raise ValueError('Frozen candidate changed: '+name)
    image_manifest=json.loads((args.images/'images_manifest.json').read_text())
    if sha(args.images/'images_manifest.json')!=report['images_manifest_sha256']:raise ValueError('Wrong image provenance')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output=(args.output or ROOT/'build/bus_server_bundles'/(stamp+'_'+args.candidate)).resolve()
    output.mkdir(parents=True,exist_ok=False)
    bundle=output/'qingyu_bus_bundle';bundle.mkdir()
    manifest=dict(schema='qingyu-official-bus-bundle-v2',candidate=args.candidate,created_utc=stamp,
                  packager_sha256=sha(Path(__file__)),runner_kind=report['runner_kind'],
                  checker={**checker,'validated_source_sha256':sha(ROOT/checker['source']),
                           'fatal_checks':(ROOT/checker['source']).read_text().count('$fatal')},
                  local_result_sha256=sha(args.run/'result.json'),
                  candidate_manifest_sha256=sha(candidate/'SOURCE_SHA256.json'),
                  data_kind=report['data_kind'],official_600_sample_evaluation=False,
                  measured_window='first CPU/source read attempt through final originating output response',
                  excluded_window='testbench staging/ITCM preload and boot before first parameter read',
                  official_loading_window_status='pending organizer loader integration; engineering measurements only',
                  ppa_status='prepared only; no remote execution or PPA acceptance',
                  required_stdcell_family='SCC40NLL_VHSC40_RVT_V0p1',files_sha256={})
    if report['runner_kind']=='official_fabric_readcache_outputqueue':
        manifest['shared_response_semantics']={
            'write_commit':'Exactly once on accepted command edge; if response ready is low, retain the response and accept no next command until retirement.',
            'inherited_contract_erratum':'The inherited opt31 sentence Backpressure must prevent both acceptance and mutation does not describe opt33. The accepted-write/held-response behavior above is the verified opt33 contract.',
            'power':'Include every speculative macro read and all cache/control logic; no energy benefit is assumed.'}
    copy(candidate/'SOURCE_SHA256.json',bundle/'candidate/SOURCE_SHA256.json')
    for name in frozen['files']:
        p=(candidate/name).resolve()
        if not p.is_relative_to(candidate.resolve()):raise ValueError('Candidate manifest escapes its source directory')
        copy(p,bundle/'candidate'/name)
    for p in sorted(TEMPLATES.rglob('*')):
        if p.is_file() and p.suffix not in ['.pyc'] and 'fixtures' not in p.relative_to(TEMPLATES).parts:
            copy(p,bundle/p.relative_to(TEMPLATES))
    fixtures(bundle,checker)
    # Copy exactly the validated compilation inputs, then replace only memory
    # wrappers and fixture variants. Both official fabric source files stay intact.
    behavior=[]
    for name in (args.run/'sources.f').read_text().splitlines():
        p=ROOT/name
        if p.resolve()==(args.run/'config.v').resolve():target='common/config.v'
        elif p.is_relative_to(candidate/'rtl'):target='candidate/rtl/'+p.relative_to(candidate/'rtl').as_posix()
        elif name=='tb/tb_qingyu_bus_soc.sv':target='common/tb_behavior.sv'
        elif name==checker['source']:target='common/monitor.sv'
        else:target=name
        if target not in ['common/tb_behavior.sv','common/monitor.sv']:copy(p,bundle/target)
        behavior.append(target)
    vendor=ROOT/'vendor/e203_hbirdv2'
    pinned_path=ROOT/'reports/e203-source-manifest.json'
    pinned=json.loads(pinned_path.read_text())
    if not pinned.get('ready') or pinned.get('commit')!='9f3e34f337f5d0a1236a285871ffa2032491617a':raise ValueError('Official E203 pinned-source manifest is not ready')
    for p in (vendor/'rtl').rglob('*'):
        if p.is_file() and p.suffix in ['.v','.sv','.vh','.svh']:
            entry=pinned['files'].get(p.relative_to(vendor).as_posix())
            if not entry or not entry['matches_commit'] or sha(p)!=entry['sha256']:raise ValueError('Official vendor source/header differs: '+str(p))
            copy(p,bundle/'vendor/e203_hbirdv2'/p.relative_to(vendor))
    if sha(vendor/'LICENSE')!=pinned['files']['LICENSE']['sha256']:raise ValueError('Pinned LICENSE differs')
    copy(vendor/'LICENSE',bundle/'vendor/e203_hbirdv2/LICENSE')
    public_pinned={k:v for k,v in pinned.items() if k!='reference'}
    public_pinned['original_inventory_sha256']=sha(pinned_path)
    public_pinned['reference']='official riscv-mcu/e203_hbirdv2 commit '+pinned['commit']
    put(bundle/'evidence/e203-source-manifest.json',json.dumps(public_pinned,indent=2)+'\n')
    for filename in ['qingyu_banked_sram.sv','qingyu_sram16.sv','sirv_gnrl_ram.v']:
        copy(ROOT/'rtl/asic'/filename,bundle/'rtl/asic'/filename)
    remove={'rtl/qingyu_sram16.sv','vendor/e203_hbirdv2/rtl/e203/general/sirv_gnrl_ram.v',
            'vendor/e203_hbirdv2/rtl/e203/general/sirv_sim_ram.v','candidate/rtl/qingyu_shared_sram.sv'}
    macro=[x.replace('common/tb_behavior.sv','common/tb_macro.sv') for x in behavior if x not in remove]
    macro+=['rtl/asic/qingyu_banked_sram.sv','rtl/asic/qingyu_sram16.sv','rtl/asic/sirv_gnrl_ram.v','candidate/rtl/asic/qingyu_shared_sram.sv']
    synth=[x for x in macro if x not in ['common/config.v','common/tb_macro.sv','common/monitor.sv']]
    for mode,lines in [('behavioral',behavior),('macro',macro),('soc_synth',synth)]:
        put(bundle/('filelists/'+mode+'.f'),'\n'.join(lines)+'\n')
    put(bundle/'common/synth_defines.v','`define DISABLE_SV_ASSERTION 1\n'+(bundle/'common/config.v').read_text())
    accel=(candidate/'rtl/qingyu_accel.sv').read_text()
    xrows=int(re.search(r'for\s*\(g=0;\s*g<(\d+);\s*g=g\+1\) begin: g_x',accel)[1])
    ybanks=int(re.search(r'localparam Y_BANKS = (\d+);',accel)[1])
    manifest['expected_macros']={'private128':32+ybanks+1,'private1024':2*xrows,'shared4096':64,'cpu4096':16}
    put(bundle/'assessment_expected.tcl','\n'.join('set EXPECTED_'+key.upper()+' '+str(value) for key,value in manifest['expected_macros'].items())+'\n')
    copy(args.run/'result.json',bundle/'evidence/local_run.json')
    copy(args.images/'images_manifest.json',bundle/'images/images_manifest.json')
    for i,path in enumerate(args.provenance):
        if not isinstance(json.loads(path.read_text(encoding='utf-8-sig')),dict):raise ValueError('Provenance must be JSON object')
        copy(path,bundle/f'provenance/{i}_{path.name}')
    for row in report['layers']:
        layer=f"layer{row['layer']:02d}"
        for name in ['firmware64.hex','shared.hex','expected.hex']:
            source=args.run/layer/name if name=='firmware64.hex' else args.images/layer/name
            if sha(source)!=row['input_sha256'][name]:raise ValueError('Validated image changed: '+str(source))
            copy(source,bundle/layer/name)
    # Verify every unchanged behavioral input still matches the tested build.
    manifest['packaged_behavioral_inputs_sha256']={x:sha(bundle/x) for x in behavior}
    manifest['physical_fixture_sha256']=sha(bundle/'common/tb_macro.sv')
    manifest['monitor_generated_sha256']=sha(bundle/'common/monitor.sv')
    put(bundle/'verify.sh','#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\nexec python3 run_bus_server.py "$@"\n')
    for path in sorted(bundle.rglob('*')):
        if path.is_file():manifest['files_sha256'][path.relative_to(bundle).as_posix()]=sha(path)
    if (bundle/'common/monitor.sv').read_text().count('$fatal')!=manifest['checker']['fatal_checks']:
        raise ValueError('A validated scoreboard check was lost during adaptation')
    put(bundle/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    archive=output/'qingyu_bus_bundle.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(bundle.rglob('*')):
            if p.is_file():z.write(p,'qingyu_bus_bundle/'+p.relative_to(bundle).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise RuntimeError('Archive CRC failed')
    put(output/'qingyu_bus_bundle.zip.sha256',sha(archive)+'  qingyu_bus_bundle.zip\n')
    print(archive);print('SHA256='+sha(archive))


if __name__=='__main__':main()
