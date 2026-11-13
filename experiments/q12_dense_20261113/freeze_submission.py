"""Export the measured candidate without private fixtures or technology libraries."""
from pathlib import Path
import hashlib,json,shutil
H=Path(__file__).resolve().parent;R=H.parents[1]
C=H/'candidates/native12_earlycheck';B=R/'final/q12_20261113/vendor'
O=R/'final/q12_submission_20261113'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
record=json.loads((C/'candidate.json').read_text())
for n,h in record['source_sha256'].items():assert sha(C/n)==h,n
assert not O.exists(),'Frozen release already exists; do not overwrite it'
O.mkdir();shutil.copytree(B/'src',O/'src',ignore=shutil.ignore_patterns('q13_rice_encoder.sv'))
mapping={
 'src/q12/core_datareset/q12_task4.sv':'q12_task4.sv',
 'src/q12/decoder2/q12_rice_decoder.sv':'q12_rice_decoder.sv',
 'src/q12/integration/q12_icb_stream_prefix.sv':'q12_icb_stream_prefix.sv',
 'src/q12/integration/q12_stream_engine_overlap.sv':'q12_stream_engine_overlap.sv',
 'src/q12/native_output/q12_dense12_writer.sv':'q12_dense12_writer.sv',
 'src/q12_vendor/tb_q12soc_vendor.sv':'tb_native_vendor.sv'}
for target,source in mapping.items():
 p=O/target;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/source,p)
(O/'firmware').mkdir()
for n in ('soc_main.c','startup.S','linker.ld'):shutil.copyfile(C/n,O/'firmware'/n)
fw=H/'build/dense12_w10_wp_earlycheck/firmware64.hex'
assert sha(fw)==record['synthetic_soc12']['firmware_sha256']
shutil.copyfile(fw,O/'firmware/firmware64.hex')
baseline=json.loads((B/'manifest.json').read_text())
order=[s.replace('src/q12/encoder_bounded/q13_rice_encoder.sv','src/q12/native_output/q12_dense12_writer.sv') for s in baseline['source_order']]
assert all((O/s).is_file()for s in order)
files={'source_order':order,'include_directories':baseline['include_directories'],
       'simulation_top':'tb_q12soc','synthesis_top':'qingyu_e203_soc_top',
       'external_dependencies':['Authorized standard-cell libraries','Official RAMSP128X16/RAMSP1024X16/RAMSP4096X16 models and libraries','Private task vectors regenerated for X12/W10/Y12'],
       'note':'Source list includes testbench and macro-presence checks; synthesis must exclude src/q12_vendor/. Do not reuse old compressed task outputs.'}
(O/'filelist.json').write_text(json.dumps(files,indent=2)+'\n')
e=O/'evidence';e.mkdir()
for n in ('earlycheck_observation.json','power_observation.json','final_report_data.json'):
 shutil.copyfile(H/'report_2h_20261113'/n,e/n)
freeze={'selection':'USER_SELECTED_SUBMISSION_BASELINE','engineering_acceptance':'OPEN_ITEMS_REMAIN',
 'candidate':record['candidate'],'engine_sha256':record['source_sha256']['q12_stream_engine_overlap.sv'],
 'measured_netlist_sha256':'3eb43b4d79bbeb0389f4bb272e93629e7241dc1a6186c4e6c37a8b7bd448b712',
 'source_overrides':mapping,'output':record['output'],'numeric_transform':record['numeric_transform'],
 'server_run':'/tmp/q12_earlycheck_full_y0zb5w2z','power_run':'/tmp/q12_power_recovery_gghtgybp',
 'files_sha256':{str(p.relative_to(O)).replace('\\','/'):sha(p)for p in O.rglob('*')if p.is_file()}}
(O/'FREEZE_MANIFEST.json').write_text(json.dumps(freeze,indent=2)+'\n')
print('FROZEN',O,'FILES',len(freeze['files_sha256']),'ENGINE',freeze['engine_sha256'])
