"""Evidence-linked service and compute budgets; never a measured PPA result.

The scalar service model assumes saturated traffic at the stated slave II.
Startup, drain, CPU, codec, and data-dependency bubbles are not zero in RTL;
the max(service, compute) comparison is only an optimistic lower bound.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(values, frequency, target):
    average = mean(values)
    return {
        "service_cycles_mean": average,
        "service_cycles_min": min(values),
        "service_cycles_max": max(values),
        "task_s_upper_bound_from_mean_service": frequency / average,
        "samples_below_budget_ignoring_other_work": sum(v < frequency / target for v in values),
        "samples": len(values),
    }


def budget(samples, frequency, target):
    modes = {
        "synchronous_preloaded_r2_w2": lambda i, o: 2 * i + 2 * o,
        "fastwrite_preloaded_r2_w1": lambda i, o: 2 * i + o,
        "fastwrite_initial_write_then_read_r2_w1": lambda i, o: 3 * i + o,
        "fastwrite_initial_write_captured_no_reread": lambda i, o: i + o,
        "hypothetical_read_hit_preloaded_r1_w1": lambda i, o: i + o,
        "hypothetical_read_hit_initial_write_then_read_r1_w1": lambda i, o: 2 * i + o,
    }
    return {
        "mean_input_words": mean(i for i, _ in samples),
        "mean_output_words": mean(o for _, o in samples),
        "modes": {name: stats([fn(i, o) for i, o in samples], frequency, target)
                  for name, fn in modes.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    frequency, target = 150_000_000, 10_450
    source_paths = {
        "huffman": "build/lossless_command_budget_20261111/result.json",
        "deflate": "build/deflate_command_budget_20261111/result.json",
        "fabric": "build/memfab_bandwidth/20261111T153331030931Z/result.json",
        "pair_identity": "build/winograd_integer_identity_20261111/result.json",
        "precision_tasks": "build/precision_tasks_20261111_r1/result.json",
    }
    sources = {key: json.loads((args.root / path).read_text(encoding="utf-8"))
               for key, path in source_paths.items()}
    for key in ("huffman", "deflate", "fabric", "pair_identity"):
        assert sources[key]["passed"], key
    huffman = [(sample["input_words"], sample["output_words"])
               for layer in sources["huffman"]["layers"] for sample in layer["samples_commands"]]
    deflate = [(sample["input_words"], sample["output_words"])
               for layer in sources["deflate"]["layers"] for sample in layer["samples"]]
    assert len(huffman) == len(deflate) == 12 * 256
    biases = [(layer["training_choice"]["bias_min"], layer["training_choice"]["bias_max"])
              for layer in sources["deflate"]["layers"]]
    assert all(-32768 <= low <= high < 32768 for low, high in biases)
    saved_bias_words = 512 - 128
    raw = {"int16_legacy_bias64": [(11936, 12672)],
           "int8_legacy_bias64": [(6256, 6336)],
           "int8_bias16": [(5872, 6336)],
           "huffman_int8_legacy_bias64": huffman,
           "huffman_int8_bias16": [(i - saved_bias_words, o) for i, o in huffman],
           "deflate_int8_legacy_bias64": deflate,
           "deflate_int8_bias16": [(i - saved_bias_words, o) for i, o in deflate]}
    bounds = {key: budget(value, frequency, target) for key, value in raw.items()}
    pair_main = 13 * 16 * 32
    x_factors, w_factors = 13 * 32, 16 * 32
    pair_base = pair_main + x_factors + w_factors
    assert pair_base == 7584
    report = {
        "schema": "qingyu-transport-compute-feasibility-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_completed": True,
        "acceptance_passed": False,
        "rtl_measurement": False,
        "official_loader_start": "OPEN; no hardware loader implementation in audited local files",
        "frequency_hz_assumed": frequency,
        "target_task_s_strictly_greater_than": target,
        "target_mean_cycles_strictly_less_than": frequency / target,
        "sources": {key: {"path": path, "sha256": digest(args.root / path)}
                    for key, path in source_paths.items()},
        "script_sha256": digest(Path(__file__)),
        "bias16": {"valid_only_for_frozen_policy": "x8_w8_y8_h0",
                   "observed_min": min(low for low, _ in biases),
                   "observed_max": max(high for _, high in biases),
                   "input_words_saved": saved_bias_words,
                   "required_format_change": "explicit signed16 container, sign extension, range rejection"},
        "transport": bounds,
        "compute": {
            "direct_4row_64mac_main_steps": 25 * 16 * 64,
            "direct_8row_128mac_main_steps": 13 * 16 * 64,
            "direct_16row_256mac_main_steps": 7 * 16 * 64,
            "pair_8row_128multipliers": {
                "main_steps": pair_main,
                "separate_x_factor_array_steps": x_factors,
                "separate_w_factor_array_steps": w_factors,
                "base_steps_including_all_factors": pair_base,
                "output_vectors_of_128_lanes": 13 * 16,
                "extra_cycles_formula": "208*(init_cycles_per_vector+pipeline_drain_cycles_per_vector)+other_stalls",
                "single_factor_multiplier_serial_total_steps": pair_main + 99 * 32 + 256 * 32,
                "factor_hardware_counted": True,
                "required_private_bandwidth_bits_per_main_step": {"x": 8 * 2 * 8, "w": 16 * 2 * 8},
                "minimum_pack": "adjacent K INT8 pairs in each 16-bit private SRAM word",
                "four_lane_quantize_output_cycles_without_overlap": 99 * 256 // 4,
                "factors_computed_offline": False,
            },
            "width_proof": {
                "operand_signed_bits": 8, "pair_sum_signed_bits": 9,
                "pair_product_signed_bits": 18, "factor_signed_bits": 21,
                "bias_mode_signed_bits": 16,
                "prefix_absolute_upper_bound": 32768 + 2 * 32 * 16384 + 32 * 65536,
                "prefix_minimum_safe_signed_bits_by_triangle_bound": 23,
                "proposed_accumulator_signed_bits": 24,
                "legacy_bias48_supported_by_this_bound": False,
            },
            "multiplier_partial_product_proxy_only": {
                "pair128_9x9": 128 * 9 * 9,
                "direct256_8x8": 256 * 8 * 8,
                "ratio": (128 * 9 * 9) / (256 * 8 * 8),
                "not_cell_area": True,
            },
        },
        "limits": [
            "Service sums exclude initial/final latency and all contention/control stalls.",
            "R2/W1 support is the measured saturated microtest slave contract, not a full-SoC result.",
            "R1/W1 is a hypothetical hit-only read-ahead contract, not a measured design or permission.",
            "Initial write capture requires correct bus-committed data, buffers, ordering, and official loader compatibility.",
            "max(service,compute) is an optimistic overlap bound; no dependency-correct schedule is claimed.",
            "Codec symbol throughput, tables, variable-length buffering, area, energy and STA remain unimplemented.",
            "No frozen RTL, task definition, numeric configuration or official bus parameter is changed.",
        ],
    }
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output / "result.json"),
                      "target_cycles": frequency / target,
                      "pair_base_steps": pair_base,
                      "fastwrite_preloaded_bias16": {key: value["modes"]["fastwrite_preloaded_r2_w1"]
                                                     for key, value in bounds.items() if "bias16" in key}}, indent=2))


if __name__ == "__main__":
    main()
