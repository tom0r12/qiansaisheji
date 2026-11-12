"""Check immutable INT8 package, fail-closed gates and actual macro hierarchy."""
from pathlib import Path
import argparse,ast,hashlib,json,re,subprocess,sys,tkinter,zipfile
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--fixture-run',type=Path,required=True);a=p.parse_args()
 bundle=a.bundle.resolve();fixture=a.fixture_run.resolve();m=json.loads((bundle/'manifest.json').read_text());r={'passed':False,'checks':[]}
 def ok(s):r['checks'].append(s)
 actual={p.relative_to(bundle).as_posix() for p in bundle.rglob('*') if p.is_file()}
 if actual!=set(m['files_sha256'])|{'manifest.json'}:raise ValueError('Unlisted/missing package files')
 for name,h in m['files_sha256'].items():
  if not (bundle/name).resolve().is_relative_to(bundle) or sha(bundle/name)!=h:raise ValueError('Package changed '+name)
 ok('complete manifest/hash closure')
 includes=(bundle/'filelists/includes.f').read_text().splitlines()
 if set(includes)!=set(m['include_headers_sha256']) or any(sha(bundle/n)!=m['include_headers_sha256'][n] for n in includes):raise ValueError('Explicit include inventory differs')
 if '$sources $include_headers $STD_CELL_LIBS' not in (bundle/'assessment/common.tcl').read_text():raise ValueError('Assessment misses include header hashes')
 if 'Assessment input changed: ' not in (bundle/'run_int8_server.py').read_text():raise ValueError('Assessment omits full post-run manifest check')
 ok('explicit include hashes and complete post-assessment input verification')
 local=json.loads((fixture/'result.json').read_text())
 tested_order=[local['sources_sha256'][str(x)] for x in local['commands'][0] if str(x) in local['sources_sha256']]
 packaged_order=[sha(bundle/x) for x in (bundle/'filelists/macro.f').read_text().splitlines()]+[local['model_sha256']]
 if tested_order!=packaged_order:raise ValueError('Packaged macro source order differs from the actual passed four-state compilation')
 ok('ordered packaged macro sources exactly match passed four-state compile inputs')
 with zipfile.ZipFile(bundle.parent/'qingyu_int8soc_validation.zip') as z:
  if z.testzip():raise ValueError('ZIP CRC')
 ok('ZIP CRC')
 for path in bundle.rglob('*.py'):ast.parse(path.read_text())
 tcl=tkinter.Tcl()
 for path in bundle.rglob('*.tcl'):
  if not int(tcl.call('info','complete',path.read_text())):raise ValueError('Incomplete Tcl '+str(path))
 ok('Python syntax and Tcl complete-script syntax')
 common=(bundle/'assessment/common.tcl').read_text();tcl.eval(common[common.index('set fixed_cpu_prefix'):common.index('proc memory_audit')])
 cases={
 'u_fio/engine/compute/pe/reg':'included_compute_logic','u_fio/engine/transport/owner':'included_transport_logic',
 'u_fio/engine/encoder/history':'included_codec_logic','u_fio/engine/decoder/history':'included_codec_logic',
 'u_fio/engine/reorder/buffer':'included_reorder_logic','u_fio/engine/state':'included_engine_control_logic',
 'u_fio/response':'included_fio_mmio_logic','u_shared/u_cache/cache_data':'included_shared_interface_logic',
 'u_e203_subsys_top/u_e203_subsys_main/u_mem_merge/owner':'included_new_bus_merges',
 'u_e203_subsys_top/u_e203_subsys_main/u_e203_cpu_top/core/reg':'excluded_reused_cpu_logic',
 'u_e203_subsys_top/u_e203_subsys_main/u_e203_subsys_mems/fabric/reg':'excluded_fixed_bus_peripheral_logic',
 'u_e203_subsys_top/u_e203_subsys_main/new_boundary':'included_adapter_or_boundary_logic'}
 for name,expected in cases.items():
  if tcl.call('area_class',name,'DFF')!=expected:raise ValueError('Wrong accounting '+name)
 ok('all new INT8 logic, merge, shared interface and boundary area included')
 vvp=fixture/'simv';scopes={}
 for line in vvp.read_text().splitlines():
  q=re.match(r'^(S_\w+) \.scope (\w+), "([^"]+)" "([^"]+)"',line)
  if q:
   parents=re.findall(r', (S_\w+)',line)
   scopes[q[1]]=dict(kind=q[2],name=q[3],reference=q[4],parent=parents[-1] if parents else None)
 def hierarchy(key):
  row=scopes[key];return (hierarchy(row['parent'])+'/' if row['parent'] else '')+row['name']
 counts={'private128':0,'private1024':0,'shared4096':0,'cpu4096':0};macros=[]
 for key,row in scopes.items():
  if row['kind']!='module' or not row['reference'].startswith('RAMSP'):continue
  name=hierarchy(key)
  if not name.startswith('tb_int8soc/dut/'):raise ValueError('Macro outside full SoC')
  category=tcl.call('area_class',name[len('tb_int8soc/dut/'):],row['reference'])
  countkey={('included_private_macro','RAMSP128X16'):'private128',('included_private_macro','RAMSP1024X16'):'private1024',('excluded_fixed_shared_macro','RAMSP4096X16'):'shared4096',('excluded_cpu_tcm_macro','RAMSP4096X16'):'cpu4096'}.get((category,row['reference']))
  if countkey is None:raise ValueError('Unexpected actual macro '+name)
  counts[countkey]+=1;macros.append(dict(instance=name,reference=row['reference'],area_class=category))
 if counts!=m['expected_macros']:raise ValueError('Actual elaborated macro counts differ '+str(counts))
 r['actual_macro_counts']=counts;r['macro_inventory']=macros;r['local_vvp_sha256']=sha(vvp)
 ok('actual four-state compiled macro hierarchy matches declared counts/accounting')
 for key,value in {'QINGYU_BUNDLE':bundle,'QINGYU_WORK':bundle.parent,'QINGYU_PLATFORM_CONFIG':bundle/'platform_config.example.tcl','QINGYU_BUNDLE_SHA256':'local-check'}.items():tcl.setvar('env('+key+')',str(value))
 try:tcl.call('source',str(bundle/'assessment/common.tcl'))
 except tkinter.TclError as error:
  if 'Configuration must explicitly define STD_CELL_LIBS' not in str(error):raise
 else:raise ValueError('Unconfigured EDA did not fail closed')
 ok('unconfigured assessment fails before vendor tool commands')
 for mode in ['behavioral','macro','soc_synth']:
  lines=(bundle/f'filelists/{mode}.f').read_text().splitlines()
  if len(lines)!=len(set(lines)) or any(not (bundle/x).is_file() for x in lines):raise ValueError('Bad ordered filelist')
  if mode!='behavioral' and any(x in lines for x in ['rtl/qingyu_sram16.sv','vendor/e203_hbirdv2/rtl/e203/general/sirv_sim_ram.v','experiments/h1500v/opt33_readcache/rtl/qingyu_shared_sram.sv']):raise ValueError('Behavioral memory in physical build')
 for path in bundle.rglob('*'):
  if not path.is_file():continue
  if path.name in ['AGENTS.md'] or 'local_functional_models' in path.name:raise ValueError('Nonengineering/model file packaged')
  if re.search(r'codex|openai|chatgpt|AGENTS\.md|C:[/\\]+Users[/\\]',path.read_text(errors='replace'),re.I):raise ValueError('Local product/credential-directory text packaged: '+str(path))
  if path.suffix in ['.v','.sv'] and re.search(r'\bmodule\s+RAMSP(?:128|1024|4096)X16',path.read_text()):raise ValueError('Macro model copied into bundle')
 ok('ordered physical source closure; manufacturer models remain external')
 physical=(bundle/'common/tb_macro.sv').read_text()
 for text in ['.mem[','.mem_r[']:
  if text in physical:raise ValueError('Private-array shortcut in physical fixture')
 for text in ['read_shared_word(17\'(word_index),readback_data)','word_index<131072','preload_commands!=131072||preload_responses!=131072','runtime_enabled=1;rst_n=1;','release `SHARED.cache_clear;','activity_pending<=1;','last_ack=cycles;']:
  if text not in physical:raise ValueError('Physical fixture invariant absent '+text)
 ok('real macro-port initialization and full shared readback; runtime/last-ACK activity isolation')
 subprocess.run([sys.executable,str(bundle/'run_int8_server.py'),'--mode','validate'],check=True,capture_output=True,text=True)
 r.update(passed=True,manifest_sha256=sha(bundle/'manifest.json'),limits=['Local functional model and syntax/accounting only; no manufacturer/STA/PPA execution'])
 (bundle.parent/'local_package_checks.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='macro_inventory'},indent=2))
if __name__=='__main__':main()
