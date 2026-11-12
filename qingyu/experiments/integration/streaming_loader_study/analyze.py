"""Read-only, reproducible loader-window evidence and conditional lower bounds.

No RTL or existing evidence is edited. This is not a cycle-accurate hardware
simulation, platform-loader implementation, or timing/PPA acceptance result.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PDF = ROOT.parent.parent / "f8732a6ebb0442b1986eeec83a4bf6db.pdf"
BUDGET = ROOT / "build/tiled_codec_budget_20261112/result.json"
SOC = ROOT / "build/int8soc/20261111T175515904061Z/result.json"
FREQUENCY = 150_000_000
TARGET = 10_450


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def summary(values):
    ordered = sorted(values)
    return {"min": min(values), "mean": statistics.mean(values),
            "p95_nearest_rank": ordered[math.ceil(.95*len(ordered))-1], "max": max(values)}


def main():
    import fitz  # Only for re-reading the supplied primary PDF; not model fitting.
    doc = fitz.open(PDF)
    pages = []
    for number in (3, 4, 12):
        page = doc[number-1]
        content = page.get_text()
        text_file = HERE / f"original_physical_page_{number}.txt"
        text_file.write_text(content, encoding="utf-8")
        image_file = HERE / f"original_physical_page_{number}.png"
        page.get_pixmap(matrix=fitz.Matrix(1.3, 1.3)).save(image_file)
        pages.append({"physical_page": number, "text_sha256": sha(text_file), "image_sha256": sha(image_file)})

    source_paths = [
        "reports/e203-source-manifest.json",
        "experiments/integration/int8soc/soc_main.c",
        "experiments/integration/int8soc/tb_int8soc.sv",
        "experiments/integration/int8soc/qingyu_e203_soc_top.v",
        "experiments/integration/int8stream_dual/qingyu_int8stream_engine.sv",
        "experiments/transport/icb_stream_prefix/qingyu_icb_stream_prefix.sv",
        "experiments/h1500v/opt33_readcache/rtl/qingyu_shared_sram.sv",
        "experiments/h1500v/opt30_fusedpipe4/rtl/qingyu_e203_subsys_main.v",
        "vendor/e203_hbirdv2/rtl/e203/subsys/e203_subsys_mems.v",
        "vendor/e203_hbirdv2/rtl/e203/debug/sirv_debug_module.v",
        "experiments/arithmetic/winograd_task9/winograd_int8_task8.sv",
        "experiments/arithmetic/winograd_task9/SOURCE_SHA256.json",
        "experiments/arithmetic/winograd_task8_prefetch/SOURCE_SHA256.json",
    ]
    missing = [name for name in source_paths if not (ROOT/name).is_file()]
    if missing:
        raise FileNotFoundError(missing)
    vendor_files = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT/"vendor/e203_hbirdv2").rglob("*") if p.is_file())
    save("evidence.json", {
        "schema": "qingyu-streaming-loader-study-evidence-v1",
        "primary_pdf": {"name": PDF.name, "sha256": sha(PDF), "page_count": len(doc), "extracted_pages": pages},
        "source_sha256": {name: sha(ROOT/name) for name in source_paths},
        "result_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in (BUDGET, SOC)},
        "vendor_inventory": vendor_files,
        "vendor_scope": "Local pinned public E203 RTL/LICENSE snapshot; not an organizer loader delivery.",
        "official_loader_found": False,
        "absence_claim_scope": "Inspected local supplied PDFs, vendor snapshot and project-owned TB/driver only; no claim about unseen organizer assets.",
        "script_sha256": sha(Path(__file__)),
    })
    corpus = json.loads(BUDGET.read_text(encoding="utf-8"))["candidates"]["global_rice32"]
    rows = []
    for layer in corpus["layers"]:
        for sample in layer["samples"]:
            i = 202 + math.ceil(sample["x_bits"]/32) + sum(math.ceil(n/32) for n in sample["w_group_bits"])
            o = 17 + sum(math.ceil(n/32) for n in sample["y_tile_bits"])
            assert i == sample["input_words"] and o == sample["output_words"]
            # Current engine writes magic=0 once, then final magic=Q8Y1 once.
            # The frozen corpus budget counted only the final 17-word header.
            rows.append({"layer": layer["layer"], "sample_index": sample["sample_index"],
                         "input_words": i, "output_unique_words": o, "actual_output_write_commands": o+1,
                         "strict_r1_w1_service_lower_bound": 2*i+o+1,
                         "strict_r2_w1_service_lower_bound": 3*i+o+1,
                         "prefix202_then_preloaded_core_floor": 202+9355,
                         "x_words": math.ceil(sample["x_bits"]/32),
                         "w_words": [math.ceil(n/32) for n in sample["w_group_bits"]]})
    assert len(rows) == 3072
    budget = FREQUENCY / TARGET
    fields = ("input_words", "output_unique_words", "actual_output_write_commands",
              "strict_r1_w1_service_lower_bound", "strict_r2_w1_service_lower_bound")
    first = json.loads(SOC.read_text(encoding="utf-8"))
    metrics = first["layers"][0]["metrics"]
    actual_sample = next(r for r in rows if r["layer"] == 0 and r["sample_index"] == first["sample_index"])
    assert actual_sample["input_words"] == metrics["reads"]
    assert actual_sample["actual_output_write_commands"] == metrics["writes"]
    r1 = [r["strict_r1_w1_service_lower_bound"] for r in rows]
    result = {
        "schema": "qingyu-streaming-loader-conditional-budget-v1",
        "analysis_completed": True, "hardware_verified": False, "acceptance_passed": False,
        "clock_hz_assumed_not_sta_signed": FREQUENCY, "target_tasks_per_second_strictly_greater": TARGET,
        "cycle_limit": budget, "single_integer_task_largest_passing_cycles": math.ceil(budget)-1,
        "tasks": len(rows), "summary": {field: summary([r[field] for r in rows]) for field in fields},
        "strict_r1_w1_service_floor_over_limit_tasks": sum(v >= budget for v in r1),
        "strict_r1_w1_mean_floor_headroom": budget - statistics.mean(r1),
        "largest_average_read_cost_allowed_by_service_only": (budget-statistics.mean(r["input_words"]+r["actual_output_write_commands"] for r in rows))/statistics.mean(r["input_words"] for r in rows),
        "input_raw_fallback_max_words": 202+math.ceil(50886/32)+8*math.ceil(16448/32),
        "output_raw_fallback_max_unique_words": 17+16*math.ceil(12722/32),
        "raw_fallback_strict_r1_w1_service_floor": 2*(202+math.ceil(50886/32)+8*math.ceil(16448/32))+(17+16*math.ceil(12722/32))+1,
        "observed_first_soc_task": {
            "result": str(SOC.relative_to(ROOT)).replace("\\", "/"), "sample_index": first["sample_index"],
            "metrics": metrics,
            "serial_initial_loader_one_write_per_cycle_optimistic_total": metrics["cpu_setup_to_ack"]+metrics["reads"],
            "status": "Conditional sum with an ideal serial initial loader, not a measured strict window; sample 9 is generated silence.",
        },
        "assumptions": [
            "Same unmodified official 32-bit fabric, one shared-slave ingress; every source write/read and output write is real.",
            "Loader packet is the existing frozen Rice layout; no duplicate source/live copy and no runtime matrix preprocessing.",
            "R1/W1 are optimistic command-service costs, not guaranteed by cold-cache, alternating streams, fairness or loader timing.",
            "All decoder/core/CPU/fill/drain/validity overhead not overlapped with service must be added.",
            "Corpus is 256 existing validation samples x 12 layers, not official selected 12 tasks or unseen 600 samples.",
        ],
        "rows": rows,
    }
    save("budget.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
