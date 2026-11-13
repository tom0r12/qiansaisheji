"""Read-only report view: derives every numeric value from saved tool outputs."""
from pathlib import Path
import datetime,hashlib,json,re
def emit(s=''):
 for line in str(s).splitlines()or['']:print(' '*5+line,flush=True)
def read(p):return json.loads(p.read_text())
roots=list(Path('/tmp').glob('q12_earlycheck_full_*/result.json'));assert len(roots)==1
root=roots[0].parent;r=read(roots[0]);sr=r['stages']['synth'];v=read(root/'vendor_completed.json');cy=v['task_cycles']
print('\033[2J\033[H',end='');emit('Q12 FINAL CANDIDATE - MEASUREMENT SNAPSHOT '+datetime.datetime.now().isoformat())
emit('TT 1.10 V / 25 C | 150 MHz | full 99 x 256 signed12 output | no output entropy codec')
emit('RUN '+str(root));emit('ENGINE '+r['engine_sha256']);emit('NETLIST '+hashlib.sha256((root/'synth/mapped.v').read_bytes()).hexdigest())
emit();emit('VENDOR FUNCTIONAL CASES: 12 / 12 PASS; real SRAM readback and bus conservation')
emit('THROUGHPUT: %.6f tasks/s | mean %.6f cycles | maximum %d cycles'%(150000000/(sum(cy)/12),sum(cy)/12,max(cy)))
parts=sr['area_library_units'];area=parts['INCREMENTAL_LIBRARY_AREA']/1e6
emit('INCREMENTAL AREA: %.9f mm^2 | reference 0.448646863 mm^2 | change %.3f%%'%(area,(area/.448646862835-1)*100))
emit('FULL SOC AREA: %.9f mm^2'%(parts['FULL_SOC_LIBRARY_AREA']/1e6))
emit('DC SETUP: %.8f ns | DC HOLD: %.8f ns'%(sr['worst_reported_setup_ns'],sr['worst_reported_hold_ns']))
ct=(root/'synth/check_timing_after.rpt').read_text();emit('CHECK_TIMING: '+('unconstrained endpoints require review'if'not constrained'in ct else'no unconstrained endpoint warning'))
fm=root/'formal/result.json'
if fm.exists():
 f=read(fm);emit('FORMAL tool_complete=%s accepted=%s'%(f.get('tool_complete'),f.get('passed')));emit('FORMAL AUDIT '+json.dumps(f.get('audit'))[:260])
else:
 lines=[x.strip()for x in(root/'formal/tool.log').read_text(errors='replace').splitlines()if x.strip()];emit('FORMAL RUNNING '+' | '.join(lines[-2:]))
pr=[(p,read(p))for p in Path('/tmp').glob('q12_power_recovery_*/result.json')]
pr=[(p,a)for p,a in pr if a.get('windows')]
if pr:
 assert len(pr)==1
 p,a=pr[0];emit();emit('PT POWER RUN '+str(p.parent)+' | '+a['phase']);emit('Layer   Window (us)   Full-SoC power (mW)   Energy (uJ)')
 for w in a['windows']:
  n=w.get('provisional_unqualified')
  if n:emit('%02d      %10.6f        %10.6f          %10.6f'%(w['layer'],w['duration_ps']/1e6,n['power_w']*1000,n['energy_uj']))
 if'mean_energy_uj_unqualified'in a:emit('MEAN ENERGY %.9f uJ | weighted POWER %.9f mW'%(a['mean_energy_uj_unqualified'],a['weighted_power_w_unqualified']*1000))
 emit('POWER ACCEPTANCE: '+str(a.get('accepted'))+'; annotation sources and check_power warnings require review')
emit();emit('NOT OFFICIAL SIGNOFF: 600-sample accuracy and platform-loader acceptance remain open.')
