"""Inventory optimized RTL structures, with no process mapping or PPA claim."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import argparse, hashlib, json, re, subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SV2V = Path('/opt/qingyu-tools/sv2v-0.0.13/sv2v-Linux/sv2v')
SV2V_SHA = 'b80a8ac6212aa72a196d9d6129cda35f16dbfa799ec61848c46321f845b6b635'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def number(value):
    return int(value, 2) if isinstance(value, str) else int(value)

def inventory(design, top):
    modules = design['modules']
    types, ff, memories, multipliers, macros = Counter(), Counter(), Counter(), Counter(), Counter()
    def visit(name, instances=1, ancestors=()):
        assert name not in ancestors, 'Recursive hierarchy'
        for cell in modules[name]['cells'].values():
            kind, params = cell['type'], cell['parameters']
            if kind in modules:
                mod = modules[kind]
                if number(mod.get('attributes', {}).get('blackbox', 0)):
                    macros[kind] += instances
                else:
                    visit(kind, instances, ancestors + (name,))
            else:
                types[kind] += instances
                if re.match(r'^\$(?:a|s)?dff', kind):
                    ff[kind] += instances * number(params['WIDTH'])
                if kind == '$mem_v2':
                    memories[f'{number(params["SIZE"])}x{number(params["WIDTH"])}'] += instances
                if kind == '$mul':
                    spec = f'A{number(params["A_WIDTH"])}xB{number(params["B_WIDTH"])}_Y{number(params["Y_WIDTH"])}'
                    multipliers[spec] += instances
                assert not re.match(r'^\$(?:a)?dlatch', kind), 'Unexpected inferred latch'
    visit(top)
    return {'rtl_cells_by_type': dict(sorted(types.items())),
            'flip_flop_bits_by_type': dict(sorted(ff.items())), 'flip_flop_bits': sum(ff.values()),
            'unmapped_memories_count_by_geometry': dict(sorted(memories.items())),
            'multipliers_count_by_geometry': dict(sorted(multipliers.items())),
            'blackbox_macro_instances': dict(sorted(macros.items())),
            'macro_storage_bits': sum(macros.get(f'RAMSP{n}X16', 0)*n*16 for n in [128,1024,4096])}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', nargs='+', default=['core8','core9','encoder','bounded_encoder','decoder','bounded_decoder'])
    args = parser.parse_args()
    choices = {
        'core8': ('experiments/arithmetic/winograd_task8_prefetch','winograd_int8_task8.sv','winograd_int8_task8'),
        'core9': ('experiments/arithmetic/winograd_task9','winograd_int8_task8.sv','winograd_int8_task8'),
        'encoder': ('experiments/codec/rice32','rice32_encoder.sv','rice32_encoder'),
        'bounded_encoder': ('experiments/codec/rice32_bounded','rice32_encoder.sv','rice32_encoder'),
        'decoder': ('experiments/codec/rice32','rice32_decoder.sv','rice32_decoder'),
        'bounded_decoder': ('experiments/codec/rice32_bounded','rice32_decoder.sv','rice32_decoder')}
    assert all(c in choices for c in args.cases)
    assert sha(SV2V) == SV2V_SHA
    out = ROOT/'build/int8_structure'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True)
    report = {'passed':False, 'schema':'qingyu-int8-rtl-structure-inventory-v1',
              'script_sha256':sha(Path(__file__)), 'sv2v_path':str(SV2V), 'sv2v_sha256':SV2V_SHA,
              'sv2v_version':subprocess.check_output([SV2V,'--version'],text=True).strip(),
              'yosys_version':subprocess.check_output(['yosys','-V'],text=True).strip(), 'preprocessor_defines':['SYNTHESIS'],
              'limits':['Optimized RTLIL structural inventory, not technology-mapped gates or physical area.',
                        'Memory macro bodies are intentional interface blackboxes; their power/timing/area are unknown.',
                        'Converter/generic optimizer equivalence is not signed off; no netlist is promoted to physical implementation.',
                        'No STA, whole-SoC energy or official-loader performance claim.'], 'results':[]}
    def save(): (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    save(); print(out,flush=True)
    try:
        for name in args.cases:
            folder, filename, top = choices[name]
            manifest_path = ROOT/folder/'SOURCE_SHA256.json'
            manifest = json.loads(manifest_path.read_text())
            for relative,digest in manifest['files'].items():
                assert sha(manifest_path.parent/relative)==digest
            for relative,digest in manifest.get('external_dependencies',{}).items():
                assert sha(ROOT/relative)==digest
            sources = [ROOT/folder/filename]
            if name.startswith('core'):
                sources += [ROOT/'experiments/arithmetic/winograd_array8/winograd_int8_pair_acc32.sv',
                            ROOT/'rtl/asic/qingyu_sram16.sv', HERE/'sram_blackboxes.v']
            before = {str(s.relative_to(ROOT)):sha(s) for s in sources}
            case = out/name; case.mkdir()
            converted = case/'converted.v'
            with converted.open('w') as dest, (case/'conversion.log').open('w') as log:
                subprocess.run([SV2V,'-DSYNTHESIS',*sources],stdout=dest,stderr=log,check=True,timeout=120)
            script = case/'inventory.ys'
            script.write_text(f'read_verilog {converted}\nhierarchy -check -top {top}\nproc\nopt\nwreduce\nopt\nmemory_collect\nopt_clean\ncheck -assert\nstat -width\nwrite_json {case / "structure.json"}\n')
            with (case/'yosys.log').open('w') as log:
                subprocess.run(['yosys','-Q','-T','-s',script],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
            assert before == {str(s.relative_to(ROOT)):sha(s) for s in sources}
            data=json.loads((case/'structure.json').read_text())
            item={'name':name,'source_manifest_sha256':sha(manifest_path),'sources_sha256':before,
                  **inventory(data,top),'artifacts_sha256':{p.name:sha(p) for p in case.iterdir() if p.is_file()},
                  'warnings':[line for line in (case/'yosys.log').read_text().splitlines() if line.startswith('Warning:')]}
            report['results'].append(item); save()
            print(json.dumps({k:v for k,v in item.items() if k not in ['warnings','artifacts_sha256','sources_sha256','rtl_cells_by_type']}),flush=True)
        report['passed']=True; save(); print('PASS '+str(out/'result.json'),flush=True)
    except Exception as error:
        report['error']=str(error);save();raise

if __name__=='__main__': main()
