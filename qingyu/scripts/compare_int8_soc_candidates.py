"""Compare two frozen real-E203 diagnostic corpora without changing acceptance scope."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load_verified(relative):
    path=ROOT/relative;data=json.loads(path.read_text())
    assert data['passed'] and data['tasks']==72
    for row in data['runs']:
        report_path=ROOT/row['result'];assert sha(report_path)==row['result_sha256']
        report=json.loads(report_path.read_text());assert report['passed'] and report['sample_index']==row['sample_index']
        assert row['metrics']==[r['metrics'] for r in report['layers']]
        for layer in report['layers']:
            assert sha(ROOT/layer['simulation_log'])==layer['simulation_log_sha256']
        assert sha(ROOT/report['simulator_path'])==report['simulator_sha256']
        for name,digest in report['sources_sha256'].items():assert sha(ROOT/name)==digest
        for name,digest in report['firmware_sources_sha256'].items():assert sha(ROOT/name)==digest
    return data,sha(path)

def main():
    first='build/int8soc_corpus/20261111T174454919053Z/result.json'
    second='build/int8soc_corpus/20261111T175642268453Z/result.json'
    a,ah=load_verified(first);b,bh=load_verified(second)
    assert a['corpus_manifest_sha256']==b['corpus_manifest_sha256']
    result={'schema':'qingyu-int8-real-soc-core-comparison-v1','passed':False,
            'reports':{first:ah,second:bh},'comparison_script_sha256':sha(Path(__file__)),
            'core8':'experiments/arithmetic/winograd_task8_prefetch',
            'core9':'experiments/arithmetic/winograd_task9',
            'common_engine':'experiments/integration/int8stream_dual',
            'common_codec':'experiments/codec/rice32_bounded','tasks_per_candidate':72,
            'samples':[], 'limits':['Source preload excluded; real CPU setup through final output-marker ACK only.',
                 'Diagnostic selection includes generated silence and traffic extreme, not an unbiased population mean.',
                 '150MHz remains unqualified by process STA; no measured new area/energy.',
                 'Ideal serialized loader bounds add at least one cycle per source word; actual loader overhead can be greater.'],
            'acceptance':{'throughput_tasks_s_min_exclusive':10450,'area_mm2_max':0.5,'energy_uj_max':6.3,
                          'official_loader_measured':False,'physical_area_measured':False,'whole_soc_energy_measured':False,'satisfied':False}}
    for p,q in zip(a['runs'],b['runs']):
        assert p['sample_index']==q['sample_index']
        ac=[v['cpu_setup_to_ack'] for v in p['metrics']];bc=[v['cpu_setup_to_ack'] for v in q['metrics']]
        for u,v in zip(p['metrics'],q['metrics']):
            assert all(u[k]==v[k] for k in ['layer','reads','writes','commands','responses','macro_reads','macro_writes'])
        am,bm=sum(ac)/12,sum(bc)/12
        result['samples'].append({'sample_index':p['sample_index'],'core8_mean_cpu_cycles':am,'core9_mean_cpu_cycles':bm,
            'mean_cycles_saved':am-bm,'cycle_reduction_percent':100*(am-bm)/am,
            'paired_saved_cycles':[u-v for u,v in zip(ac,bc)],
            'core8_serialized_ideal_loader_plus_cpu_mean':sum(v['reads']+v['cpu_setup_to_ack'] for v in p['metrics'])/12,
            'core9_serialized_ideal_loader_plus_cpu_mean':sum(v['reads']+v['cpu_setup_to_ack'] for v in q['metrics'])/12})
    am=a['diagnostic_mean_cpu_setup_to_ack'];bm=b['diagnostic_mean_cpu_setup_to_ack']
    result['diagnostic_summary']={'core8_mean_cpu_cycles':am,'core9_mean_cpu_cycles':bm,'mean_cycles_saved':am-bm,
         'cycle_reduction_percent':100*(am-bm)/am,'conditional_same_clock_throughput_gain_percent':100*(am/bm-1)}
    speech=[r for r in result['samples'] if r['sample_index']!=9]
    sa=sum(r['core8_mean_cpu_cycles'] for r in speech)/5;sb=sum(r['core9_mean_cpu_cycles'] for r in speech)/5
    result['posthoc_non_generated_silence_description']={'selection':'Exclude the preregistered generated silence control sample9 only; descriptive, no design fitting',
        'core8_mean_cpu_cycles':sa,'core9_mean_cpu_cycles':sb,'mean_cycles_saved':sa-sb,'cycle_reduction_percent':100*(sa-sb)/sa}
    result['passed']=True
    target=ROOT/'docs/evidence/20261112_int8_core8_core9_soc_comparison.json'
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(target);print(json.dumps(result['diagnostic_summary']))

if __name__=='__main__':main()
