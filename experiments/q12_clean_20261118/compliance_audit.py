"""Compliance audit of a local clean-variant run (static source checks).

python compliance_audit.py runs/<run_dir> [...]
Checks:
 1. Every staged source whose file name exists in the pinned upstream E203
    (qingyu/vendor/e203_hbirdv2) is byte-identical to upstream, except the
    explicitly listed project integration files.
 2. No entropy-coding / read-ahead / loader / mailbox / output-compression
    modules are instantiated or compiled.
 3. Shared SRAM has exactly one ICB slave instance, driven only by the original
    sysmem_icb port of the unmodified e203_subsys_mems.
 4. Bus width: ICB data/address 32 bits at the shared SRAM and DMA ports.
 5. The original memory fabric allows zero-cycle responses (ALLOW_0CYCL_RSP=1)
    and keeps SPLT_FIFO_OUTS_NUM=1 (unchanged platform limits).
"""
from pathlib import Path
import hashlib, json, re, sys
HERE = Path(__file__).resolve().parent
WORK = HERE.parents[2]
UP = WORK / 'qingyu/vendor/e203_hbirdv2/rtl/e203'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
norm = lambda p: Path(p).read_bytes().replace(b'\r\n', b'\n')
INTEGRATION = {  # project-owned integration copies of upstream subsystem files
    'qingyu_e203_soc_top.v', 'qingyu_e203_subsys_top.v', 'qingyu_e203_subsys_main.v', 'config.v'}
FORBIDDEN = [r'\brice\b', r'q12_rice_decoder', r'read_ahead', r'readcache', r'\bloader\b', r'mailbox', r'q13_rice_encoder', r'delta_decode']


def logical(n):
    m = re.match(r'^\d{3}_(.+)$', n); return m.group(1) if m else n


def audit(run):
    run = Path(run)
    srcs = [Path(l.strip()) for l in (run / 'sources.f').read_text().splitlines() if l.strip() and not l.startswith('+incdir')]
    upstream = {}
    for p in UP.rglob('*.v'): upstream.setdefault(p.name, []).append(p)
    identical, differing, project = [], [], []
    for s in srcs:
        name = logical(s.name)
        if name in upstream and name not in INTEGRATION:
            if any(norm(s) == norm(u) for u in upstream[name]): identical.append(name)
            else: differing.append(name)
        else: project.append(name)
    texts = {logical(s.name): s.read_text(errors='replace') for s in srcs}
    hw = {k: v for k, v in texts.items() if not k.startswith('tb_') and k != 'q12_gpio_source.sv'}
    forbidden = []
    for k, v in hw.items():
        code = re.sub(r'//[^\n]*', '', v)
        for pat in FORBIDDEN:
            if re.search(pat, code, re.I): forbidden.append((k, pat))
    top = texts['qingyu_e203_soc_top.v']
    shared_inst = re.findall(r'qingyu_shared_sram\s+(\w+)\s*\(', top)
    m = re.search(r'qingyu_shared_sram\s+u_shared\s*\((.*?)\);', top, re.S)
    conn = dict(re.findall(r'\.(\w+)\(([^)]*)\)', m.group(1))) if m else {}
    shared_ok = len(shared_inst) == 1 and all(v.strip().startswith('sysmem_icb_') or k in ('clk', 'rst_n') for k, v in conn.items())
    other_users = [k for k, v in hw.items() if k != 'qingyu_e203_soc_top.v' and re.search(r'\bu_shared\b', re.sub(r'//[^\n]*', '', v))]
    mems = texts['e203_subsys_mems.v']; bus = texts['sirv_icb1to8_bus.v']
    fabric = {'subsys_mems_identical_upstream': 'e203_subsys_mems.v' in identical,
              'SPLT_FIFO_OUTS_NUM_1': bool(re.search(r'\.SPLT_FIFO_OUTS_NUM\s*\(1\)', mems)),
              'ALLOW_0CYCL_RSP_1_in_original_icb1to8': bool(re.search(r'\.ALLOW_0CYCL_RSP\s*\(1\)', bus)),
              'icb1to8_identical_upstream': 'sirv_icb1to8_bus.v' in identical}
    widths = {'shared_addr32_data32': bool(re.search(r'input wire \[31:0\] icb_cmd_addr, icb_cmd_wdata', texts['qingyu_shared_sram.sv'])),
              'dma_port32': bool(re.search(r'wire \[31:0\] dma_icb_cmd_addr|input wire \[31:0\] dma_icb_cmd_addr', top + texts['qingyu_e203_subsys_main.v']))}
    res = {'run': str(run), 'upstream_identical_count': len(identical), 'upstream_named_but_modified': differing,
           'project_or_integration_files': project, 'forbidden_hits': forbidden,
           'shared_sram_single_instance_on_original_sysmem_icb': shared_ok, 'shared_sram_connections': conn,
           'other_modules_referencing_u_shared': other_users, 'fabric': fabric, 'widths': widths}
    res['passed'] = (not differing and not forbidden and shared_ok and not other_users and all(fabric.values()) and all(widths.values()))
    return res


if __name__ == '__main__':
    out = [audit(r) for r in sys.argv[1:]]
    for r in out:
        print(json.dumps({k: r[k] for k in ['run', 'passed', 'upstream_identical_count', 'upstream_named_but_modified', 'forbidden_hits',
                                           'shared_sram_single_instance_on_original_sysmem_icb', 'other_modules_referencing_u_shared', 'fabric', 'widths']}, ensure_ascii=False, indent=1))
        print('project/integration files:', r['project_or_integration_files'])
    (HERE / 'compliance_audit.json').write_text(json.dumps(out, indent=1, ensure_ascii=False))
