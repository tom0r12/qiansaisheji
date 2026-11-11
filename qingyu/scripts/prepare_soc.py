"""Generate auditable adapters around the unchanged official E203 source."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/e203_hbirdv2'
OUT = ROOT / 'generated'

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'upstream pattern mismatch: {old[:80]!r}')
    return text.replace(old, new, 1)

def main():
    OUT.mkdir(exist_ok=True)
    sources = {}
    for stem in ('e203_subsys_main', 'e203_subsys_top', 'e203_soc_top'):
        folder = 'soc' if stem == 'e203_soc_top' else 'subsys'
        path = VENDOR / f'rtl/e203/{folder}/{stem}.v'
        data = path.read_bytes()
        sources[str(path.relative_to(VENDOR))] = hashlib.sha256(data).hexdigest()
        text = data.decode('utf-8')
        qname = 'qingyu_' + stem
        ports = ('output wire qingyu_bus_clk, output wire qingyu_bus_rst_n,\n'
                 if stem != 'e203_soc_top' else
                 'output wire qingyu_host_valid, output wire [31:0] qingyu_host_code,\n')
        text = replace_once(text, f'module {stem}(', f'module {qname}(\n  {ports}')
        if stem == 'e203_subsys_main':
            text = replace_once(text, f'module {qname}(',
                f'module {qname} #(parameter [31:0] QINGYU_RESET_VECTOR=32\'h80000000)(')
            text = replace_once(text, '.pc_rtvec        (pc_rtvec)',
                '.pc_rtvec        (QINGYU_RESET_VECTOR)')
            text = replace_once(text, 'endmodule',
                'assign qingyu_bus_clk = hfclk;\n'
                'assign qingyu_bus_rst_n = main_rst_n;\nendmodule')
        elif stem == 'e203_subsys_top':
            text = replace_once(text, 'e203_subsys_main  u_e203_subsys_main(',
                'qingyu_e203_subsys_main u_e203_subsys_main(\n'
                ' .qingyu_bus_clk(qingyu_bus_clk),\n'
                ' .qingyu_bus_rst_n(qingyu_bus_rst_n),')
        else:
            text = '`include "e203_defines.v"\n' + text
            text = replace_once(text, 'e203_subsys_top u_e203_subsys_top(',
                'wire qingyu_bus_clk, qingyu_bus_rst_n;\n'
                'qingyu_e203_subsys_top u_e203_subsys_top(\n'
                ' .qingyu_bus_clk(qingyu_bus_clk),\n'
                ' .qingyu_bus_rst_n(qingyu_bus_rst_n),')
            for bus in ('sysfio', 'sysmem'):
                for signal in ('cmd_read', 'cmd_addr', 'cmd_wdata', 'cmd_wmask'):
                    import re
                    pattern = rf'\.{bus}_icb_{signal}\s*\(\s*\)'
                    text, count = re.subn(pattern, f'.{bus}_icb_{signal}({bus}_icb_{signal})', text)
                    if count != 1:
                        raise ValueError(pattern)
                text = replace_once(text, f'.{bus}_icb_rsp_valid({bus}_icb_cmd_valid)',
                    f'.{bus}_icb_rsp_valid({bus}_icb_rsp_valid)')
                text = replace_once(text, f'.{bus}_icb_rsp_ready({bus}_icb_cmd_ready)',
                    f'.{bus}_icb_rsp_ready({bus}_icb_rsp_ready)')
                import re
                for signal, constant in [('rsp_err', "1'b0"), ('rsp_rdata', "32'b0")]:
                    pattern = rf'\.{bus}_icb_{signal}\s*\(\s*{constant}\s*\)'
                    text, count = re.subn(pattern, f'.{bus}_icb_{signal}({bus}_icb_{signal})', text)
                    if count != 1:
                        raise ValueError(pattern)
            declarations = ''
            instances = ''
            for bus, endpoint in [('sysmem', 'qingyu_shared_sram'), ('sysfio', 'qingyu_fio')]:
                declarations += (f'wire {bus}_icb_cmd_read, {bus}_icb_rsp_valid, {bus}_icb_rsp_ready, {bus}_icb_rsp_err;\n'
                    f'wire [31:0] {bus}_icb_cmd_addr, {bus}_icb_cmd_wdata, {bus}_icb_rsp_rdata;\n'
                    f'wire [3:0] {bus}_icb_cmd_wmask;\n')
                instances += f'{endpoint} u_{"shared" if bus == "sysmem" else "fio"}(\n .clk(qingyu_bus_clk), .rst_n(qingyu_bus_rst_n),\n'
                signals = ['cmd_valid','cmd_ready','cmd_read','cmd_addr','cmd_wdata','cmd_wmask',
                           'rsp_valid','rsp_ready','rsp_err','rsp_rdata']
                original_ports=',\n'.join(f' .icb_{s}({bus}_icb_{s})' for s in signals)
                if bus=='sysmem':
                    for sig in signals:
                        width='[31:0] ' if sig in ('cmd_addr','cmd_wdata','rsp_rdata') else '[3:0] ' if sig=='cmd_wmask' else ''
                        declarations+=f'`ifdef QINGYU_BLOCK_COPY\nwire {width}block_mem_{sig};\n`endif\n'
                    ports=',\n'.join(f' .icb_{s}(block_mem_{s})' for s in signals)
                    instances+='\n`ifdef QINGYU_BLOCK_COPY\n'+ports+'\n`else\n'+original_ports+'\n`endif\n'
                else:
                    extra=',\n'.join(f' .{side}_{s}({net}_{s})' for side,net in [('cpu','sysmem_icb'),('mem','block_mem')] for s in signals)
                    instances+='\n`ifdef QINGYU_BLOCK_COPY\n'+extra+',\n`endif\n'+original_ports
                if bus == 'sysfio':
                    instances += ',\n .host_valid(qingyu_host_valid), .host_code(qingyu_host_code)'
                instances += '\n);\n'
            # Declare bus widths before their first instance connection. Some
            # tool flows otherwise elaborate the connection as an implicit
            # scalar net before reaching the later vector declaration.
            text = replace_once(text, 'wire qingyu_bus_clk, qingyu_bus_rst_n;',
                declarations + 'wire qingyu_bus_clk, qingyu_bus_rst_n;')
            text = replace_once(text, 'endmodule', instances + '\nendmodule')
        (OUT / f'{qname}.v').write_text(text, encoding='utf-8')
    (OUT / 'upstream_sources.json').write_text(json.dumps(sources, indent=2), encoding='utf-8')
    print('Generated E203 SoC adapters; original vendor files unchanged.')

if __name__ == '__main__':
    main()
