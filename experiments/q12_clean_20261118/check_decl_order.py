"""Heuristic declare-before-use checker for project SV/V files (VCS/DC strictness).
python check_decl_order.py file...   -> lists identifiers used on a line before
their declaration line within the same module."""
import re, sys, pathlib
KW = set('''module endmodule input output inout wire reg logic integer genvar parameter localparam assign always always_ff always_comb
begin end if else case endcase default for function endfunction automatic task endtask generate endgenerate posedge negedge or and not
signed unsigned initial int bit byte typedef enum struct packed return while repeat forever fork join disable wait localparam'''.split())
DECL = re.compile(r'^\s*(?:input|output|inout)?\s*(?:wire|reg|logic|integer|genvar)\b(?:\s+signed)?\s*(?:\[[^\]]*\]\s*)*(.*?);', re.M)


def check(path):
    text = pathlib.Path(path).read_text(errors='replace')
    text = re.sub(r'/\*.*?\*/', lambda m: '\n' * m.group(0).count('\n'), text, flags=re.S)
    lines = [re.sub(r'//.*', '', l) for l in text.split('\n')]
    issues = []
    mod_start = 0
    for i, l in enumerate(lines):
        if re.match(r'\s*module\b', l): mod_start = i
    # per module
    for m in re.finditer(r'\bmodule\b(.*?)\bendmodule\b', '\n'.join(lines), re.S):
        start = '\n'.join(lines)[:m.start()].count('\n')
        body = m.group(0).split('\n')
        header_end = next((k for k, l in enumerate(body) if ');' in l), 0)
        decl = {}
        for k, l in enumerate(body):
            dm = re.match(r'^\s*(?:input|output|inout)?\s*(?:wire|reg|logic|integer|genvar)\b', l)
            if dm or k <= header_end:
                seg = l.split('=')[0] if dm else l
                for name in re.findall(r'\b([A-Za-z_]\w*)\b', re.sub(r'\[[^\]]*\]', '', seg)):
                    if name not in KW: decl.setdefault(name, k)
        for k, l in enumerate(body):
            if k <= header_end: continue
            for name in set(re.findall(r'(?<![\.\'`$\w])([A-Za-z_]\w*)\b', l)):
                if name in decl and decl[name] > k:
                    issues.append((start + k + 1, name, start + decl[name] + 1))
    return issues


if __name__ == '__main__':
    bad = 0
    for f in sys.argv[1:]:
        for line, name, dline in check(f):
            print('%s:%d uses %s declared at line %d' % (f, line, name, dline)); bad += 1
    print('ISSUES', bad)
