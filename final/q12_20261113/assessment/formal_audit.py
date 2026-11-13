"""Bind and conservatively assess exact full-SoC Formality evidence; no EDA launch."""
from pathlib import Path
import argparse, csv, hashlib, json, re

EXPECTED = {'RAMSP128X16': 30, 'RAMSP1024X16': 6, 'RAMSP4096X16': 80}
BASELINE_SHA256 = '07bc11f0d6301a7570979e70aca022f54845c8bab6468eae58f10ba94aa3a80e'
REPORTS = ['blackboxes_reference.rpt', 'blackboxes_implementation.rpt', 'matched.rpt',
           'unmatched.rpt', 'unmatched_black_boxes.rpt', 'status.rpt', 'failing.rpt',
           'aborted.rpt', 'unverified.rpt', 'unmatched_after_verify.rpt',
           'unmatched_black_boxes_after_verify.rpt', 'guidance.rpt', 'dont_verify.rpt',
           'constants.rpt', 'hdlin_mismatches.rpt']

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def bind_inputs(package, synth_directory, formal_directory, libraries):
    """Call immediately before fm_shell. All four library paths are required."""
    package, synth, formal = map(lambda x: Path(x).resolve(), [package, synth_directory, formal_directory])
    formal.mkdir(parents=True, exist_ok=True)
    identity_path = package / 'hardware/manifest.json'
    identity = json.loads(identity_path.read_text(encoding='utf-8'))
    if identity.get('soc_result_sha256') != BASELINE_SHA256:
        raise ValueError('Different behavioral candidate selected for proof')
    if identity.get('expected_macros') != EXPECTED:
        raise ValueError('Full SoC 30/6/80 macro inventory required')
    sources = {}
    for name, digest in identity['sources_sha256'].items():
        p = package / 'hardware' / name
        if sha(p) != digest:
            raise ValueError('Staged reference source changed: ' + name)
        sources[str(p)] = digest
    if len(libraries) != 4:
        raise ValueError('Exactly official TT standard-cell and three macro DBs required')
    names = [Path(p).name.lower() for p in libraries]
    if sum('scc40nll_vhsc40_rvt_tt' in x for x in names) != 1:
        raise ValueError('Official SCC40NLL RVT TT library missing')
    for macro in EXPECTED:
        if sum(x.startswith(macro.lower() + '_tt_') and x.endswith('.db') for x in names) != 1:
            raise ValueError('Official TT macro DB missing: ' + macro)
    artifacts = [synth / n for n in ['mapped.v', 'mapped.svf', 'macros_before.tsv', 'macros_mapped.tsv']]
    artifacts += [package / 'hardware/sources.tcl', identity_path]
    for p in artifacts:
        if not p.is_file() or not p.stat().st_size:
            raise ValueError('Missing required proof input: ' + str(p))
    record = {'scope': 'Exact staged complete SoC versus its single mapped netlist, SRAM internal behavior excluded',
              'top': 'qingyu_e203_soc_top', 'soc_result_sha256': identity['soc_result_sha256'],
              'reference_sources_sha256': sources,
              'artifacts_sha256': {str(p): sha(p) for p in artifacts},
              'libraries_sha256': {str(Path(p).resolve()): sha(p) for p in libraries},
              'expected_macros': EXPECTED,
              'no_manual_exceptions': True}
    dump(formal / 'input_binding.json', record)
    return record

def canonical(path):
    # DC change_names legalizes generate brackets/dots. Canonical collisions fail.
    return re.sub(r'_+', '_', re.sub(r'[^A-Za-z0-9_/]', '_', path.replace('\\', ''))).strip('_')

def inventory(path):
    with Path(path).open(encoding='utf-8') as f:
        rows = list(csv.DictReader(f, delimiter='\t'))
    result, counts = {}, dict.fromkeys(EXPECTED, 0)
    for row in rows:
        if set(row) != {'instance', 'reference', 'library_cell'}:
            raise ValueError('Unrecognized macro inventory columns')
        ref = row['reference']; key = canonical(row['instance'])
        if ref not in counts or key in result or '/' not in row['library_cell']:
            raise ValueError('Unknown macro, canonical collision or unresolved library cell')
        counts[ref] += 1
        result[key] = ref
    if counts != EXPECTED:
        raise ValueError('Wrong full-SoC macro counts: ' + str(counts))
    return result

def boxes(text, side):
    prefix = side + ':/WORK/qingyu_e203_soc_top/'
    paths = re.findall(re.escape(prefix) + r'([^\s]+)', text)
    # Lists from report_black_boxes include each qualified instance on its line.
    if not paths:
        raise ValueError('No recognizable qualified SRAM box instances')
    distinct = set(p.rstrip(',;') for p in paths)
    normalized = {canonical(p) for p in distinct}
    if len(normalized) != len(distinct):
        raise ValueError('Ambiguous canonical blackbox name collision')
    all_qualified = set(re.findall(r'[ri]:/[^\s]+', text))
    if any(not x.startswith(prefix) for x in all_qualified):
        raise ValueError('Unexpected blackbox design/container')
    return normalized

def zero_points(text, category):
    if re.search(r'before matching', text, re.I):
        return False
    if re.search(r'\bNo\s+' + category + r'\s+(?:compare\s+)?points\b', text, re.I):
        return True
    lines = re.findall(r'^\s*(\d+)\s+' + category + r'\s+(?:compare\s+)?points\s*$', text, re.I | re.M)
    return len(lines) == 1 and int(lines[0]) == 0

