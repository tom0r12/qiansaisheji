"""Query the installed tool's own activity-provenance documentation."""
from pathlib import Path
import os,shutil,subprocess,tempfile
p=Path(tempfile.mkdtemp(prefix='q12_pt_api_',dir='/tmp'))
t=p/'help.tcl';t.write_text('help -verbose get_switching_activity\nhelp -verbose report_switching_activity\nexit\n')
lc=Path(shutil.which('lc_shell')).resolve().parent.parent
with(p/'help.log').open('w')as f:
 r=subprocess.run([shutil.which('pt_shell'),'-f',str(t)],cwd=str(p),env=dict(os.environ,SYNOPSYS_LC_ROOT=str(lc)),stdout=f,stderr=subprocess.STDOUT,timeout=90)
print('\033[2J\033[H',end='')
for line in (p/'help.log').read_text(errors='replace').splitlines():print(' '*35+line)
print(' '*35+'API_DIRECTORY '+str(p))
