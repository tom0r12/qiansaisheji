"""Check saved evidence and generate the twelve-window table, without EDA."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent
obs = json.loads((ROOT / 'earlycheck_observation.json').read_text(encoding='utf-8'))
power = json.loads((ROOT / 'power_observation.json').read_text(encoding='utf-8'))
provenance = json.loads((ROOT / 'report_provenance.json').read_text(encoding='utf-8'))
assert obs['netlist_sha256'] == power['netlist_sha256'] == provenance['frozen_netlist_sha256']
assert obs['engine_sha256'] == provenance['frozen_engine_sha256']
cycles, durations, watts = obs['task_cycles'], power['window_duration_ps'], power['power_w']
assert len(cycles) == len(durations) == len(watts) == 12
assert abs(150e6 / (sum(cycles) / 12) - obs['throughput_at_150mhz']) < 1e-6
assert abs(sum(t * p * 1e-6 for t, p in zip(durations, watts)) / 12 - power['mean_energy_uj']) < 1e-7
assert abs(sum(obs[k] for k in ('fio_area_um2', 'np3_area_um2', 'shared_nonmacro_area_um2')) - obs['incremental_area_um2']) < 1e-6
for name, expected in provenance['evidence_figures'].items():
    assert hashlib.sha256((ROOT / 'assets' / name).read_bytes()).hexdigest() == expected, name

rows = [f'{i:02d} & {n} & {t / 1e6:.6f} & {p * 1000:.2f} & {p * t * 1e-6:.6f} ' + r'\\'
        for i, (n, t, p) in enumerate(zip(cycles, durations, watts))]
table = r'\begin{tabular}{rrrrr}\toprule' + '\n'
table += r'任务 & 周期 & 窗口（$\mu$s） & 功耗（mW） & 能耗（$\mu$J）\\\midrule' + '\n'
table += '\n'.join(rows) + '\n' + r'\bottomrule\end{tabular}' + '\n'
(ROOT / 'task_table.tex').write_text(table, encoding='utf-8')
(ROOT / 'task_rows.tex').write_text('\n'.join(rows) + '\n', encoding='utf-8')
print('PASS: identities, area sum, throughput/energy arithmetic, and five unchanged evidence figures.')