def audit(formal_directory, synth_directory, log_path=None):
    formal, synth = Path(formal_directory), Path(synth_directory)
    log = Path(log_path) if log_path else formal / 'fm.log'
    result = {'accepted': False, 'status': 'INCOMPLETE_OR_REVIEW_REQUIRED',
              'scope': 'RTL-to-mapped complete qingyu_e203_soc_top at symmetric official SRAM blackbox boundaries; not SRAM internal equivalence',
              'reasons': [], 'reports_sha256': {}}
    reasons = result['reasons']
    binding_file = formal / 'input_binding.json'
    try:
        binding = json.loads(binding_file.read_text(encoding='utf-8'))
        if binding.get('soc_result_sha256') != BASELINE_SHA256:
            raise ValueError('Different candidate in proof binding')
        for group in ['reference_sources_sha256', 'artifacts_sha256', 'libraries_sha256']:
            for name, digest in binding[group].items():
                if sha(name) != digest:
                    raise ValueError('Proof input changed during run: ' + name)
        result['input_binding_sha256'] = sha(binding_file)
        result['soc_result_sha256'] = binding['soc_result_sha256']
    except Exception as e:
        reasons.append('Input binding: ' + str(e))
    reports = {}
    for name in REPORTS:
        p = formal / name
        if not p.is_file() or not p.stat().st_size:
            reasons.append('Missing report: ' + name)
        else:
            reports[name] = p.read_text(encoding='utf-8', errors='replace')
            result['reports_sha256'][name] = sha(p)
    text = log.read_text(encoding='utf-8', errors='replace') if log.is_file() else ''
    if not text:
        reasons.append('Missing Formality console log')
    else:
        result['console_sha256'] = sha(log)
    if not re.search(r'^Q12_FORMAL_VERIFY_RETURN=1\s*$', text, re.M):
        reasons.append('verify did not return 1')
    if not re.search(r'^Q12_FORMAL_REPORT_ERRORS=0\s*$', text, re.M):
        reasons.append('Diagnostic report command failure/incompletion')
    if 'Q12_FINAL_FORMAL_COMPLETE' not in text or 'Verification SUCCEEDED' not in text:
        reasons.append('No completed successful verification')
    diagnostics = re.findall(r'^\s*(?:Error:|Fatal:|Q12_FINAL_FORMAL_FAILED:|Q12_FORMAL_REPORT_ERROR=|Q12_FORMAL_VERIFY_EXCEPTION=).+$', text, re.M)
    if diagnostics:
        result['tool_errors'] = diagnostics
        reasons.append('Tool errors require review')
    for name, category in [('failing.rpt', 'failing'), ('aborted.rpt', 'aborted'), ('unverified.rpt', 'unverified'),
                           ('unmatched_after_verify.rpt', 'unmatched'), ('unmatched_black_boxes_after_verify.rpt', 'unmatched')]:
        if not zero_points(reports.get(name, ''), category):
            reasons.append('Nonzero or unrecognized ' + category + ' report: ' + name)
    status = reports.get('status.rpt', '')
    passing = re.findall(r'^\s*(\d+) Passing compare points\s*$', status, re.M | re.I)
    if len(passing) != 1 or int(passing[0]) <= 0:
        reasons.append('Passing comparison count unavailable or zero')
    else:
        result['passing_compare_points'] = int(passing[0])
    constant_regs = re.findall(r'^\s*Constant reg\s+(.+)$', status, re.M)
    result['internal_constant_register_rows'] = constant_regs
    if not re.search(r"Don't verify points:\s*None\b", reports.get('dont_verify.rpt', ''), re.I):
        reasons.append('Dont-verify exclusions present or report unrecognized')
    if not re.search(r'User Defined Constants:\s*None\b', reports.get('constants.rpt', ''), re.I):
        reasons.append('User constants present or report unrecognized')
    hdlin = reports.get('hdlin_mismatches.rpt', '')
    clean_hdlin = bool(re.search(r'\bNo\s+(?:HDL(?:IN)?\s+)?(?:interpretation\s+)?mismatches\b|\b0\s+(?:HDL(?:IN)?\s+)?mismatches\b', hdlin, re.I))
    interpretation = re.findall(r'^.*(?:RTL interpretation messages|Verification results may disagree|Warning:.*(?:HDL|FMR)).*$', text, re.M | re.I)
    result['rtl_interpretation_diagnostics'] = interpretation
    if not clean_hdlin or interpretation:
        reasons.append('HDL interpretation/mismatch report requires review')
    try:
        before = inventory(synth / 'macros_before.tsv')
        mapped = inventory(synth / 'macros_mapped.tsv')
        if before != mapped:
            raise ValueError('Reference-to-mapped macro path/type inventory differs')
        rboxes = boxes(reports['blackboxes_reference.rpt'], 'r')
        iboxes = boxes(reports['blackboxes_implementation.rpt'], 'i')
        if rboxes != set(before) or iboxes != set(mapped) or len(rboxes) != 116:
            raise ValueError('FM boxes not exactly the same 116 mapped SRAM instances')
        result['symmetric_sram_boundary'] = {'verified': True, 'counts': EXPECTED, 'instances': 116,
                                             'internal_memory_behavior_proved': False}
    except Exception as e:
        reasons.append('Macro/blackbox scope: ' + str(e))
    result['accepted'] = not reasons
    result['status'] = 'PASS_AT_SYMMETRIC_SRAM_BOUNDARY' if not reasons else 'INCOMPLETE_OR_REVIEW_REQUIRED'
    dump(formal / 'formal_audit.json', result)
    return result

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('formal_directory', type=Path)
    ap.add_argument('synth_directory', type=Path)
    ap.add_argument('--log', type=Path)
    a = ap.parse_args()
    value = audit(a.formal_directory, a.synth_directory, a.log)
    print(json.dumps(value, indent=2))
    raise SystemExit(0 if value['accepted'] else 2)

if __name__ == '__main__':
    main()
