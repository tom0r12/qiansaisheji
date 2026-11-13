"""Fail-closed area, timing, power-unit and annotation acceptance."""
from pathlib import Path
import csv,math,re
NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
def finite(value):
    x=float(value)
    if not math.isfinite(x):raise ValueError('Nonfinite scalar')
    return x
def one(pattern,text,label):
    m=re.findall(pattern,text,re.M|re.I)
    if len(m)!=1:raise ValueError('Missing/ambiguous '+label)
    return m[0]
def macro_rows(path):
    with path.open()as f:rows=list(csv.reader(f,delimiter='\t'))
    if rows.pop(0)!=['instance','reference','library_cell']:raise ValueError('Malformed macro header')
    counts={'RAMSP128X16':0,'RAMSP1024X16':0,'RAMSP4096X16':0};seen=set()
    for row in rows:
        if len(row)!=3 or row[0]in seen or row[1]not in counts or '/'not in row[2]:raise ValueError('Malformed/unresolved macro inventory')
        seen.add(row[0]);counts[row[1]]+=1
    if counts!={'RAMSP128X16':30,'RAMSP1024X16':6,'RAMSP4096X16':80}:raise ValueError('Wrong memory inventory')
    return rows
def synth(directory):
    for n in ['mapped.v','mapped.ddc','mapped.sdc','mapped.svf','area.rpt','timing_max.rpt','timing_min.rpt','units.rpt','libraries.rpt','check_design_after.rpt','check_timing_after.rpt','explicit_area_summary.txt','q12_explicit_area_leaves.tsv']:
        if not (directory/n).is_file() or not (directory/n).stat().st_size:raise ValueError('Missing synthesis evidence '+n)
    macro_rows(directory/'macros_mapped.tsv')
    parts={k:finite(v) for k,v in re.findall(r'^([A-Z0-9_]+)=('+NUMBER+r')$',(directory/'explicit_area_summary.txt').read_text(),re.M)}
    required={'FULL_SOC_LIBRARY_AREA','FIO_LIBRARY_AREA','NP3_ARBITER_LIBRARY_AREA','SHARED_NONMACRO_LIBRARY_AREA','FIXED_SHARED_MACRO_LIBRARY_AREA','INCREMENTAL_LIBRARY_AREA'}
    if not required.issubset(parts) or any(parts[k]<=0 for k in required):raise ValueError('Missing/invalid area decomposition')
    expected=sum(parts[k] for k in ['FIO_LIBRARY_AREA','NP3_ARBITER_LIBRARY_AREA','SHARED_NONMACRO_LIBRARY_AREA'])
    if abs(expected-parts['INCREMENTAL_LIBRARY_AREA'])>0.01:raise ValueError('Area double counted or missing')
    with (directory/'q12_explicit_area_leaves.tsv').open()as f:rows=list(csv.reader(f,delimiter='\t'))[1:]
    if not rows or any(len(r)!=4 for r in rows):raise ValueError('Malformed area leaves')
    summed=sum(finite(r[2])for r in rows)
    report=finite(one(r'Total cell area:\s*('+NUMBER+r')',(directory/'area.rpt').read_text(),'total area'))
    if abs(summed-parts['FULL_SOC_LIBRARY_AREA'])>0.1 or abs(report-summed)>max(0.1,summed*1e-6):raise ValueError('Leaf/full/report area differs')
    setup=re.findall(r'slack\s*\([^)]*\)\s*('+NUMBER+r')',(directory/'timing_max.rpt').read_text())
    hold=re.findall(r'slack\s*\([^)]*\)\s*('+NUMBER+r')',(directory/'timing_min.rpt').read_text())
    if not setup or not hold:raise ValueError('Missing timing diagnostic')
    return {'mapping_complete':True,'area_library_units':parts,'area_unit_status':'library-native area; explicit physical-unit confirmation required before mm2',
            'worst_reported_setup_ns':min(map(finite,setup)),'worst_reported_hold_ns':min(map(finite,hold)),
            'timing_signoff':False,'timing_scope':'TT prelayout diagnostic, ideal clocks, assumed I/O; no corner closure or route parasitics'}
