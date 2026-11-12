"""Run the independent SRAM-backed array regression with frozen vectors."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import collections
import xml.etree.ElementTree as ET


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def linux(path):
    path=path.resolve()
    return "/mnt/"+path.drive[0].lower()+path.as_posix()[2:] if os.name=="nt" else str(path)


def main():
    here=Path(__file__).resolve().parent
    root=here.parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vectors",type=Path,default=root/"build/winograd_array8_vectors_20261112")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--cases",type=int,default=214)
    parser.add_argument("--seeds",type=int,nargs="+",default=[2039,2213,2347])
    parser.add_argument("--jobs",type=int,default=2)
    parser.add_argument("--reuse-build",type=Path,help="Reuse only after matching every compiled RTL/TB hash to its completed report")
    args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out=(args.output or root/"build/winograd_array8"/stamp).resolve()
    out.mkdir(parents=True,exist_ok=False)
    vectors=args.vectors.resolve()
    manifest_path=vectors/"manifest.json"
    manifest=json.loads(manifest_path.read_text())
    if not manifest["completed"] or not 1<=args.cases<=len(manifest["cases"]):
        raise ValueError("Incomplete/wrong vectors")
    for case in manifest["cases"]:
        for key,filename in case["files"].items():
            if sha(vectors/filename)!=case["sha256"][key]: raise ValueError("Vector hash changed")
    rtl=[here/"winograd_array8.sv",here/"winograd_int8_pair_acc32.sv",
         here.parent/"winograd_int8/winograd_int8_factor32.sv",root/"rtl/qingyu_sram16.sv"]
    tb=here/"tb_winograd_array8.sv"
    tracked=rtl+[tb,Path(__file__),here/"contract.json",here/"export_vectors.py"]
    before={p.relative_to(root).as_posix():sha(p) for p in tracked}
    report={"schema":"qingyu-winograd-array8-checks-v1","created_utc":datetime.now(timezone.utc).isoformat(),
            "source_sha256":before,"vector_manifest_sha256":sha(manifest_path),"vector_directory":str(vectors),
            "behavioral_project_sram":True,"foundry_macro_functional_test":False,
            "full_soc_tested":False,"ppa_measured":False,"commands":[],"simulations":[],"completed":False}
    prefix=["wsl.exe","-d","Ubuntu","--cd",linux(root),"--"] if os.name=="nt" else []
    def run(argv,name):
        with (out/name).open("w",encoding="utf-8") as log:
            completed=subprocess.run(prefix+list(map(str,argv)),cwd=root,stdout=log,stderr=subprocess.STDOUT)
        report["commands"].append({"argv":prefix+list(map(str,argv)),"log":name,"returncode":completed.returncode})
        (out/"partial_result.json").write_text(json.dumps(report,indent=2)+"\n")
        if completed.returncode: raise RuntimeError("Failed; see "+str(out/name))
        return (out/name).read_text(encoding="utf-8",errors="replace")
    lint=run(["verilator","--lint-only","-Wall","--top-module","winograd_array8",*[linux(p) for p in rtl]],"rtl_lint.log")
    if "%Warning" in lint or "%Error" in lint: raise RuntimeError("Unwaived RTL lint diagnostic")
    run(["verilator","--xml-only","--top-module","winograd_array8","--xml-output",linux(out/"elaboration.xml"),
         *[linux(p) for p in rtl]],"elaboration.log")
    elaborated=ET.parse(out/"elaboration.xml").getroot()
    modules={m.get("name"):m for m in elaborated.find("netlist").findall("module")}
    cell_counts=collections.Counter(c.get("submodname") for c in elaborated.find("cells").iter("cell"))
    ram_counts=collections.Counter()
    for module_name,count in cell_counts.items():
        module=modules[module_name]
        if module.get("origName")=="qingyu_sram16":
            depth=next(v.find("const").get("name") for v in module.findall("var") if v.get("name")=="DEPTH")
            ram_counts[int(depth.split("'sh")[1],16)]+=count
    if dict(ram_counts)!={1024:8,128:16} or cell_counts["winograd_int8_pair_acc32"]!=128 or cell_counts["winograd_int8_factor32"]!=24:
        raise RuntimeError("Unexpected physical SRAM or arithmetic instance count")
    top_variables={v.get("name") for v in modules["winograd_array8"].findall("var")}
    if {"row_factor_q","col_factor_q"}&top_variables: raise RuntimeError("Unexpected duplicate factor shadow arrays")
    report["elaborated_structure"]={"sram_depth_counts":dict(ram_counts),"sram_word_bits":16,
                                     "allocated_sram_bits":sum(depth*16*count for depth,count in ram_counts.items()),
                                     "raw_pair_lanes":128,"hardware_factor_units":24,"additional_factor_shadow_arrays":0,
                                     "xml_sha256":sha(out/"elaboration.xml")}
    binary=out/"obj_dir/Vtb_winograd_array8"
    if args.reuse_build:
        old_directory=args.reuse_build.resolve()
        old_report_path=old_directory/"result.json"
        old_report=json.loads(old_report_path.read_text())
        if not old_report["completed"]: raise RuntimeError("Cannot reuse an incomplete build")
        for path in rtl+[tb]:
            if old_report["source_sha256"][path.relative_to(root).as_posix()]!=sha(path):
                raise RuntimeError("Compiled source differs from reuse build")
        binary=old_directory/"obj_dir/Vtb_winograd_array8"
        if not binary.is_file(): raise RuntimeError("Reuse binary missing")
        report["reused_compilation"]={"report":str(old_report_path),"report_sha256":sha(old_report_path),
                                        "compiled_rtl_and_tb_hashes_match":True}
    else:
        run(["verilator","--binary","--timing","-Wno-fatal","--top-module","tb_winograd_array8","-j",args.jobs,
             "--Mdir",linux(out/"obj_dir"),*[linux(p) for p in rtl],linux(tb)],"compile.log")
    report["simulation_binary_sha256"]=sha(binary)
    for seed in args.seeds:
        output=run([linux(binary),"+VECTORS="+linux(vectors),f"+CASES={args.cases}",f"+SEED={seed}",
                    f"+verilator+seed+{seed}"],f"seed_{seed}.log")
        passed=re.search(r"^PASS array8 (.+)$",output,re.M)
        if not passed: raise RuntimeError("No complete PASS marker")
        metrics={key:int(value) for key,value in re.findall(r"(\w+)=(\d+)",passed.group(1))}
        if metrics["real_or_synthetic_cases"]!=args.cases or metrics["errors"]!=2 or metrics["aborted"]!=5 or metrics["resets"]!=6:
            raise RuntimeError("Regression scenario count mismatch")
        # WSL's UTF16 startup warning may leave a NUL before the first normal
        # UTF8 stdout line. Normalize only NULs for parsing; retain raw logs.
        normalized=output.replace("\x00","")
        tasks=[{key:int(value) for key,value in re.findall(r"(\w+)=(\d+)",line)} for line in normalized.splitlines() if line.startswith("TASK ")]
        if len(tasks)!=args.cases+12 or any(t["cycles"]!=t["load"]+t["factor"]+t["compute"]+t["store"] for t in tasks):
            raise RuntimeError("Incomplete phase window report")
        report["simulations"].append({"seed":seed,"passed":True,**metrics,"tasks":tasks})
        (out/"partial_result.json").write_text(json.dumps(report,indent=2)+"\n")
        print("PASS seed",seed,metrics,flush=True)
    if before!={p.relative_to(root).as_posix():sha(p) for p in tracked}: raise RuntimeError("Source changed during run")
    if sha(manifest_path)!=report["vector_manifest_sha256"]: raise RuntimeError("Vector manifest changed")
    report["completed"]=True
    report["completed_utc"]=datetime.now(timezone.utc).isoformat()
    report["logs_sha256"]={p.name:sha(p) for p in out.glob("*.log")}
    (out/"result.json").write_text(json.dumps(report,indent=2)+"\n")
    print("RESULT",out/"result.json",flush=True)


if __name__=="__main__":main()
