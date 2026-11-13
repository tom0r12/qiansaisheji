from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parent
manifest=json.loads((root/'PUBLIC_EXPORT_MANIFEST.json').read_text(encoding='utf-8'))
errors=[]
for rel,record in manifest['files'].items():
 p=root/rel
 if not p.is_file():errors.append('MISSING '+rel)
 elif hashlib.sha256(p.read_bytes()).hexdigest()!=record['sha256']:errors.append('CHANGED '+rel)
for message in errors:print(message)
print('PUBLIC_EXPORT_FILES_VERIFIED='+str(len(manifest['files'])-len(errors)))
print('Private task inputs and PDK intentionally absent; this check does not prove simulation/signoff.')
sys.exit(1 if errors else 0)
