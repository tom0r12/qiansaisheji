"""Exercise server preflight rejection without running an EDA executable."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,subprocess,sys,tempfile
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);a=p.parse_args();bundle=a.bundle.resolve()
 out=Path(tempfile.mkdtemp(prefix='qingyu_model_gate_'));env=os.environ.copy()
 # A resolvable executable makes tool-discovery pass. Every invocation below
 # uses --preflight and must fail at model identity before tool execution.
 env['QINGYU_VCS']=sys.executable;env.pop('QINGYU_SRAM_MODEL_IDENTITY',None)
 runner=bundle/'run_int8_server.py';checks=[]
 def reject(extra,message):
  r=subprocess.run([sys.executable,str(runner),'--mode','macro','--preflight',*extra],env=env,capture_output=True,text=True)
  if r.returncode==0 or message not in r.stderr:raise ValueError('Model gate did not reject expected case: '+r.stderr)
  checks.append(message)
 reject([],'requires --macro-model-manifest')
 wrong=out/'functional.json';wrong.write_text(json.dumps(dict(review='accepted',model_kind='local_functional',source_library='SRAM_Lib_2025')))
 reject(['--macro-model-manifest',str(wrong)],'Manufacturer SRAM model identity is not reviewed')
 pending=out/'pending.json';pending.write_text(json.dumps(dict(review='pending',model_kind='official_manufacturer',source_library='SRAM_Lib_2025')))
 reject(['--macro-model-manifest',str(pending)],'Manufacturer SRAM model identity is not reviewed')
 sys.dont_write_bytecode=True
 spec=importlib.util.spec_from_file_location('checked_server_runner',runner);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 artifact=out/'activity.log';artifact.write_text('original passed simulation\n');recorded=module.digest(artifact)
 module.verify_recorded_artifact(artifact,recorded,recorded)
 artifact.write_text('changed after successful simulation\n')
 try:module.verify_recorded_artifact(artifact,module.digest(artifact),recorded)
 except ValueError:checks.append('changed activity rejected even when review records its new hash')
 else:raise ValueError('Mutable activity/source-result identity gate failed')
 result=dict(passed=True,checks=checks,eda_executed=False,manifest_sha256=hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest())
 (bundle.parent/'local_model_gate_checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
