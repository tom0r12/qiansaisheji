"""Package one validated INT8 E203 composition and its complete diagnostic corpus.

Never uploads or starts proprietary EDA. Functional stand-in models are not copied.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,shutil,zipfile
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,text):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,newline='\n')
def copy(a,b):b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a,b)
def load(path):return json.loads(path.read_text())
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--corpus-run',type=Path,required=True)
 p.add_argument('--fixture-evidence',type=Path,required=True)
 p.add_argument('--core-dir',default='experiments/arithmetic/winograd_task8_prefetch',help='Explicit selected core; must match every report and physical fixture')
 p.add_argument('--output',type=Path)
 a=p.parse_args();corpus_path=a.corpus_run.resolve()/'result.json';corpus=load(corpus_path)
 if not corpus['passed'] or corpus['tasks']!=72 or len(corpus['runs'])!=6:raise ValueError('Complete passing 72-task E203 corpus required')
 packets_path=ROOT/'build/int8_packet_corpus_20261112/result.json';packets=load(packets_path)
 if sha(packets_path)!=corpus['corpus_manifest_sha256'] or not packets['passed']:raise ValueError('Packet corpus provenance differs')
 packet_by_sample={x['sample_index']:ROOT/x['path'].replace('\\','/') for x in packets['results']}
 runs=[]
 for item in corpus['runs']:
  path=ROOT/item['result'];r=load(path)
  if sha(path)!=item['result_sha256'] or not r['passed'] or len(r['layers'])!=12:raise ValueError('Incomplete/changed SoC constituent')
  if r['reuse_contract_version']!=2:raise ValueError('Need hardened source/include/build contract')
  for name,h in r['sources_sha256'].items():
   if sha(ROOT/name)!=h:raise ValueError('Validated RTL/include differs: '+name)
  for name,h in r['firmware_sources_sha256'].items():
   if sha(ROOT/name)!=h:raise ValueError('Validated firmware differs')
  if sha(path.parent/'firmware64.hex')!=r['firmware_hex_sha256']:raise ValueError('Validated firmware image differs')
  runs.append((path,r))
 baseline=runs[0][1]
 def stable(r):return {k:v for k,v in r['sources_sha256'].items() if not k.startswith('build/int8soc/')}
 for path,r in runs:
  if stable(r)!=stable(baseline) or r['source_order']!=baseline['source_order'] or r['firmware_hex_sha256']!=baseline['firmware_hex_sha256']:raise ValueError('Corpus mixes source configurations/firmware')
 core_choices={'experiments/arithmetic/winograd_task8_prefetch':('prefetch8',8),'experiments/arithmetic/winograd_task9':('task9',9)}
 if a.core_dir not in core_choices or baseline['engine_directory']!='experiments/integration/int8stream_dual' or baseline['core_directory']!=a.core_dir or baseline['codec_directory']!='experiments/codec/rice32_bounded':
  raise ValueError('This fixture needs explicit matching dual + prefetch8/task9 + bounded codec')
 core_label,x_macros=core_choices[a.core_dir]
 evidence_path=a.fixture_evidence.resolve();evidence=load(evidence_path)
 if not evidence['passed'] or not evidence['identical_baseline_metrics'] or evidence['manufacturer']:
  raise ValueError('Need explicit local functional fixture evidence, not invented manufacturer acceptance')
 for name,h in evidence['sources_sha256'].items():
  path=Path(name)
  # Evidence is produced in WSL. Compare its project-relative suffix on either host.
  marker='/qingyu/';norm=str(path).replace('\\','/')
  if not norm.startswith('/') and not re.match(r'^[A-Za-z]:/',norm):raise ValueError('Unexpected local source identity')
  if marker not in norm:raise ValueError('Fixture source outside project')
  local=ROOT/norm.split(marker,1)[1]
  if sha(local)!=h:raise ValueError('Fixture source changed: '+str(local))
 fixture_source_path=ROOT/evidence['source_run']/'result.json'
 if sha(fixture_source_path)!=evidence['source_run_sha256']:raise ValueError('Physical source run evidence changed')
 fixture_source_run=load(fixture_source_path)
 if stable(fixture_source_run)!=stable(baseline):raise ValueError('Fixture checked another INT8 composition')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 output=(a.output or ROOT/'build/int8soc_server_bundles'/stamp).resolve();output.mkdir(parents=True,exist_ok=False)
 bundle=output/'qingyu_int8soc_bundle';bundle.mkdir()
 manifest=dict(schema='qingyu-int8-e203-server-bundle-v1',candidate='int8_dual_'+core_label+'_bounded',created_utc=stamp,
  runner_kind='int8_packet_e203',checker={'top':'tb_int8soc','original':'experiments/integration/int8soc/tb_int8soc.sv','original_sha256':stable(baseline)['experiments/integration/int8soc/tb_int8soc.sv']},
  composition={k:baseline[k] for k in ['engine_directory','core_directory','codec_directory','frozen_components']},
  source_order=baseline['source_order'],local_corpus_result_sha256=sha(corpus_path),local_fixture_evidence_sha256=sha(evidence_path),
  expected_macros={'private128':21,'private1024':x_macros,'shared4096':64,'cpu4096':16},
  measured_window='first accepted CPU parameter write through final originating magic ACK, inclusive actual bus clock cycles',
  activity_window='start at first accepted CPU parameter write edge; end at edge immediately following final marker ACK; duration equals inclusive cycle count',
  excluded_window='testbench source/ITCM/DTCM preload and boot before CPU parameter write',
  official_loading_window_status='OPEN; no initial-loader source integrated',required_stdcell_family='SCC40NLL_VHSC40_RVT_V0p1',
  ppa_status='prepared only; manufacturer models and timing/power libraries still require external identity review',
  official_600_sample_evaluation=False,manufacturer_simulation_passed=False,tasks=[],files_sha256={})
 for source in (HERE/'templates').rglob('*'):
  if source.is_file() and '__pycache__' not in source.parts:copy(source,bundle/source.relative_to(HERE/'templates'))
 copy(HERE/'tb_int8soc_behavior.sv',bundle/'common/tb_behavior.sv')
 copy(HERE/'tb_int8soc_macro.sv',bundle/'common/tb_macro.sv')
 behavior=[]
 for name in baseline['source_order']:
  if name=='<run>/config.v':source=runs[0][0].parent/'config.v';target='common/config.v'
  elif name=='experiments/integration/int8soc/tb_int8soc.sv':source=None;target='common/tb_behavior.sv'
  else:source=ROOT/name;target=name
  if source is not None:copy(source,bundle/target)
  behavior.append(target)
 for name in baseline['sources_sha256']:
  if name.startswith('vendor/') and not (bundle/name).is_file():copy(ROOT/name,bundle/name)
 vendor=ROOT/'vendor/e203_hbirdv2';inventory_path=ROOT/'reports/e203-source-manifest.json';inventory=load(inventory_path)
 if not inventory['ready'] or inventory['commit']!='9f3e34f337f5d0a1236a285871ffa2032491617a':raise ValueError('Vendor pin differs')
 for name,h in baseline['official_sources_verified'].items():
  if sha(vendor/name)!=h or inventory['files'][name]['sha256']!=h or not inventory['files'][name]['matches_commit']:raise ValueError('Vendor source mismatch')
 if sha(vendor/'LICENSE')!=inventory['files']['LICENSE']['sha256']:raise ValueError('Vendor LICENSE mismatch')
 copy(vendor/'LICENSE',bundle/'vendor/e203_hbirdv2/LICENSE')
 put(bundle/'evidence/vendor_identity.json',json.dumps(dict(commit=inventory['commit'],inventory_sha256=sha(inventory_path),verified_files=baseline['official_sources_verified'],license_sha256=sha(vendor/'LICENSE')),indent=2)+'\n')
 replacements={'rtl/qingyu_sram16.sv':'rtl/asic/qingyu_sram16.sv',
  'vendor/e203_hbirdv2/rtl/e203/general/sirv_gnrl_ram.v':'rtl/asic/sirv_gnrl_ram.v',
  'vendor/e203_hbirdv2/rtl/e203/general/sirv_sim_ram.v':None,
  'experiments/h1500v/opt33_readcache/rtl/qingyu_shared_sram.sv':'experiments/h1500v/opt33_readcache/rtl/asic/qingyu_shared_sram.sv',
  'common/tb_behavior.sv':'common/tb_macro.sv'}
 macro=[replacements.get(x,x) for x in behavior];macro=[x for x in macro if x]+['rtl/asic/qingyu_banked_sram.sv']
 for name in replacements.values():
  if name and not name.startswith('common/'):copy(ROOT/name,bundle/name)
 copy(ROOT/'rtl/asic/qingyu_banked_sram.sv',bundle/'rtl/asic/qingyu_banked_sram.sv')
 synth=[x for x in macro if not x.startswith('common/')]
 for mode,lines in [('behavioral',behavior),('macro',macro),('soc_synth',synth)]:put(bundle/f'filelists/{mode}.f','\n'.join(lines)+'\n')
 include_headers=['vendor/e203_hbirdv2/rtl/e203/'+name for name in ['core/config.v','core/e203_defines.v','perips/apb_i2c/i2c_master_defines.v']]
 if any(name not in baseline['sources_sha256'] for name in include_headers):raise ValueError('Explicit validated include header missing')
 put(bundle/'filelists/includes.f','\n'.join(include_headers)+'\n')
 manifest['include_headers_sha256']={name:sha(bundle/name) for name in include_headers}
 put(bundle/'common/synth_defines.v','`define DISABLE_SV_ASSERTION 1\n')
 put(bundle/'assessment_expected.tcl',''.join('set EXPECTED_'+k.upper()+' '+str(v)+'\n' for k,v in manifest['expected_macros'].items()))
 copy(runs[0][0].parent/'firmware64.hex',bundle/'firmware64.hex')
 for name in baseline['firmware_sources_sha256']:copy(ROOT/name,bundle/name)
 copy(corpus_path,bundle/'evidence/validated_corpus.json')
 # Sanitize local absolute paths in functional evidence; retain the original SHA.
 safe_evidence={k:v for k,v in evidence.items() if k not in ['sources_sha256','commands']}
 safe_evidence['sources_sha256']={str(k).replace('\\','/').split('/qingyu/',1)[1]:v for k,v in evidence['sources_sha256'].items()}
 safe_evidence['original_evidence_sha256']=sha(evidence_path)
 put(bundle/'evidence/local_functional_fixture.json',json.dumps(safe_evidence,indent=2)+'\n')
 for path,r in runs:
  sample=r['sample_index'];packet_result_path=packet_by_sample[sample];packet_report=load(packet_result_path)
  if not packet_report['passed'] or sha(packet_result_path)!=r['packet_result_sha256']:raise ValueError('Packet identity mismatch')
  copy(path,bundle/f'evidence/sample{sample:03d}_soc.json')
  for row in r['layers']:
   layer=row['layer'];data=packet_result_path.parent/f'layer{layer:02d}';meta=load(data/'manifest.json')
   if sha(data/'manifest.json')!=row['packet_manifest_sha256']:raise ValueError('Validated packet manifest differs')
   task_id=f'sample{sample:03d}_layer{layer:02d}'
   for name in ['input.hex','expected_output.hex','manifest.json']:
    if name!='manifest.json' and sha(data/name)!=meta['files_sha256'][name]:raise ValueError('Packet bytes differ')
    copy(data/name,bundle/'tasks'/task_id/name)
   manifest['tasks'].append(dict(task_id=task_id,sample_index=sample,layer=layer,input_words=meta['input_words'],output_written_words=meta['output_written_words'],expected_metrics=row['metrics'],validated_log_sha256=row['simulation_log_sha256']))
 for directory,h in baseline['frozen_components'].items():
  if sha(ROOT/directory/'SOURCE_SHA256.json')!=h:raise ValueError('Component manifest changed')
  copy(ROOT/directory/'SOURCE_SHA256.json',bundle/'evidence/component_manifests'/(Path(directory).name+'.json'))
 readme=(HERE/'SERVER_README.md').read_text().replace('prefetch8',core_label).replace('8 private1024x16',str(x_macros)+' private1024x16')
 put(bundle/'README.md',readme)
 manifest['physical_fixture_sha256']=sha(bundle/'common/tb_macro.sv')
 manifest['packager_sha256']=sha(Path(__file__))
 manifest['files_sha256']={f.relative_to(bundle).as_posix():sha(f) for f in sorted(bundle.rglob('*')) if f.is_file()}
 put(bundle/'manifest.json',json.dumps(manifest,indent=2)+'\n')
 # Recheck all source identities after copying, before the immutable archive.
 for path,r in runs:
  for name,h in r['sources_sha256'].items():
   if sha(ROOT/name)!=h:raise ValueError('Source changed during package generation')
 archive=output/'qingyu_int8soc_validation.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
  for f in sorted(bundle.rglob('*')):
   if f.is_file():z.write(f,f.relative_to(output).as_posix())
 zip_hash=sha(archive)
 launcher='''#!/bin/sh
set -eu
cd "$(dirname "$0")"
printf '%s  %s\\n' 'ZIPHASH' 'qingyu_int8soc_validation.zip' | sha256sum -c -
run=$(mktemp -d "qingyu_int8verify_XXXXXX")
unzip -q qingyu_int8soc_validation.zip -d "$run"
exec python3 "$run/qingyu_int8soc_bundle/run_int8_server.py" "$@"
'''.replace('ZIPHASH',zip_hash)
 put(output/'qi',launcher)
 summary=dict(bundle=bundle.relative_to(ROOT).as_posix(),zip=archive.relative_to(ROOT).as_posix(),zip_sha256=zip_hash,zip_bytes=archive.stat().st_size,launcher_sha256=sha(output/'qi'),tasks=len(manifest['tasks']),uploaded=False)
 put(output/'package_result.json',json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
