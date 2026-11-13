"""Record a reviewable candidate and compact test evidence; no promotion implied."""
from pathlib import Path
import hashlib,json,shutil,zipfile
H=Path(__file__).resolve().parent;B=H/'build/dense12_w10_wp';O=H/'candidates/native12'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
O.mkdir(parents=True,exist_ok=True)
files={n:B/n for n in ['q12_task4.sv','q12_rice_decoder.sv','q12_stream_engine_overlap.sv','q12_icb_stream_prefix.sv','soc_main.c']}
files.update({'q12_dense12_writer.sv':H/'rtl/q12_dense12_writer.sv','tb_native_vendor.sv':H/'server/tb_native_vendor.sv',
              'startup.S':H/'firmware/startup.S','linker.ld':H/'firmware/linker.ld'})
for n,p in files.items():shutil.copyfile(p,O/n)
checks={'synthetic_soc12':json.loads((B/'result.json').read_text())}
for n in ['writer12_result.json','requant12_result.json','decoder_k7_result.json']:
 p=H/'checks'/n
 if p.exists():checks[n]=json.loads(p.read_text())
checks['decoder_k7_result.json']=json.loads((H/'checks/decoder_k7/replay_result.json').read_text())
assert checks['synthetic_soc12']['passed']and len(checks['synthetic_soc12']['tasks'])==12
with zipfile.ZipFile(H/'server/native12.zip')as z:server_identity=json.loads(z.read('identity.json'))
record={'candidate':'q12_x12_w10_y12_native_write_priority','status':'EXPERIMENTAL_NOT_PROMOTED',
 'source_sha256':{n:sha(O/n)for n in files},'generator_sha256':sha(H/'run_local.py'),
 'server_package_identity':server_identity,'output':{'format':'signed12 fixed-index full matrix','compression':False,
 'elements':25344,'tile_count':16,'rows_per_tile':99,'columns_per_tile':16,'tile_words':594,'allocation_words':9521,'task_writes':9522,'magic':'0x32443151'},
 'numeric_transform':{'x':'unchanged frozen signed12','weights':'RNE(original signed12 / 4), clamp [-512,511]',
 'bias':'RNE(original signed22 / 4)','shift':'original shift - 1','output':'signed12 RNE, clamp [-2048,2047]','physical_output_scale':'twice original signed13 output scale','training_or_finetuning':False},
 'requirements':{'min_throughput_tasks_s':6000,'preferred_min_throughput':6022.403340426386,'max_incremental_area_mm2':0.448646862835,'system_bus_bits':32,'full_loading_window':True},
 'evidence':checks,'qualified_throughput':None,'area_mm2':None,'energy_uj':None,'timing_pass':False,'official600_accuracy_pass':False}
(O/'candidate.json').write_text(json.dumps(record,indent=2)+'\n');print('FROZEN_EXPERIMENTAL_CANDIDATE',sha(O/'candidate.json'))
