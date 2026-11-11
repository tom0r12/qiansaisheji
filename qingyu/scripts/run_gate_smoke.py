"""Bounded RTL-vs-mapped functional simulation using local licensed cell models.

Private PDK contents are only extracted under local_pdk; no network is used.
This is a sampled functional check, not formal equivalence, STA or SDF signoff.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from zipfile import ZipFile

from inspect_pdk import SplitZipReader, archive_parts, repair_disk_offsets

ROOT = Path(__file__).resolve().parents[1]
NETLIST = ROOT / "reports/synthesis_mapped_netlist.v"
MODEL = ROOT / "local_pdk/stdcell/verilog/sc9mc_logic0040ll_base_rvt_c40.v"
MEMBER = "pdk/sc9mc_base_rvt_c40/r1p1/verilog/sc9mc_logic0040ll_base_rvt_c40.v"
REPORT = ROOT / "reports/gate_smoke.json"
LOG = ROOT / "reports/gate_smoke.log"

def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    global NETLIST, REPORT, LOG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-fsm", action="store_true",
                        help="check the separately generated gate_smoke_nofsm_netlist.v")
    args = parser.parse_args()
    stem = "gate_smoke_nofsm" if args.no_fsm else "gate_smoke"
    if args.no_fsm:
        NETLIST = ROOT / "reports/gate_smoke_nofsm_netlist.v"
        REPORT = ROOT / "reports/gate_smoke_nofsm.json"
        LOG = ROOT / "reports/gate_smoke_nofsm.log"
    start = time.monotonic()
    report = {
        "kind": "SAMPLED_RTL_VS_STD_CELL_MAPPED_FUNCTIONAL_SIMULATION",
        "passed": False,
        "formal_equivalence": False,
        "static_timing_analysis": False,
        "sdf_annotated": False,
        "timing_150mhz_pass": None,
        "contains_private_pdk_data": True,
        "external_upload_performed": False,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "one 99x4 tile, control/ICB checks, RTL+mapped observed responses and independent expected outputs",
        "netlist": str(NETLIST.relative_to(ROOT)),
        "state_encoding_flow": "synth -nofsm" if args.no_fsm else "production mapped netlist (see synthesis flow)",
        "limitations": [
            "Sampled vectors do not prove equivalence over all inputs/states",
            "Behavioral synchronous SRAM models substitute the nine blackboxes",
            "ARM_UD_MODEL selects vendor uniform-delay models, not actual corner/SDF timing",
            "2000ns clock period and settled-phase checks are functional only; no 150MHz inference",
            "No SoC-wide or official DC/Formality equivalence claim"
        ]
    }
    synthesis_summary = ROOT / "reports/synthesis_summary.json"
    if synthesis_summary.is_file() and not args.no_fsm:
        summary = json.loads(synthesis_summary.read_text(encoding="utf-8"))
        report["state_encoding_flow"] = summary.get("fsm_policy", "unspecified")
    try:
        inventory = json.loads((ROOT / "reports/pdk_inventory.json").read_text(encoding="utf-8"))
        source = Path(inventory["source"])
        with SplitZipReader(archive_parts(source)) as reader, ZipFile(reader) as archive:
            repair_disk_offsets(archive, reader)
            info = archive.getinfo(MEMBER)
            if not MODEL.is_file():
                MODEL.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, MODEL.open("wb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
            if MODEL.stat().st_size != info.file_size:
                raise ValueError("Local cell model length differs from ZIP member")
            report["cell_model"] = {"path": str(MODEL.relative_to(ROOT)), "archive_member": MEMBER,
                                    "zip_crc32": f"{info.CRC:08x}", "sha256": checksum(MODEL)}
        text = NETLIST.read_text(encoding="utf-8")
        memories = re.findall(r"qingyu_sram16\s*#\(\s*\.ADDR_W\(32's?d(\d+)\),\s*\.DEPTH\(32's?d(\d+)\)\s*\)\s*(\\\S+|\w+)\s*\(", text)
        actual = Counter((int(aw), int(depth)) for aw, depth, _ in memories)
        expected = Counter({(7,128):5, (12,4096):2, (10,1024):2})
        report["sram_blackbox_parameters"] = [{"instance": name, "addr_width": int(aw), "depth": int(depth), "data_width": 16} for aw,depth,name in memories]
        report["sram_parameters_preserved"] = actual == expected
        if actual != expected:
            raise ValueError(f"SRAM parameters differ: {actual}")
        cell_types = sorted(set(re.findall(r"^\s+([A-Z][A-Z0-9_]+)\s+_\d+_\s*\(", text, re.M)))
        defined = set(re.findall(r"^module\s+(\w+)", MODEL.read_text(encoding="ascii", errors="replace"), re.M))
        missing = sorted(set(cell_types)-defined)
        report["mapped_cell_types"] = cell_types
        report["undefined_cell_types"] = missing
        if missing:
            raise ValueError(f"Missing cell models: {missing}")
        reference = (ROOT / "rtl/qingyu_accel.sv").read_text(encoding="utf-8")
        reference, count = re.subn(r"\bmodule\s+qingyu_accel\b", "module qingyu_accel_ref", reference, count=1)
        if count != 1:
            raise ValueError("Cannot name isolated RTL reference")
        ref_path = ROOT / f"reports/{stem}_reference.v"
        ref_path.write_text(reference, encoding="utf-8")
        files = [MODEL, NETLIST, ref_path, ROOT/"rtl/qingyu_sram16.sv", ROOT/"tb/tb_qingyu_gate_smoke.sv"]
        filelist = ROOT / f"reports/{stem}_files.f"
        filelist.write_text("\n".join(str(p.relative_to(ROOT)).replace("\\","/") for p in files)+"\n", encoding="utf-8")
        compile_cmd = [shutil.which("iverilog") or "iverilog", "-g2012", "-DARM_UD_MODEL", "-s", "tb_qingyu_gate_smoke", "-o", f"reports/{stem}.vvp", "-c", f"reports/{stem}_files.f"]
        run_cmd = [shutil.which("vvp") or "vvp", f"reports/{stem}.vvp"]
        report["commands"] = [compile_cmd, run_cmd]
        report["source_sha256"] = {str(p.relative_to(ROOT)): checksum(p) for p in files if p != MODEL}
        report["source_sha256"]["scripts/run_gate_smoke.py"] = checksum(Path(__file__))
        with LOG.open("w", encoding="utf-8") as log:
            log.write("LOCAL PRIVATE STANDARD CELL MODELS; SAMPLED FUNCTIONAL CHECK ONLY.\n")
            log.write("NOT formal equivalence, STA, SDF or official ASIC acceptance.\n")
            log.flush()
            for command, timeout in [(compile_cmd,120),(run_cmd,240)]:
                log.write("COMMAND: " + " ".join(command) + "\n"); log.flush()
                process = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
                if process.returncode:
                    raise RuntimeError(f"Command failed exit={process.returncode}")
        output = LOG.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"PASS mapped gate smoke: outputs=(\d+) bus_checks=(\d+) compared_cycles=(\d+)", output)
        if not match or int(match[1]) != 396:
            raise ValueError("Complete PASS marker missing")
        report["passed"] = True
        report["outputs_compared"] = int(match[1])
        report["bus_transactions_checked"] = int(match[2])
        report["settled_cycles_compared"] = int(match[3])
        report["compiled_simulation_sha256"] = checksum(ROOT / f"reports/{stem}.vvp")
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    report["elapsed_wall_seconds"] = round(time.monotonic()-start,3)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "report": str(REPORT), "error": report.get("error"), "elapsed_wall_seconds": report["elapsed_wall_seconds"]}, indent=2), flush=True)
    if not report["passed"]:
        if LOG.exists(): print(LOG.read_text(encoding="utf-8", errors="replace")[-4500:])
        raise SystemExit(1)

if __name__ == "__main__":
    main()
