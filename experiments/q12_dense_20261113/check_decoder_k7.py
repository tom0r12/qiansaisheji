"""Reuse established independent vectors/lockstep for the new k6/k7 contract."""
from pathlib import Path
import hashlib
H=Path(__file__).resolve().parent;R=H.parents[1];out=H/'checks/decoder_k7';out.mkdir(parents=True,exist_ok=True)
base=R/'final/q12_20261113/vendor/src/q12/decoder2/q12_rice_decoder.sv'
ref=base.read_text()
for old,new in [('start_k!=9','start_k!=7'),('k_q==6 ? 63 : 7','k_q==6 ? 63 : 31'),
                ('k_q==6 ? 7 : 10','k_q==6 ? 7 : 8'),('remainder_window[71:63]','remainder_window[71:65]'),
                ('quotient<<9','quotient<<7'),('u>>9','u>>7')]:
 assert old in ref,old
 ref=ref.replace(old,new)
(out/'reference_k7.sv').write_text(ref)
script=(R/'experiments/q12_area_20261113/check_decoder_replay.py').read_text()
begin=script.index('here=Path(');end=script.index("ref=base.read_text()",begin)
setup='here=Path('+repr(str(H))+');out=Path('+repr(str(out))+');base=out/"reference_k7.sv";candidate=here/"candidates/native12/q12_rice_decoder.sv"\n'
script=script[:begin]+setup+script[end:]
script=script.replace('for k in (6,9):','for k in (6,7):')
exec(compile(script,str(H/'check_decoder_k7.py'),'exec'),{'__name__':'__main__','__file__':str(H/'check_decoder_k7.py')})
