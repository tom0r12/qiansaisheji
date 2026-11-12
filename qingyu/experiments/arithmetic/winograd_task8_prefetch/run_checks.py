"""Strict RTL lint, physical storage inventory, and whole-task protocol/numeric regression."""
from __future__ import annotations
import argparse
import collections
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def linux(p):
    p=p.resolve();return "/mnt/"+p.drive[0].lower()+p.as_posix()[2:] if os.name=="nt" else str(p)

def main():
    here=Path(__file__).resolve().parent;root=here.parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vectors",type=Path,default=root/"build/winograd_task8_vectors_20261112")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--cases",type=int,default=22)
    parser.add_argument("--seeds",type=int,nargs="+",default=[2371,2477,2551])
    parser.add_argument("--jobs",type=int,default=2)
    parser.add_argument("--reuse-build",type=Path)
    args=parser.parse_args();vectors=args.vectors.resolve()
    out=(args.output or root/"build/winograd_task8_prefetch"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")).resolve()
    out.mkdir(parents=True,exist_ok=False)
    manifest_path=vectors/"manifest.json";manifest=json.loads(manifest_path.read_text())
    if not manifest["completed"] or not 1<=args.cases<=len(manifest["cases"]):raise ValueError("Bad vectors")
    for case in manifest["cases"]:
        for k,p in case["files"].items():
            if sha(vectors/p)!=case["sha256"][k]:raise ValueError("Changed vectors")
    rtl=[here/"winograd_int8_task8.sv",here.parent/"winograd_array8/winograd_int8_pair_acc32.sv",root/"rtl/qingyu_sram16.sv"]
    tb=here/"tb_winograd_task8.sv";tracked=rtl+[tb,Path(__file__),here/"contract.json",here/"export_vectors.py"]
    before={p.relative_to(root).as_posix():sha(p) for p in tracked}
    report={"schema":"qingyu-winograd-task8-prefetch-checks-v1","created_utc":datetime.now(timezone.utc).isoformat(),
            "source_sha256":before,"vector_manifest_sha256":sha(manifest_path),"vector_directory":str(vectors),
            "behavioral_project_sram":True,"foundry_macro_functional_test":False,"full_soc_tested":False,
            "ppa_measured":False,"commands":[],"simulations":[],"completed":False}
    prefix=["wsl.exe","-d","Ubuntu","--cd",linux(root),"--"] if os.name=="nt" else []
    def run(argv,name):
        with (out/name).open("w",encoding="utf8") as f:done=subprocess.run(prefix+list(map(str,argv)),cwd=root,stdout=f,stderr=subprocess.STDOUT)
        report["commands"].append({"argv":prefix+list(map(str,argv)),"log":name,"returncode":done.returncode})
        (out/"partial_result.json").write_text(json.dumps(report,indent=2)+"\n")
        if done.returncode:raise RuntimeError("Failed; see "+str(out/name))
        return (out/name).read_text(encoding="utf8",errors="replace").replace("\x00","")
    lint=run(["verilator","--lint-only","-Wall","--top-module","winograd_int8_task8",*[linux(p) for p in rtl]],"rtl_lint.log")
    if "%Warning" in lint or "%Error" in lint:raise RuntimeError("Unwaived RTL diagnostic")
    run(["verilator","--xml-only","--top-module","winograd_int8_task8","--xml-output",linux(out/"elaboration.xml"),*[linux(p) for p in rtl]],"elaboration.log")
    xml=ET.parse(out/"elaboration.xml").getroot();modules={m.get("name"):m for m in xml.find("netlist").findall("module")}
    cells=collections.Counter(c.get("submodname") for c in xml.find("cells").iter("cell"));rams=collections.Counter()
    for name,count in cells.items():
        m=modules[name]
        if m.get("origName")=="qingyu_sram16":
            depth=next(v.find("const").get("name") for v in m.findall("var") if v.get("name")=="DEPTH")
            rams[int(depth.split("'sh")[1],16)]+=count
    if dict(rams)!={1024:8,128:21} or cells["winograd_int8_pair_acc32"]!=128:raise RuntimeError("Unexpected storage/arithmetic count")
    muls=collections.Counter()
    for name,count in cells.items():
        for node in modules[name].iter():
            if node.tag in ("mul","muls"):muls[node.tag]+=count
    report["elaborated_structure"]={"sram_depth_counts":dict(rams),"sram_word_bits":16,
                                    "allocated_sram_bits":sum(d*16*n for d,n in rams.items()),
                                    "raw_pair_lanes":128,"load_factor_multipliers":2,"additional_snapshot_state_bits":3121,"W_burst_data_address_bits":789,"xml_multiply_node_count":dict(muls),
                                    "xml_sha256":sha(out/"elaboration.xml")}
    binary=out/"obj_dir/Vtb_winograd_task8"
    if args.reuse_build:
        old=args.reuse_build.resolve();oldreport=json.loads((old/"result.json").read_text())
        if not oldreport["completed"]:raise RuntimeError("Reuse incomplete")
        for p in rtl+[tb]:
            if oldreport["source_sha256"][p.relative_to(root).as_posix()]!=sha(p):raise RuntimeError("Reuse source differs")
        binary=old/"obj_dir/Vtb_winograd_task8"
        report["reused_compilation"]={"report":str(old/"result.json"),"report_sha256":sha(old/"result.json"),"compiled_hashes_match":True}
    else:
        run(["verilator","--binary","--timing","-Wno-fatal","--top-module","tb_winograd_task8","-j",args.jobs,
             "--Mdir",linux(out/"obj_dir"),*[linux(p) for p in rtl],linux(tb)],"compile.log")
    report["simulation_binary_sha256"]=sha(binary)
    for seed in args.seeds:
        output=run([linux(binary),"+VECTORS="+linux(vectors),f"+CASES={args.cases}",f"+SEED={seed}",f"+verilator+seed+{seed}"],f"seed_{seed}.log")
        passed=re.search(r"^PASS task8 (.+)$",output,re.M)
        if not passed:raise RuntimeError("No complete PASS marker")
        metrics={k:int(v) for k,v in re.findall(r"(\w+)=(\d+)",passed.group(1))}
        if metrics["real_or_synthetic_cases"]!=args.cases or metrics["successful"]!=args.cases+11 or metrics["errors"]!=2 or metrics["aborted"]!=7 or metrics["resets"]!=8:raise RuntimeError("Scenario count mismatch")
        tasks=[{k:int(v) for k,v in re.findall(r"(\w+)=(\d+)",line)} for line in output.splitlines() if line.startswith("TASK ")]
        if len(tasks)!=args.cases+13 or any(t["cycles"]!=sum(t[k] for k in ("load","factor","cache","compute","store")) for t in tasks):raise RuntimeError("Incomplete timing window")
        report["simulations"].append({"seed":seed,"passed":True,**metrics,"tasks":tasks})
        (out/"partial_result.json").write_text(json.dumps(report,indent=2)+"\n")
        print("PASS seed",seed,metrics,flush=True)
    if before!={p.relative_to(root).as_posix():sha(p) for p in tracked}:raise RuntimeError("Source changed during run")
    if sha(manifest_path)!=report["vector_manifest_sha256"]:raise RuntimeError("Vector manifest changed")
    report.update(completed=True,completed_utc=datetime.now(timezone.utc).isoformat(),logs_sha256={p.name:sha(p) for p in out.glob("*.log")})
    (out/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    print("RESULT",out/"result.json",flush=True)
if __name__=="__main__":main()
