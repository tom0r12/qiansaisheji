from pathlib import Path
import json,re
def out(s):
 for line in str(s).splitlines():print(' '*35+line[:160])
print('\033[2J\033[H',end='')
for f in Path('/tmp').glob('q12_power_probe_*/result.json'):
 p=f.parent;out('PROBE '+str(p));out(f.read_text());log=(p/'tool.log').read_text(errors='replace')
 lines=log.splitlines()
 for i,line in enumerate(lines):
  if line.startswith('Error:')or'Q12_FINAL_POWER_FAILED'in line:out('\n'.join(lines[max(0,i-2):i+5]))
 out('FILES '+str([q.name for q in p.iterdir()]))
 out('LOG_TAIL');out('\n'.join(lines[-12:]))
for f in Path('/tmp').glob('q12_earlycheck_full_*/synth/tool.log'):
 out('LATEST_SYNTH '+str(f));out('\n'.join(f.read_text(errors='replace').splitlines()[-6:]))
