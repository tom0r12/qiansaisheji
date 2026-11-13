"""Compare library area with same-cell LEF micron dimensions; read-only."""
from pathlib import Path
import re,json,gzip

root=Path.home()/'Desktop/smic_official/S40/smic/SCC40NLL_VHSC40_RVT_V0.1/SCC40NLL_VHSC40_RVT_V0p1'
libs=list(root.rglob('scc40nll_vhsc40_rvt_tt_v1p1_25c_basic.lib*'))
lefs=list(root.rglob('*.lef'))+list(root.rglob('*.lef.gz'))
print('AREA_UNIT_FILES',len(libs),len(lefs))
def text(p):
    return gzip.open(str(p),'rt',errors='replace').read() if p.suffix=='.gz' else p.read_text(errors='replace')
matches=[]
for lp in libs[:1]:
    s=text(lp);cells=list(re.finditer(r'\bcell\s*\(\s*"?([^\s"()]+)"?\s*\)',s));areas={}
    for i,m in enumerate(cells):
        section=s[m.end():cells[i+1].start() if i+1<len(cells) else len(s)]
        a=re.search(r'\barea\s*:\s*([\d.eE+-]+)\s*;',section)
        if a:areas[m.group(1)]=float(a.group(1))
    for fp in lefs:
        s=text(fp)
        for name,body in re.findall(r'\bMACRO\s+(\S+)(.*?)\bEND\s+\1\b',s,re.S):
            a=re.search(r'\bSIZE\s+([\d.eE+-]+)\s+BY\s+([\d.eE+-]+)\s*;',body)
            if a and name in areas and areas[name]>0:
                physical=float(a.group(1))*float(a.group(2))
                if physical<=0:continue
                matches.append({'cell':name,'lib_area':areas[name],'lef_width_um':float(a.group(1)),
                    'lef_height_um':float(a.group(2)),'ratio':areas[name]/physical,'lib':str(lp),'lef':str(fp)})
        if len(matches)>=5:break
print('AREA_UNIT_MATCHED_CELLS',len(matches))
for row in matches[:5]:print(json.dumps(row))
if matches:
    print('AREA_UNIT_ALL_MATCH_MICRON2',all(abs(r['ratio']-1)<0.0001 for r in matches))
