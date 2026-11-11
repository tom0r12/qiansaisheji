"""Create a small, explicit allow-list archive for the contest EDA server.

The archive contains no credentials, private libraries, datasets or binaries.
It is a synthesis preparation subset, not a complete contest submission.
"""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "rtl/qingyu_accel.sv",
    "rtl/qingyu_sram16.sv",
    "rtl/qingyu_fio.sv",
    "scripts/synth_dc.tcl",
    "scripts/server_probe.sh",
    "constraints/accelerator.sdc",
    "docs/eda_server.md",
    "docs/synthesis.md",
    "docs/engineering_contract.md",
    "docs/numeric_format.md",
)
README = """Qingyu EDA server preparation subset

1. Unpack in your contest account's Desktop directory, then enter this folder.
2. Run: sh scripts/server_probe.sh
   Optionally pass organizer-provided shared library directories as arguments.
3. Read docs/eda_server.md and docs/synthesis.md before using DC.

This is not a complete submission or a ready-to-run macro-mapped design.
synth_dc.tcl requires actual standard-cell DB files, SRAM DB files, a macro
wrapper and contest I/O constraints. The included qingyu_sram16.sv is only a
behavioral simulation reference; synth_dc.tcl intentionally does not read it.
The DC entry synthesizes qingyu_accel only; the separate FIO adapter and SRAM
areas must be included in the final accelerator/interface total.

No passwords, PDK libraries, model data, installed tools or server credentials
are included. No server connection, upload or tool run has been performed.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT.parent / "output/eda/qingyu_dc_start.zip")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.suffix.lower() != ".zip":
        parser.error("--output must end with .zip")
    payloads = {name: (ROOT / name).read_bytes() for name in FILES}
    # Always use Unix newlines, including when built on Windows.
    for name in payloads:
        payloads[name] = payloads[name].replace(b"\r\n", b"\n")
    payloads["README.txt"] = README.encode("utf-8")
    sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n"
                   for name, data in sorted(payloads.items()))
    payloads["SHA256SUMS"] = sums.encode("ascii")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for name, data in sorted(payloads.items()):
            info = zipfile.ZipInfo("qingyu_dc_start/" + name,
                                   date_time=(2026, 10, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Archive failed its CRC check")
        for name, data in payloads.items():
            if archive.read("qingyu_dc_start/" + name) != data:
                raise RuntimeError(f"Archive content mismatch: {name}")
    temporary.replace(output)
    print(f"Created {output} ({output.stat().st_size:,} bytes, {len(payloads)} files)")
    print(f"SHA256 {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
