"""Real E203 execution of complete compressed packets through the official bus."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from run_candidate_soc import sha,run

def build_contract(command):
 result=[];i=0
 generated={'--Mdir':'<linux-build>/obj','-f':'<run>/sources.f'}
 while i<len(command):
  token=str(command[i])
  if token=='-j':i+=2;continue
  if token in generated:result.extend([token,generated[token]]);i+=2;continue
  result.append(token);i+=1
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--layers',type=int,default=1)
 p.add_argument('--jobs',type=int,default=2)
 p.add_argument('--reuse-build',type=Path)
 p.add_argument('--images',type=Path,default=ROOT/'build/int8_packets_20261112')
 p.add_argument('--core-dir',type=Path,default=ROOT/'experiments/arithmetic/winograd_task8')
 p.add_argument('--engine-dir',type=Path,default=ROOT/'experiments/integration/int8stream')
 p.add_argument('--codec-dir',type=Path,default=ROOT/'experiments/codec/rice32')
 a=p.parse_args()
 if not 1<=a.layers<=12 or a.jobs<1:p.error('invalid layers/jobs')
 out=ROOT/'build/int8soc'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
 images=(ROOT/a.images).resolve();core=(ROOT/a.core_dir).resolve()
 engine=(ROOT/a.engine_dir).resolve();codec=(ROOT/a.codec_dir).resolve()
 if any(not d.is_relative_to(ROOT) for d in [core,engine,codec]):raise ValueError('component outside workspace')
 packet_report_path=images/'result.json';packet_report=json.loads(packet_report_path.read_text())
 if not packet_report.get('passed'):raise ValueError('packet export did not pass')
 packet_rows={r['layer']:r for r in packet_report['layers']}
 if set(packet_rows)!=set(range(12)):raise ValueError('incomplete packet export')
 cfg=out/'config.v';cfg.write_text('`timescale 1ns/1ps\n')
 base=ROOT/'experiments/h1500v/opt33_readcache/rtl'
 template=ROOT/'scripts/fixtures/e203_soc_sources.f'
 replacements={'build/block_config.v':cfg,'build/timescale.v':None,
  'generated/qingyu_e203_soc_top.v':HERE/'qingyu_e203_soc_top.v',
  'generated/qingyu_e203_subsys_main.v':base/'qingyu_e203_subsys_main.v',
  'generated/qingyu_e203_subsys_top.v':base/'qingyu_e203_subsys_top.v',
  'build/dual_row_study/qingyu_accel.sv':None,'rtl/qingyu_fio.sv':HERE/'qingyu_int8stream_fio.sv',
  'rtl/qingyu_shared_sram.sv':base/'qingyu_shared_sram.sv',
  'tb/tb_qingyu_soc.sv':HERE/'tb_int8soc.sv','tb/tb_qingyu_soc_performance.sv':None}
 sources=[replacements.get(s,ROOT/s) for s in template.read_text().splitlines() if s.strip()]
 sources=[s for s in sources if s is not None]
 extra=[str((engine/'qingyu_int8stream_engine.sv').relative_to(ROOT)),
  'experiments/transport/icb_stream_prefix/qingyu_icb_stream_prefix.sv',
  str((codec/'rice32_encoder.sv').relative_to(ROOT)),str((codec/'rice32_decoder.sv').relative_to(ROOT)),
  'experiments/transport/rowpair_pack/rowpair_pack.sv',
  str((core/'winograd_int8_task8.sv').relative_to(ROOT)),
  'experiments/arithmetic/winograd_array8/winograd_int8_pair_acc32.sv']
 sources += [ROOT/s for s in extra]+[base/'qingyu_icb_merge.sv']
 if len(sources)!=len(set(sources)):raise ValueError('duplicate source')
 includes=[ROOT/'vendor/e203_hbirdv2/rtl/e203'/s for s in
           ['core/config.v','core/e203_defines.v','perips/apb_i2c/i2c_master_defines.v']]
 def snapshot():return {str(s.relative_to(ROOT)):sha(s) for s in sources+includes}
 before=snapshot()
 vendor_path=ROOT/'reports/e203-source-manifest.json';vendor=json.loads(vendor_path.read_text())
 assert vendor['ready'] and vendor['commit']=='9f3e34f337f5d0a1236a285871ffa2032491617a'
 verified={}
 for s in sources+includes:
  if s.is_relative_to(ROOT/'vendor/e203_hbirdv2'):
   name=s.relative_to(ROOT/'vendor/e203_hbirdv2').as_posix();entry=vendor['files'][name]
   if not entry['matches_commit'] or sha(s)!=entry['sha256']:raise ValueError('official source changed '+name)
   verified[name]=sha(s)
 frozen={}
 for directory in ['experiments/transport/icb_stream_prefix',str(codec.relative_to(ROOT)),
                   'experiments/transport/rowpair_pack',str(core.relative_to(ROOT)),str(engine.relative_to(ROOT))]:
  manifest=ROOT/directory/'SOURCE_SHA256.json';record=json.loads(manifest.read_text())
  for name,digest in record['files'].items():
   if sha(manifest.parent/name)!=digest:raise ValueError('frozen component changed '+name)
  for name,digest in record.get('external_dependencies',{}).items():
   if sha(ROOT/name)!=digest:raise ValueError('frozen dependency changed '+name)
  frozen[directory]=sha(manifest)
 filelist=out/'sources.f';filelist.write_text(''.join(str(s.relative_to(ROOT))+'\n' for s in sources))
 source_order=['<run>/config.v' if s==cfg else str(s.relative_to(ROOT)) for s in sources]
 firmware_sources=[HERE/'soc_main.c',ROOT/'sw/startup.S',ROOT/'sw/runtime.c',ROOT/'sw/linker.ld']
 fw_before={str(s.relative_to(ROOT)):sha(s) for s in firmware_sources}
 report={'schema':'qingyu-int8soc-experiment-v1','passed':False,'phase':'compile',
  'sources_sha256':before,'source_order':source_order,'reuse_contract_version':2,
  'firmware_sources_sha256':fw_before,'runner_sha256':sha(Path(__file__)),
  'source_template_sha256':sha(template),'official_vendor_manifest_sha256':sha(vendor_path),
  'official_sources_verified':verified,'frozen_components':frozen,'core_directory':str(core.relative_to(ROOT)),'layers':[],
  'engine_directory':str(engine.relative_to(ROOT)),'codec_directory':str(codec.relative_to(ROOT)),
  'packet_result_sha256':sha(packet_report_path),'sample_index':packet_report['sample_index'],
  'limits':['Behavioral private/shared SRAM; no manufacturer PPA or STA',
   '150MHz assumed only','Source packet preloaded before reset; external official loader is excluded',
   'Real CPU setup/accepted START/first read to final originating output-marker ACK reported separately',
   'Selected 12 model layers, not the official600 audio evaluation']}
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 save();print(out,flush=True)
 try:
  lint_sources=[HERE/'qingyu_int8stream_fio.sv',*[ROOT/s for s in extra],ROOT/'rtl/qingyu_sram16.sv']
  run(['verilator','--lint-only','-Wall','--top-module','qingyu_int8stream_fio',*lint_sources],out/'rtl_lint.log')
  report['strict_new_rtl_lint_passed']=True;save()
  # Build generated C++ on the Linux filesystem; preserve the executable and
  # its exact source/compiler identities in the persistent project run folder.
  obj=Path(tempfile.mkdtemp(prefix='qingyu_int8soc_'))/'obj'
  build=['verilator','--binary','--timing','--autoflush','--timescale-override','1ns/1ps',
   '--top-module','tb_int8soc','--prefix','Vcandidate','--Mdir',obj,
   '-Wno-fatal','-DDISABLE_SV_ASSERTION=1','-j',str(a.jobs),'-CFLAGS','-O1','-f',filelist]
  build+=['-Ivendor/e203_hbirdv2/rtl/e203/'+s for s in ['core','perips','perips/apb_i2c']]
  args=build_contract(build[1:])
  if a.reuse_build:
   prior_dir=(ROOT/a.reuse_build).resolve();prior=json.loads((prior_dir/'result.json').read_text())
   if not prior.get('passed') or prior.get('reuse_contract_version')!=2:raise ValueError('reuse requires a passing version2 contract')
   if prior['source_order']!=source_order or prior['source_template_sha256']!=sha(template):raise ValueError('reused source order/template differs')
   def stable(d):return {k:v for k,v in d.items() if not k.startswith('build/int8soc/')}
   if stable(prior['sources_sha256'])!=stable(before):raise ValueError('reused sources differ')
   if sha(prior_dir/'config.v')!=sha(cfg):raise ValueError('reused config differs')
   if prior['simulator_build_arguments']!=args:raise ValueError('reused compiler arguments differ')
   executable=ROOT/prior['simulator_path']
   if sha(executable)!=prior['simulator_sha256']:raise ValueError('reused binary changed')
  else:
   run(build,out/'build.log',timeout=1200)
   executable=out/'Vcandidate';shutil.copy2(obj/'Vcandidate',executable)
  if snapshot()!=before:raise ValueError('source changed during build')
  report.update(simulator_build_arguments=args,simulator_sha256=sha(executable),
   simulator_path=str(executable.relative_to(ROOT)),compiler_output_directory=str(obj),phase='firmware');save()
  cc=['riscv64-unknown-elf-gcc','-march=rv32imac','-misa-spec=2.2','-mabi=ilp32',
   '-ffreestanding','-fno-builtin','-msmall-data-limit=0','-ffunction-sections','-fdata-sections',
   '-Wall','-Wextra','-Werror','-nostdlib','-nostartfiles','-O3','-flto','-Isw','-Tsw/linker.ld','-Wl,--gc-sections',
   ROOT/'sw/startup.S',HERE/'soc_main.c',ROOT/'sw/runtime.c','-lgcc','-o',out/'firmware.elf']
  run(cc,out/'firmware_compile.log')
  run(['riscv64-unknown-elf-objcopy','-O','binary',out/'firmware.elf',out/'firmware.bin'],out/'objcopy.log')
  raw=(out/'firmware.bin').read_bytes()
  if len(raw)>65536:raise ValueError('firmware too large')
  raw=raw.ljust(65536,b'\0');fw=out/'firmware64.hex'
  fw.write_text(''.join(f'{int.from_bytes(raw[i:i+8],"little"):016x}\n' for i in range(0,65536,8)))
  report.update(firmware_hex_sha256=sha(fw),phase='simulation');save()
  for layer in range(a.layers):
   data=images/f'layer{layer:02d}';m=json.loads((data/'manifest.json').read_text())
   if m!=packet_rows[layer]:raise ValueError('packet export/manifest mismatch')
   for name,digest in m['files_sha256'].items():
    if sha(data/name)!=digest:raise ValueError('packet changed '+name)
   case=out/f'layer{layer:02d}';case.mkdir()
   command=[executable,'+FIRMWARE='+str(fw),'+INPUT='+str(data/'input.hex'),
    '+EXPECTED='+str(data/'expected_output.hex'),'+INPUT_WORDS='+str(m['input_words']),
    '+OUTPUT_WORDS='+str(m['output_written_words']),'+LAYER='+str(layer)]
   run(command,case/'simulation.log',cwd=case,timeout=600)
   log=(case/'simulation.log').read_text()
   if 'PASS real E203 INT8 packet task complete;' not in log:raise ValueError('missing complete PASS')
   rows=re.findall(r'^INT8SOC_METRICS (.+)$',log,re.M)
   if len(rows)!=1:raise ValueError('ambiguous metrics')
   metrics={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',rows[0])}
   report['layers'].append({'layer':layer,'metrics':metrics,'packet_manifest_sha256':sha(data/'manifest.json'),
     'simulation_log':str((case/'simulation.log').relative_to(ROOT)),'simulation_log_sha256':sha(case/'simulation.log')})
   print(json.dumps(metrics),flush=True);save()
  if snapshot()!=before or {str(s.relative_to(ROOT)):sha(s) for s in firmware_sources}!=fw_before:raise ValueError('source changed during run')
  report.update(passed=True,phase='complete')
  report['mean_cpu_setup_to_ack_cycles']=sum(c['metrics']['cpu_setup_to_ack'] for c in report['layers'])/a.layers
  report['mean_start_to_ack_cycles']=sum(c['metrics']['start_to_ack'] for c in report['layers'])/a.layers
  report['tasks_per_second_cpu_setup_at_assumed_150mhz']=150000000/report['mean_cpu_setup_to_ack_cycles']
  save();print('PASS '+str(out/'result.json'),flush=True)
 except Exception as e:
  report.update(phase='failed',error=str(e));save();raise

if __name__=='__main__':main()
