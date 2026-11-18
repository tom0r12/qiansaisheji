"""Apply literal replacements: python subst.py <file> <spec.py>
spec.py defines R = [(old, new, expected_count), ...]. Whitespace-insensitive
matching is NOT done; old must match exactly (after CRLF->LF)."""
import sys, pathlib
f = pathlib.Path(sys.argv[1]); spec = {}
exec(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8'), spec)
t = f.read_bytes().decode('utf-8').replace('\r\n', '\n')
for item in spec['R']:
    old, new = item[0], item[1]; n = item[2] if len(item) > 2 else 1
    c = t.count(old)
    if c != n:
        raise SystemExit(f'count {c} != {n} for: {old[:80]!r}')
    t = t.replace(old, new)
f.write_bytes(t.encode('utf-8'))
print('patched', f)
