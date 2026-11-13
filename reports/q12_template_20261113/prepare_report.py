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

# Derived chart inputs retain every recorded task and do not fit or smooth data.
import csv
synthetic = json.loads((ROOT / 'synthetic_observation.json').read_text(encoding='utf-8'))
tasks = synthetic['tasks']
assert len(tasks) == 12 and all(t['passed'] for t in tasks)
assert sum(t['cycles'] for t in tasks) / 12 == 25647.75
assert all(t['values'] == 25344 and t['output_writes'] == 9522 for t in tasks)
with (ROOT / 'synthetic_tasks.csv').open('w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['task', 'input_words', 'cycles'])
    writer.writerows((t['case'], t['input_words'], t['cycles']) for t in tasks)
rows = [f"{t['case']:02d} & {t['input_words']} & {t['cycles']} & {t['output_writes']} & {t['values']} & 通过 " + r'\\' for t in tasks]
table = r'\begin{tabular}{rrrrrl}\toprule' + '\n'
table += r'任务 & 输入字数 & 周期 & 输出写命令 & 核对值数 & 结果\\\midrule' + '\n'
table += '\n'.join(rows) + '\n' + r'\bottomrule\end{tabular}' + '\n'
(ROOT / 'synthetic_table.tex').write_text(table, encoding='utf-8')
with (ROOT / 'power_tasks.csv').open('w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['task', 'cycles', 'duration_us', 'power_mw', 'energy_uj'])
    writer.writerows((i, n, t/1e6, p*1000, p*t*1e-6) for i,(n,t,p) in enumerate(zip(cycles,durations,watts)))
assert 17 + 594 * 15 + (12 * 1583) // 32 == 9520
assert (12 * 1583) % 32 == 20
assert 6336 + 16384 == 22720
print('PASS: synthetic records, complete chart inputs, and final output index.')
