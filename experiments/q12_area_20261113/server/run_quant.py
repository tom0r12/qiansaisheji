#!/usr/bin/env python3
"""Isolated official-library A/B experiment; never edits the frozen final run."""
import hashlib
import json
import os
import signal
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

package = Path(__file__).resolve().parent
std = Path(os.environ.get('Q12_STD_DB', str(Path.home() / 'Desktop/smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1/liberty/1.1v/scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.db')))
dc = shutil.which('dc_shell')
if not dc or not std.is_file():
    raise SystemExit('Missing dc_shell or official TT library: ' + str(std))
root = Path(tempfile.mkdtemp(prefix='q12_quant_area_', dir='/tmp'))
print('Q12_QUANT_DIRECTORY=' + str(root), flush=True)
data = {'library': str(std), 'library_sha256': hashlib.sha256(std.read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256((package/'quant_miter.sv').read_bytes()).hexdigest(),
        'period_ns': 6.666666667, 'dc_shell': dc, 'directory': str(root), 'results': []}
for top in ('quant_reference', 'quant_candidate'):
    run = root / top
    run.mkdir()
    env = dict(os.environ, Q12_STD_DB=str(std), Q12_QUANT_SOURCE=str(package/'quant_miter.sv'), Q12_QUANT_TOP=top)
    start = time.time()
    with (run/'dc.log').open('w') as log:
        p = subprocess.Popen([dc, '-f', str(package/'map_quant.tcl')], cwd=str(run), env=env,
                             stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            p.wait(timeout=900)
            status = {'top': top, 'returncode': p.returncode, 'seconds': time.time()-start}
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
            status = {'top': top, 'timed_out': True, 'seconds': time.time()-start}
    status['metrics'] = (run/'metrics.txt').read_text() if (run/'metrics.txt').is_file() else None
    data['results'].append(status)
    (root/'result.json').write_text(json.dumps(data, indent=2))
    print(json.dumps(status), flush=True)
print('Q12_QUANT_RESULT=' + str(root/'result.json'), flush=True)
