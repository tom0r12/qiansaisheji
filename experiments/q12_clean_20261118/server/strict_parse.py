"""Stricter second-opinion parse/elaboration of a package's hardware source set
with Icarus Verilog (SYNTHESIS + vendor-macro mode, local mock RAM ports)."""
import re, subprocess, sys, pathlib
S = pathlib.Path(__file__).resolve().parent
def main(cand):
    cand = pathlib.Path(cand); tcl = (cand / 'hardware/sources.tcl').read_text()
    files = [str(cand / 'hardware' / m) for m in re.findall(r'\{(src/[^}]+)\}', tcl)]
    cmd = ['iverilog', '-g2012', '-DSYNTHESIS=1', '-DQ12_USE_VENDOR_MACROS=1', '-DDISABLE_SV_ASSERTION=1',
           '-I', str(cand / 'hardware/includes'), '-s', 'qingyu_e203_soc_top', '-o', 'NUL', *files, str(S / 'local_mock/mock_rams.v')]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    errs = [l for l in r.stdout.splitlines() if 'error' in l.lower()]
    print('\n'.join(errs[:30])); print('IVERILOG rc=%d errors=%d' % (r.returncode, len(errs)))
    return r.returncode
if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
