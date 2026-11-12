"""Portable production-configuration RTL checks using synthetic engineering data.

This exercises the accelerator component, not an E203 end-to-end task, and does
not establish official KWT accuracy, SRAM macro timing, power, or area results.
Each run has a new output directory so previous evidence is never overwritten.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ROWS, K, LANES = 99, 64, 16


def round_sat16(value: int, shift: int) -> int:
    """Round magnitude to nearest/ties-to-even, restore sign, saturate INT16."""
    magnitude = abs(value)
    quotient, remainder = divmod(magnitude, 1 << shift)
    if shift and (2 * remainder > 1 << shift or
                  (2 * remainder == 1 << shift and quotient % 2)):
        quotient += 1
    rounded = -quotient if value < 0 else quotient
    return max(-32768, min(32767, rounded))


def hex_file(path: Path, values: list[int], bits: int) -> None:
    path.write_text("".join(f"{v & ((1 << bits)-1):0{bits//4}x}\n" for v in values),
                    encoding="ascii")


def generate_vectors(directory: Path, seed: int, cases: int) -> dict:
    rng = random.Random(seed)
    evidence = []
    for case in range(cases):
        xs = [[rng.randint(-32768, 32767) for _ in range(K)] for _ in range(ROWS)]
        ws = [[rng.randint(-32768, 32767) for _ in range(LANES)] for _ in range(K)]
        bias = [rng.randint(-(1 << 39), (1 << 39)-1) for _ in range(LANES)]
        shifts = [rng.choice((0, 1, 2, 8, 15, 16, 24, 31, 47)) for _ in range(LANES)]
        # Independent directed channels ensure ties in both signs, both INT16
        # saturation limits, zero shift and the maximum supported right shift.
        directed = [(3, 1), (5, 1), (-3, 1), (-5, 1),
                    (32768, 0), (-32769, 0), ((1 << 46)+1, 47), (-(1 << 46)-1, 47)]
        for directed_index, (b, s) in enumerate(directed):
            # Rotate the directed channels so every MAC lane also receives
            # nonzero random operands in a multi-case run.
            lane = (directed_index + 3*case) % LANES
            bias[lane], shifts[lane] = b, s
            for row in ws:
                row[lane] = 0
        xs[0] = [-32768 if j % 2 else 32767 for j in range(K)]
        xs[-1] = [0] * K
        ys = []
        saturated = 0
        for x in xs:
            y = []
            for lane in range(LANES):
                value = bias[lane]
                for k in range(K):
                    value += x[k] * ws[k][lane]
                    if not -(1 << 47) <= value < 1 << 47:
                        raise ValueError("Synthetic vector accidentally overflows INT48")
                result = round_sat16(value, shifts[lane])
                saturated += result in (-32768, 32767)
                y.append(result)
            ys.extend(y)
        metadata = []
        for b, shift in zip(bias, shifts):
            metadata += [(b >> (16*j)) & 0xffff for j in range(3)] + [shift]
        prefix = directory / f"case{case:02d}"
        hex_file(Path(str(prefix)+"_x.hex"), [v for row in xs for v in row], 16)
        w_words = [(row[j] & 0xffff) | ((row[j+1] & 0xffff) << 16)
                   for row in ws for j in range(0, LANES, 2)]
        hex_file(Path(str(prefix)+"_w.hex"), w_words, 32)
        hex_file(Path(str(prefix)+"_meta.hex"), metadata, 16)
        hex_file(Path(str(prefix)+"_expected.hex"),
                 [(ys[j] & 0xffff) | ((ys[j+1] & 0xffff) << 16)
                  for j in range(0, len(ys), 2)], 32)
        evidence.append({"case": case, "outputs": len(ys), "saturation_limit_outputs": saturated})
    return {"kind": "SYNTHETIC engineering vectors; not KWT/official precision evidence",
            "seed": seed, "cases": evidence, "shape": [ROWS, K, LANES]}


def tool_path(option: str | None, name: str) -> str:
    path = option or shutil.which(name)
    if not path or not Path(path).is_file():
        raise RuntimeError(f"{name} not found; pass --{name} with an executable path")
    return str(Path(path).resolve())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", help="RTL directory; may be repeated")
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--cases", type=int, default=3)
    parser.add_argument("--fast-consumer", action="store_true",
                        help="consume without artificial stalls; skip indexed read probes")
    parser.add_argument("--x-storage-checks", action="store_true",
                        help="read all X words after packed, MMIO and single-element writes")
    parser.add_argument("--iverilog")
    parser.add_argument("--vvp")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", help="new directory for this run; must not already exist")
    args = parser.parse_args()
    if args.cases < 2:
        parser.error("--cases must be at least 2 to exercise both reset scenarios")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = (ROOT / (args.output or f"build/candidate_checks/{timestamp}")).resolve()
    output.mkdir(parents=True, exist_ok=False)
    vectors = output / "vectors"
    vectors.mkdir()
    result = {"data": generate_vectors(vectors, args.seed, args.cases),
              "consumer_mode": "no artificial stalls" if args.fast_consumer else "random backpressure and indexed MMIO probes",
              "x_storage_checks": args.x_storage_checks,
              "scope": "accelerator-only functional regression with behavioral synchronous SRAM",
              "excluded": ["E203 end-to-end performance", "official 600-sample accuracy",
                           "foundry SRAM timing", "synthesis/STA/power/area"], "runs": []}
    result["vector_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted(vectors.glob("*.hex"))}
    result["runner_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["python_version"] = sys.version
    candidates = args.candidate or ["experiments/h1500v/opt12_wait/rtl",
                                   "experiments/h1500v/opt13_row8/rtl"]
    try:
        iv, vv = tool_path(args.iverilog, "iverilog"), tool_path(args.vvp, "vvp")
        result["tools"] = {"iverilog": iv, "vvp": vv,
            "iverilog_version": subprocess.run([iv, "-V"], capture_output=True,
                                                text=True, errors="replace").stdout.splitlines()[0]}
        for index, name in enumerate(candidates):
            candidate = (ROOT / name).resolve()
            source = candidate if candidate.suffix == ".sv" else candidate / "qingyu_accel.sv"
            work = output / f"{index:02d}_{source.parent.parent.name}"
            work.mkdir()
            sources = [ROOT / "rtl/qingyu_sram16.sv", source,
                       ROOT / "tb/tb_candidate_stream.sv"]
            entry = {"candidate": str(source), "passed": False,
                     "sha256": {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):
                                hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                     "logs": str(work)}
            result["runs"].append(entry)
            binary = work / "candidate.vvp"
            commands = [("compile", [iv, "-g2012", "-Wall", "-DQINGYU_BLOCK_COPY",
                         "-s", "tb_candidate_stream", "-o", str(binary), *map(str, sources)]),
                        ("simulate", [vv, str(binary), f"+VECTORS={vectors.as_posix()}",
                         f"+CASES={args.cases}", f"+SEED={args.seed}", f"+FAST={int(args.fast_consumer)}",
                         f"+X_STORAGE={int(args.x_storage_checks)}"])]
            for stage, command in commands:
                start = time.monotonic()
                process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                         encoding="utf-8", errors="replace", timeout=args.timeout)
                text = process.stdout + process.stderr
                (work / f"{stage}.log").write_text(text, encoding="utf-8")
                entry[stage] = {"command": command, "returncode": process.returncode,
                                "seconds": round(time.monotonic()-start, 3)}
                if process.returncode:
                    print(text[-5000:])
                    raise RuntimeError(f"{name}: {stage} failed")
                if stage == "simulate":
                    match = re.search(r"PASS candidate_stream synthetic outputs=(\d+)", text)
                    if not match:
                        raise RuntimeError(f"{name}: simulator exited without a PASS marker")
                    entry["outputs_checked"] = int(match.group(1))
                    entry["x_words_checked"] = int(re.search(r"X_STORAGE words_checked=(\d+)", text).group(1))
                    entry["case_compute_cycles"] = [int(x) for x in re.findall(r"compute_cycles=(\d+)", text)]
                    entry["store_stream_overlap_cycles"] = int(re.search(r"overlap_cycles=(\d+)", text).group(1))
            entry["passed"] = True
            print(f"PASS {name}: {entry['outputs_checked']} synthetic outputs", flush=True)
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Evidence: {output / 'result.json'}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
