"""Local immutable-package, syntax and accounting checks; no proprietary EDA."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tkinter
import zipfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path)
    args=parser.parse_args();bundle=args.bundle.resolve()
    report=dict(passed=False,scope='Local package/syntax/area-boundary checks only; no EDA results',checks=[])
    def passed(name):report['checks'].append(name)
    manifest=json.loads((bundle/'manifest.json').read_text())
    actual={p.relative_to(bundle).as_posix() for p in bundle.rglob('*') if p.is_file()}
    if actual!=set(manifest['files_sha256'])|{'manifest.json'}:raise ValueError('Unlisted/missing bundle files')
    for name,h in manifest['files_sha256'].items():
        if not (bundle/name).resolve().is_relative_to(bundle):raise ValueError('Manifest path escapes bundle')
        if hashlib.sha256((bundle/name).read_bytes()).hexdigest()!=h:raise ValueError('Changed file '+name)
    passed('all manifest hashes')
    candidate=json.loads((bundle/'candidate/SOURCE_SHA256.json').read_text())
    for name,h in candidate['files'].items():
        if hashlib.sha256((bundle/'candidate'/name).read_bytes()).hexdigest()!=h:raise ValueError('Candidate snapshot changed '+name)
    passed('complete embedded candidate source manifest')
    with zipfile.ZipFile(bundle.parent/'qingyu_bus_bundle.zip') as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC')
    passed('ZIP CRC')
    for p in bundle.rglob('*.py'):ast.parse(p.read_text(),filename=str(p))
    passed('Python syntax')
    tcl=tkinter.Tcl()
    for p in bundle.rglob('*.tcl'):
        if not int(tcl.call('info','complete',p.read_text())):raise ValueError('Incomplete Tcl '+str(p))
    passed('Tcl complete-script syntax; vendor commands not executed')
    common=(bundle/'assessment/common.tcl').read_text()
    subset=common[common.index('set fixed_cpu_prefix'):common.index('proc memory_audit')]
    tcl.eval(subset)
    examples={
        ('u_fio/u_accel/g_x_0/ram0/macro_ram','RAMSP1024X16'):'included_private_macro',
        ('u_fio/guard/DFF0','DFF'):'included_fio_accelerator_logic',
        ('u_dma_merge/owner_fifo_0','DFF'):'included_new_bus_merges',
        ('u_e203_subsys_top/u_e203_subsys_main/u_mem_merge/count_q','DFF'):'included_new_bus_merges',
        ('u_shared/u_storage/banks_0/slices_0/macro_ram','RAMSP4096X16'):'excluded_fixed_shared_macro',
        ('u_shared/response_read_reg','DFF'):'included_shared_interface_logic',
        ('u_shared/read_pending_reg','DFF'):'included_shared_interface_logic',
        ('u_shared/ack_gate','AND2'):'included_shared_interface_logic',
        ('u_shared/u_cache/cache_data_reg_0','DFF'):'included_shared_interface_logic',
        ('u_e203_subsys_top/u_e203_subsys_main/u_e203_cpu_top/u_core/DFF0','DFF'):'excluded_reused_cpu_logic',
        ('u_e203_subsys_top/u_e203_subsys_main/u_e203_cpu_top/u_srams/ram','RAMSP4096X16'):'excluded_cpu_tcm_macro',
        ('u_e203_subsys_top/u_e203_subsys_main/u_e203_subsys_mems/u_fab/DFF0','DFF'):'excluded_fixed_bus_peripheral_logic',
        ('u_e203_subsys_top/u_e203_subsys_main/new_glue','DFF'):'included_adapter_or_boundary_logic',
    }
    for (path,ref),expected in examples.items():
        if tcl.call('area_class',path,ref)!=expected:raise ValueError('Area classification '+path)
    passed('thirteen accounting cases; both merges, protocol and read-cache logic counted')
    for key,value in {'QINGYU_BUNDLE':bundle,'QINGYU_WORK':bundle.parent,
                      'QINGYU_PLATFORM_CONFIG':bundle/'platform_config.example.tcl',
                      'QINGYU_BUNDLE_SHA256':'local-syntax-check'}.items():tcl.setvar('env('+key+')',str(value))
    try:tcl.call('source',str(bundle/'assessment/common.tcl'))
    except tkinter.TclError as error:
        if 'Configuration must explicitly define STD_CELL_LIBS' not in str(error):raise
    else:raise ValueError('Unconfigured assessment did not stop')
    passed('unconfigured assessment fails before any vendor EDA command')
    monitor=(bundle/'common/monitor.sv').read_text()
    checker=manifest['checker']
    local=json.loads((bundle/'evidence/local_run.json').read_text())
    if local['runner_kind']!=manifest['runner_kind'] or local['sources_sha256'].get(checker['source'])!=checker['validated_source_sha256']:
        raise ValueError('Wrong validated scoreboard selected')
    if 'module '+checker['top']+';' not in monitor or monitor.count('$fatal')!=checker['fatal_checks']:
        raise ValueError('Scoreboard module/check inventory changed')
    if '`MEM.mem[' in monitor or monitor.count('$dumpon')!=1 or monitor.count('$dumpoff')!=2:raise ValueError('Monitor reference/activity window')
    if 'task_end=ticks;\n       if(dump_enabled)$dumpoff;' not in monitor:raise ValueError('Dump does not end at originating DMA ACK')
    if '!fixture.runtime_enabled' not in monitor:raise ValueError('Preload forces are visible to the runtime scoreboard')
    if manifest['runner_kind'] in ['official_fabric_zeroack_outputqueue','official_fabric_readcache_outputqueue']:
        if 'output_returned==12671' not in monitor or 'd_count[p]' not in monitor:raise ValueError('Multi-outstanding output retirement not checked')
    if manifest['runner_kind'].startswith('official_fabric_zeroack') or manifest['runner_kind']=='official_fabric_readcache_outputqueue':
        if monitor.index('if(`MEM.icb_cmd_valid&&`MEM.icb_cmd_ready)')>monitor.index('if(`MEM.icb_rsp_valid&&`MEM.icb_rsp_ready)'):
            raise ValueError('Zero-cycle response checked before its accepted command')
    if manifest['runner_kind']=='official_fabric_readcache_outputqueue':
        for expected in ['cache_clears==0','cache_hits+cache_misses','cache_ram_reads',
                         'cache_ram_writes','cache_prefetch_reads','QINGYU_READCACHE']:
            if expected not in monitor:raise ValueError('Missing read-cache accounting: '+expected)
        if 'QINGYU_READCACHE' not in checker['extra_metrics']:
            raise ValueError('Server runner would omit actual read-cache RAM activity')
    physical=(bundle/'common/tb_macro.sv').read_text()
    if manifest['runner_kind']=='official_fabric_readcache_outputqueue' and 'same-edge readback error or unknown' not in physical:
        raise ValueError('Physical readback misses zero-cycle cached responses')
    if manifest['runner_kind']=='official_fabric_readcache_outputqueue':
        if "force `SHARED.cache_clear=1'b0;" not in physical or 'release `SHARED.cache_clear;' not in physical:
            raise ValueError('Physical preload reset decode is not isolated and released')
    for required in ['shared_reset=0','repeat(4)@(negedge clk)','preload_commands!=131072||preload_responses!=131072',
                     'preload_shared_word();','runtime_enabled=1;rst_n=1;','read_shared_word(17\'(16384+j),readback_data)']:
        if required not in physical:raise ValueError('Physical fixture missing '+required)
    passed('immutable expected-data references and common timing/activity markers')
    for mode in ['behavioral','macro','soc_synth']:
        lines=(bundle/'filelists'/(mode+'.f')).read_text().splitlines()
        if any('shared_sram_mp' in x or 'score_top' in x for x in lines):raise ValueError('Obsolete bypass boundary')
        for name in lines:
            if not (bundle/name).is_file():raise ValueError('Missing filelist input '+name)
        for required in ['candidate/rtl/qingyu_icb_merge.sv','candidate/rtl/qingyu_e203_soc_top.v',
                         'vendor/e203_hbirdv2/rtl/e203/subsys/e203_subsys_mems.v']:
            if required not in lines:raise ValueError('Official bus input missing '+required)
    passed('all filelist inputs exist; original official fabric and new merges selected; no MP wrapper')
    for p in bundle.rglob('*'):
        if not p.is_file() or p.suffix not in ['.py','.md','.tcl','.sh','.json','.sv','.v','.txt']:continue
        lower=p.read_text(errors='replace').lower()
        if any(x in lower for x in ['chatgpt','openai','codex','ai-generated']):raise ValueError('Unexpected tool attribution '+str(p))
        if p.name.upper()=='AGENTS.MD' or '/users/' in lower or '\\users\\' in lower:
            raise ValueError('Unexpected local instruction/user path '+str(p))
    passed('neutral names in owned scripts and instructions')
    if 'official_manufacturer' not in (bundle/'run_bus_server.py').read_text():raise ValueError('No reviewed external macro identity gate')
    passed('manufacturer macro identity required; no bundled substitute model')
    subprocess.run([sys.executable,str(bundle/'run_bus_server.py'),'--mode','validate'],check=True)
    report['passed']=True
    (bundle.parent/'local_package_checks.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
