"""Stop only this session's owned, path-bound EDA jobs; retain every artifact."""
from pathlib import Path
import os, signal, time

prefixes = (
    'q12_native12_full_', 'q12_compact12_full_', 'q12_native12_timing_',
    'q12_earlycheck_full_', 'q12_power_recovery_', 'q12_c25_timing_full_',
    'q12_native_full_launch_', 'q12_compact_full_launch_', 'q12_early_launch_',
    'q12_timing_launch_', 'q12_power_recover_launch_', 'q12_cell_launch_',
)
roots = [p.resolve() for p in Path('/tmp').iterdir()
         if p.is_dir() and p.name.startswith(prefixes) and p.stat().st_uid == os.getuid()]
def inside(value):
    try:
        p = Path(value).resolve()
        return any(p == r or r in p.parents for r in roots)
    except (OSError, ValueError):
        return False
def scan():
    found = {}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name) == os.getpid(): continue
        try:
            if p.stat().st_uid != os.getuid(): continue
            cwd = os.readlink(str(p / 'cwd'))
            args = (p / 'cmdline').read_bytes().decode(errors='replace').split('\0')
            if inside(cwd) or any(x.startswith('/tmp/') and inside(x) for x in args):
                found[int(p.name)] = (cwd, Path(args[0]).name)
        except (OSError, ValueError): pass
    return found
jobs = scan()
for pid, (cwd, tool) in sorted(jobs.items()):
    print('STOP_OWN_SESSION', pid, tool, cwd, flush=True)
    try: os.kill(pid, signal.SIGTERM)
    except ProcessLookupError: pass
time.sleep(2)
for pid, (cwd, tool) in scan().items():
    print('FORCE_STOP_OWN_SESSION', pid, tool, cwd, flush=True)
    try: os.kill(pid, signal.SIGKILL)
    except ProcessLookupError: pass
time.sleep(1)
remaining = scan()
print('REMAINING_OWN_SESSION_JOBS', len(remaining), remaining, flush=True)
print('ARTIFACTS_RETAINED; NO_NEW_TESTS_STARTED', flush=True)
