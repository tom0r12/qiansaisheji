"""Run a local Yosys logic-only synthesis with SRAMs kept as black boxes.

This is an engineering check, not a contest area/timing/power acceptance flow.
Local standard-cell library data never leave this machine.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def yosys_path(path):
    path = Path(path).resolve()
    try:
        # Relative POSIX paths work for both native Yosys and the Windows
        # WASI filesystem. Native Windows backslashes in tool argv do not.
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def yosys_quote(path):
    return '"' + yosys_path(path).replace('"', '\\"') + '"'


def yosys_command(explicit):
    if explicit:
        return [explicit]
    native = shutil.which("yosys")
    if native:
        return [native]
    if (ROOT / "tools/yosys/yowasp_yosys").is_dir():
        return [sys.executable, str(Path(__file__).resolve()), "--internal-yowasp"]
    raise FileNotFoundError("No native Yosys or project-local tools/yosys installation")


def execute(command, log_path, timeout, env):
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log,
                                   stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise RuntimeError(f"Tool exceeded {timeout}s; see {log_path.name}")
    if code:
        tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-16:])
        raise RuntimeError(f"Tool exited {code}; {log_path.name}:\n{tail}")
    return round(time.monotonic() - started, 3)


def cell_areas(liberty):
    # Liberty cell/area declarations in this vendor library are line-oriented.
    # Do not interpret area as square micrometres unless explicitly confirmed.
    cell_re = re.compile(r'^\s*cell\s*\(\s*"?([^"\)]+)"?\s*\)')
    area_re = re.compile(r"^\s*area\s*:\s*([+\-0-9.eE]+)\s*;")
    areas = {}
    current = None
    with liberty.open("r", encoding="ascii", errors="replace") as stream:
        for line in stream:
            cell_match = cell_re.match(line)
            if cell_match:
                current = cell_match.group(1).strip()
            area_match = area_re.match(line)
            if area_match and current is not None:
                areas[current] = float(area_match.group(1))
                current = None
    return areas


def number_parameter(value):
    return int(value, 2) if isinstance(value, str) and re.fullmatch("[01]+", value) else value


def inspect_netlist(path, liberty=None, um2=False):
    design = json.loads(path.read_text(encoding="utf-8"))
    modules = design["modules"]
    top = modules["qingyu_accel"]
    counts = Counter(cell["type"] for cell in top.get("cells", {}).values())
    memories = []
    unknown = {}
    area = 0.0
    areas = cell_areas(liberty) if liberty else {}
    for name, cell in top.get("cells", {}).items():
        kind = cell["type"]
        if "qingyu_sram16" in kind:
            module = modules.get(kind, {})
            attributes = module.get("attributes", {})
            if not int(attributes.get("blackbox", "0"), 2):
                raise RuntimeError(f"SRAM instance {name} was not kept as a black box")
            parameters = dict(module.get("parameter_default_values", {}))
            parameters.update(cell.get("parameters", {}))
            memories.append({"instance": name, "module": kind,
                             "depth": number_parameter(parameters.get("DEPTH")),
                             "width": 16})
        elif liberty:
            if kind in areas:
                area += areas[kind]
            else:
                unknown[kind] = unknown.get(kind, 0) + 1
    if len(memories) != 9:
        raise RuntimeError(f"Expected nine SRAM black boxes, found {len(memories)}")
    inferred = {kind: count for kind, count in counts.items() if kind.startswith("$mem")}
    if inferred:
        raise RuntimeError(f"Unexpected inferred memory cells in accelerator logic: {inferred}")
    summary = {"cell_count_including_sram_instances": sum(counts.values()),
               "cell_counts": dict(sorted(counts.items())),
               "sram_blackboxes": memories,
               "sram_macro_count": len(memories),
               "sram_storage_bits": sum((memory["depth"] or 0) * 16 for memory in memories),
               "sram_macro_area_included": False}
    if liberty:
        summary.update({"logic_area_library_units": area,
                        "logic_area_mm2": area / 1_000_000 if um2 else None,
                        "area_unit_um2_explicitly_asserted": um2,
                        "unmapped_or_unknown_cell_types": unknown})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generic-only", action="store_true")
    parser.add_argument("--liberty", type=Path)
    parser.add_argument("--yosys", help="explicit native Yosys executable")
    parser.add_argument("--timeout", type=int, default=300,
                        help="maximum seconds per tool stage")
    parser.add_argument("--area-unit-um2", action="store_true",
                        help="assert vendor cell area numbers are square micrometres")
    args = parser.parse_args()
    output = ROOT / "reports"
    output.mkdir(exist_ok=True)
    report_path = output / "synthesis_summary.json"
    sources = [ROOT / "rtl/qingyu_sram16.sv", ROOT / "rtl/qingyu_accel.sv"]
    report = {"status": "started", "scope": "accelerator_logic_only_excludes_sram",
              "fsm_policy": "preserve_source_encoding_synth_nofsm",
              "official_total_area_pass": None, "timing_150mhz_pass": None,
              "power_evaluation": "not_performed", "sram_implementation": "blackbox",
              "limitations": ["SRAM macro area and timing models are unavailable in this run.",
                              "ABC mapping is not static timing or routed timing analysis.",
                              "Generic/TT mapping does not establish every required process corner."]}
    try:
        command = yosys_command(args.yosys)
        environment = os.environ.copy()
        environment["YOWASP_CACHE_DIR"] = str(ROOT / "tools/yosys_cache")
        report["tool_command"] = command
        report["rtl_sha256"] = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
        execute(command + ["-V"], output / "synthesis_tool_version.txt", args.timeout, environment)
        report["tool_version"] = (output / "synthesis_tool_version.txt").read_text(encoding="utf-8").strip()
        generic_script = output / "synthesis_generic.ys"
        generic_script.write_text("\n".join([
            "# SRAM internals are deliberately excluded from logic synthesis.",
            "read_verilog -sv -lib " + yosys_quote(sources[0]),
            "read_verilog -sv " + yosys_quote(sources[1]),
            "hierarchy -check -top qingyu_accel",
            "synth -top qingyu_accel -noabc -nofsm",
            "check -assert",
            "write_json " + yosys_quote(output / "synthesis_generic_netlist.json"),
            "tee -o " + yosys_quote(output / "synthesis_generic_stat.json") + " stat -json",
            "",
        ]), encoding="utf-8")
        report["generic_seconds"] = execute(command + ["-s", yosys_path(generic_script)],
                                            output / "synthesis_generic.log", args.timeout, environment)
        report["generic"] = inspect_netlist(output / "synthesis_generic_netlist.json")
        report["status"] = "generic_passed"
        if not args.generic_only:
            library = args.liberty or ROOT / "local_pdk/stdcell/lib/sc9mc_logic0040ll_base_rvt_c40_tt_typical_max_1p10v_25c.lib"
            library = library.resolve()
            if not library.is_file():
                raise FileNotFoundError(f"Liberty file not found: {library}")
            report["liberty"] = {"path": str(library), "sha256": sha256(library)}
            mapped_script = output / "synthesis_mapped.ys"
            mapped_script.write_text("\n".join([
                "read_json " + yosys_quote(output / "synthesis_generic_netlist.json"),
                "read_liberty -lib -ignore_miss_func " + yosys_quote(library),
                "dfflibmap -liberty " + yosys_quote(library),
                "abc -liberty " + yosys_quote(library),
                "clean",
                "check -assert",
                "write_json " + yosys_quote(output / "synthesis_mapped_netlist.json"),
                "write_verilog -noattr -noexpr " + yosys_quote(output / "synthesis_mapped_netlist.v"),
                "tee -o " + yosys_quote(output / "synthesis_mapped_stat.json")
                    + " stat -json -liberty " + yosys_quote(library),
                "",
            ]), encoding="utf-8")
            report["mapping_seconds"] = execute(command + ["-s", yosys_path(mapped_script)],
                                                 output / "synthesis_mapped.log", args.timeout, environment)
            report["mapped"] = inspect_netlist(output / "synthesis_mapped_netlist.json",
                                               library, args.area_unit_um2)
            report["status"] = "logic_mapping_passed"
            if report["mapped"]["unmapped_or_unknown_cell_types"]:
                raise RuntimeError("Mapped netlist contains cells without known standard-cell area")
        after = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
        if after != report["rtl_sha256"]:
            raise RuntimeError("RTL sources changed during this run; rerun on the frozen sources")
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(report_path),
                      "error": report.get("error"),
                      "logic_area_library_units": report.get("mapped", {}).get("logic_area_library_units")},
                     ensure_ascii=False))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--internal-yowasp":
        sys.path.insert(0, str(ROOT / "tools/yosys"))
        from yowasp_yosys import run_yosys
        raise SystemExit(run_yosys(sys.argv[2:]))
    raise SystemExit(main())