POWER={'W':1.0,'mW':1e-3,'uW':1e-6,'nW':1e-9,'pW':1e-12}
def power_value(report,units):
    # Prefer an explicit unit on Total Power; otherwise require exactly one
    # recognized power scale in report_units. Never guess from magnitude.
    match=one(r'^\s*Total Power\s*=\s*('+NUMBER+r')\s*([munp]?W)?(?:\s|$)',report,'total power')
    value=finite(match[0]);suffix=match[1]
    if value<0:raise ValueError('Negative power')
    declared=re.findall(r'(?:Power\s+[Uu]nits?|[Pp]ower\s*:)\s*[:=]?\s*('+NUMBER+r')\s*([munp]?W)\b',units)
    if suffix:
        if suffix not in POWER:raise ValueError('Unknown power suffix')
        return value*POWER[suffix]
    if not declared:raise ValueError('Unknown report power unit')
    scales={finite(scale)*POWER[unit]for scale,unit in declared}
    if len(scales)!=1:raise ValueError('Conflicting dynamic/leakage power units')
    return value*scales.pop()
def power(directory,duration_ps):
    report=(directory/'power.rpt').read_text(errors='replace');units=(directory/'power_units.rpt').read_text(errors='replace')
    watts=power_value(report,units)
    # Full report retained even if this PT release lacks provenance attributes.
    # Coverage thresholds are an engineering gate, not an official criterion.
    with (directory/'macro_pin_activity.tsv').open()as f:rows=list(csv.DictReader(f,delimiter='\t'))
    macros=set();unqualified=[]
    for r in rows:
        if set(r)!={'instance','pin','direction','toggle_rate','static_probability','toggle_source','probability_source'}:raise ValueError('Malformed macro activity table')
        macros.add(r['instance'])
        try:
            rate=finite(r['toggle_rate']);prob=finite(r['static_probability'])
            if rate<0 or not 0<=prob<=1:raise ValueError()
        except ValueError:unqualified.append(r['pin']);continue
        sources=(r['toggle_source']+' '+r['probability_source']).lower()
        if any(x in sources for x in ['unknown','default','unannotated']) or not all(re.search(r'saif|file|propagat|constant|user|implied|clock',r[k],re.I) for k in ['toggle_source','probability_source']):unqualified.append(r['pin'])
    if len(macros)!=116 or unqualified:raise ValueError('Macro activity provenance incomplete: macros=%d pins=%d missing=%s'%(len(macros),len(unqualified),unqualified[:5]))
    activity=(directory/'activity_after.rpt').read_text(errors='replace')
    # Preserve release-specific tables verbatim. A report with no recognized
    # explicit fraction remains unqualified rather than inventing a percentage.
    fractions=re.findall(r'\b(?:annotated|annotation coverage)\b[^\n]*?('+NUMBER+r')\s*%',activity,re.I)
    if not fractions or any(not 0<=finite(x)<=100 for x in fractions):raise ValueError('Unrecognized switching-activity coverage format')
    coverage=min(map(finite,fractions))
    if coverage<100:raise ValueError('Incomplete annotation needs category-specific review: '+str(coverage))
    check=(directory/'check_power.rpt').read_text(errors='replace')
    if re.search(r'^\s*(?:Error:|Warning:)',check,re.M):raise ValueError('check_power diagnostics require review')
    return {'power_w':watts,'energy_uj':watts*duration_ps*1e-6,'duration_ps':duration_ps,
            'macro_input_activity_rows':len(rows),'coverage_percent':coverage,
            'scope':'Exact-window full-SoC TT prelayout RTL-SAIF estimate; not silicon measurement or official acceptance'}
