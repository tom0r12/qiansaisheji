"""Reuse the frozen scalar regression to cross-check the new raw pair lane.

The frozen source is hash-verified and copied only to a new build directory.
R/C still come from the original hardware factor units. Additional checks
compare the raw lane plus the correct frame's factors against BOTH the frozen
dot implementation and the independent direct64-product scoreboard.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    here = Path(__file__).resolve().parent
    root = here.parents[2]
    frozen = here.parent / "winograd_int8"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = (args.output or root / "build" / "winograd_array_lane" / stamp).resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((frozen / "SOURCE_SHA256.json").read_text())
    for key, digest in manifest["files"].items():
        if sha(frozen / key) != digest:
            raise RuntimeError("Frozen scalar source mismatch: " + key)
    source = (frozen / "tb_winograd_int8.sv").read_text()

    def replace_once(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise RuntimeError("Unexpected frozen test structure")
        source = source.replace(old, new)

    replace_once("module tb_winograd_int8;", "module tb_winograd_array_lane;")
    replace_once("    integer a, b, c, d, k, n, target;", """
    logic raw_ready, raw_valid;
    logic signed [22:0] raw_sum;
    logic [4:0] raw_count_q = 0;
    logic raw_was_stalled = 0;
    logic signed [22:0] raw_held_sum = 0;
    longint signed raw_reference_row = 0, raw_reference_col = 0;
    longint signed raw_expected_row [0:8191], raw_expected_col [0:8191];
    winograd_int8_pair_acc32 raw_lane(.clk, .rst_n, .in_valid(d_valid), .in_ready(raw_ready),
        .in_first(raw_count_q==0), .in_last(raw_count_q==31),
        .in_x_even(dx_even), .in_x_odd(dx_odd), .in_w_even(dw_even), .in_w_odd(dw_odd),
        .out_valid(raw_valid), .out_ready(d_out_ready), .out_pair_sum(raw_sum));
    always @(posedge clk) begin
        if (!rst_n) begin raw_count_q <= 0; raw_was_stalled <= 0; end
        else begin
            if (d_valid && raw_ready) raw_count_q <= raw_count_q + 5'd1;
            if (raw_ready !== d16_ready || raw_valid !== d16_valid)
                $fatal(1, "Raw/frozen pipeline protocol differs");
            if (raw_was_stalled && (!raw_valid || raw_sum !== raw_held_sum))
                $fatal(1, "Raw pair sum changed under backpressure");
            raw_was_stalled <= raw_valid && !d_out_ready;
            raw_held_sum <= raw_sum;
        end
    end
    integer a, b, c, d, k, n, target;""")
    replace_once("                    first_cycle = cycles;", """                    first_cycle = cycles;
                    raw_reference_row = longint'($signed(d_row));
                    raw_reference_col = longint'($signed(d_col));""")
    replace_once("                    expected_dot[dwr] = dot_run; expected16[dwr] = dot_run + bias16_run;", """                    expected_dot[dwr] = dot_run; expected16[dwr] = dot_run + bias16_run;
                    raw_expected_row[dwr] = raw_reference_row;
                    raw_expected_col[dwr] = raw_reference_col;""")
    replace_once('                if (drd >= dwr) $fatal(1, "Unexpected/stale dot response");', """                if (drd >= dwr) $fatal(1, "Unexpected/stale dot response");
                if (!raw_valid || longint'($signed(raw_sum)) - raw_expected_row[drd] - raw_expected_col[drd] != expected_dot[drd])
                    $fatal(1, "Raw accumulator/frozen dot/direct64 mismatch");""")
    testbench = out / "tb_winograd_array_lane.sv"
    testbench.write_text(source)
    commands = []
    def run(argv, logfile):
        with (out / logfile).open("w") as log:
            result = subprocess.run(list(map(str, argv)), cwd=root, stdout=log, stderr=subprocess.STDOUT)
        commands.append({"argv": list(map(str, argv)), "returncode": result.returncode, "log": logfile})
        if result.returncode:
            raise RuntimeError("Failed; see " + str(out / logfile))
        return (out / logfile).read_text(errors="replace")
    vvp = out / "sim.vvp"
    sources = [frozen / "winograd_int8_factor32.sv", frozen / "winograd_int8_dot64.sv", here / "winograd_int8_pair_acc32.sv"]
    hashes = {str(p.relative_to(root)).replace("\\", "/"): sha(p) for p in sources}
    run(["G:/iverilog/bin/iverilog.exe", "-g2012", "-Wall", "-s", "tb_winograd_array_lane", "-o", vvp, *sources, testbench], "compile.log")
    for seed in [104729, 130363, 155921]:
        output = run(["G:/iverilog/bin/vvp.exe", vvp, f"+SEED={seed}"], f"seed_{seed}.log")
        if "PASS cases=2910" not in output:
            raise RuntimeError("Missing regression coverage")
        print(output.strip().splitlines()[0], flush=True)
    if hashes != {str(p.relative_to(root)).replace("\\", "/"): sha(p) for p in sources}:
        raise RuntimeError("Source changed")
    report = {"schema": "qingyu-winograd-array-raw-lane-equivalence-v1", "completed": True,
              "source_sha256": hashes, "frozen_manifest_sha256": sha(frozen / "SOURCE_SHA256.json"),
              "generator_sha256": sha(Path(__file__)), "generated_tb_sha256": sha(testbench),
              "seeds": [104729, 130363, 155921], "cases_per_seed": 2910,
              "comparison": "Raw pair-sum corrected by actual hardware factors equals frozen dot RTL and independent direct64 scoreboard",
              "formal_tool_equivalence": False, "full_array_verified": False, "commands": commands}
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print("RESULT", out / "result.json", flush=True)


if __name__ == "__main__":
    main()
