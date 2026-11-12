"""Export whole-task streams using frozen tile inputs and independent direct MAC goldens."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"model"))
from reference import accumulate, round_shift_rne

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def words(path): return [int(s,16) for s in path.read_text().split()]
def signed(v,bits): return v-(1<<bits) if v&(1<<(bits-1)) else v
def write(path,values): path.write_text("".join(f"{int(v)&0xffffffff:08x}\n" for v in values))
def pack(values,bits): return sum((int(v)&((1<<bits)-1))<<(bits*i) for i,v in enumerate(values))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tile-vectors",type=Path,default=ROOT/"build/winograd_array8_vectors_20261112")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    source_manifest=args.tile_vectors/"manifest.json"
    source=json.loads(source_manifest.read_text())
    frozen_path=ROOT/"experiments/arithmetic/winograd_array8/SOURCE_SHA256.json"
    frozen=json.loads(frozen_path.read_text())
    if sha(source_manifest)!=frozen["vector_manifest_sha256"]: raise ValueError("Frozen vector identity changed")
    for path,digest in frozen["files"].items():
        if sha(frozen_path.parent/path)!=digest: raise ValueError("Frozen array source changed")
    for row in source["cases"]:
        for key,path in row["files"].items():
            if sha(args.tile_vectors/path)!=row["sha256"][key]: raise ValueError("Input tile vector changed")
    report={"schema":"qingyu-winograd-task8-vectors-v1","created_utc":datetime.now(timezone.utc).isoformat(),
            "script_sha256":sha(Path(__file__)),"frozen_tile_manifest_sha256":sha(source_manifest),
            "frozen_array_source_manifest_sha256":sha(frozen_path),"reference_sha256":sha(ROOT/"model/reference.py"),
            "numeric_configuration":source["frozen_configuration"],"validation_sample_index":source["validation_sample_index"],
            "golden":"direct64 sequential integer MAC plus scalar RNE; factor files are TB cache oracles only, never DUT input",
            "validation_parameter_fit":False,"official_evaluation":False,"cases":[],"completed":False}
    (out/"export_plan.json").write_text(json.dumps(report,indent=2)+"\n")

    def export(x,w,bias,shift,description,old_acc=None,old_out=None):
        x,w,bias,shift=[np.asarray(a,dtype=np.int64) for a in (x,w,bias,shift)]
        if x.shape!=(99,64) or w.shape!=(64,256) or bias.shape!=(256,) or shift.shape!=(256,): raise ValueError("Shape")
        if np.any(abs(x)>128) or np.any(x>127) or np.any(abs(w)>128) or np.any(w>127): raise ValueError("INT8")
        if np.any(bias< -32768) or np.any(bias>32767) or np.any(shift<0) or np.any(shift>47): raise ValueError("Metadata")
        a=accumulate(x,w,bias)
        y=np.array([[max(-128,min(127,round_shift_rne(int(a[r,c]),int(shift[c])))) for c in range(256)] for r in range(99)])
        a_tile=np.concatenate([a[:,t*16:t*16+16].reshape(-1) for t in range(16)])
        y_words=[pack(y[r,t*16+q*4:t*16+q*4+4],8) for t in range(16) for r in range(99) for q in range(4)]
        if old_acc is not None and not np.array_equal(a_tile,old_acc): raise ValueError("Direct full-task accumulator differs from frozen tile golden")
        if old_out is not None and y_words!=old_out: raise ValueError("Full-task output differs from frozen tile golden")
        xp=np.pad(x,((0,1),(0,0)))
        x_words=[pack([xp[r*2,k*2],xp[r*2,k*2+1],xp[r*2+1,k*2],xp[r*2+1,k*2+1]],8) for r in range(50) for k in range(32)]
        w_words=[pack([w[k*2,g*32+c*2],w[k*2+1,g*32+c*2],w[k*2,g*32+c*2+1],w[k*2+1,g*32+c*2+1]],8)
                 for g in range(8) for k in range(32) for c in range(16)]
        metadata=[]
        for g in range(8):
            metadata.extend(pack(bias[g*32+i*2:g*32+i*2+2],16) for i in range(16))
            metadata.extend(pack(shift[g*32+i*4:g*32+i*4+4],8) for i in range(8))
        r_factor=np.sum(x[:,0::2]*x[:,1::2],axis=1)
        c_factor=np.sum(w[0::2,:]*w[1::2,:],axis=0)
        index=len(report["cases"])
        data={"x":x_words,"w":w_words,"meta":metadata,"output":y_words,"acc":a_tile,"r":r_factor,"c":c_factor}
        if [len(data[k]) for k in data]!=[1600,4096,192,6336,25344,99,256]: raise ValueError("Packing length")
        files={key:f"case{index:04d}_{key}.hex" for key in data}
        for key,values in data.items(): write(out/files[key],values)
        report["cases"].append({"index":index,**description,"files":files,"sha256":{k:sha(out/p) for k,p in files.items()},
                                "minimum_accumulator":int(a.min()),"maximum_accumulator":int(a.max()),
                                "row_factor_min":int(r_factor.min()),"row_factor_max":int(r_factor.max()),
                                "column_factor_min":int(c_factor.min()),"column_factor_max":int(c_factor.max())})

    for layer in range(12):
        x=np.zeros((99,64),np.int64); w=np.zeros((64,256),np.int64); bias=np.zeros(256,np.int64); shift=np.zeros(256,np.int64)
        old_acc=[]; old_out=[]; common_x=None
        for tile in range(16):
            row=source["cases"][layer*16+tile]
            if row["layer"]!=layer or row["tile"]!=tile: raise ValueError("Tile identity/order")
            inp=words(args.tile_vectors/row["files"]["input"])
            if common_x is None: common_x=inp[:1600]
            if common_x!=inp[:1600]: raise ValueError("X differs across tiles")
            for i,val in enumerate(inp[:1600]):
                rp,kp=divmod(i,32)
                for b in range(4):
                    r,k=2*rp+b//2,2*kp+b%2
                    if r<99: x[r,k]=signed((val>>(8*b))&255,8)
            for i,val in enumerate(inp[1600:1856]):
                kp,cp=divmod(i,8)
                for b in range(4): w[2*kp+b%2,tile*16+2*cp+b//2]=signed((val>>(8*b))&255,8)
            for i,val in enumerate(inp[1856:1864]):
                for b in range(2): bias[tile*16+2*i+b]=signed((val>>(16*b))&65535,16)
            for i,val in enumerate(inp[1864:1868]):
                for b in range(4): shift[tile*16+4*i+b]=(val>>(8*b))&255
            old_acc.extend(signed(v,32) for v in words(args.tile_vectors/row["files"]["accumulator"]))
            old_out.extend(words(args.tile_vectors/row["files"]["output"]))
        export(x,w,bias,shift,{"kind":"frozen_validation","layer":layer,"sample_id":row["sample_id"]},old_acc,old_out)
        print("Exported full task layer",layer,flush=True)
    for xv,wv in [(-128,-128),(-128,127),(127,-128),(127,127),(0,0)]:
        export(np.full((99,64),xv),np.full((64,256),wv),np.tile([-32768,32767,-1,0],64),
               np.tile([0,1,7,15,23,24,47,2],32),{"kind":"full_range_constant","x":xv,"w":wv})
    export(np.zeros((99,64)),np.zeros((64,256)),np.tile([-32768,-259,-257,-255,-5,-3,-1,0,1,3,5,253,255,257,32767,127],16),
           np.tile([0,1,1,1,1,1,1,0,1,1,1,1,1,1,15,47],16),{"kind":"RNE_ties_and_saturation"})
    rng=np.random.default_rng(9964256)
    for case in range(4):
        export(rng.integers(-128,128,(99,64)),rng.integers(-128,128,(64,256)),rng.integers(-32768,32768,256),
               rng.integers(0,48,256),{"kind":"random_signed8","random_index":case})
    report.update(completed=True,real_full_tasks=12,synthetic_full_tasks=len(report["cases"])-12)
    (out/"manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    print("MANIFEST",out/"manifest.json",flush=True)

if __name__=="__main__": main()
