"""Prepare private standard-cell DB files from the user's local split PDK ZIP.

No network connection or server upload is performed. The output ZIP contains
proprietary PDK data and must remain within the authorized design environment.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile

from inspect_pdk import SplitZipReader, archive_parts, repair_disk_offsets

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "pdk/sc9mc_base_rvt_c40/r1p1/"
CORNERS = {
    "tt_25c": "sc9mc_logic0040ll_base_rvt_c40_tt_typical_max_1p10v_25c.db",
    "ss_125c": "sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db",
    "ss_m40c": "sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_m40c.db",
    "ff_125c": "sc9mc_logic0040ll_base_rvt_c40_ff_typical_min_1p21v_125c.db",
    "ff_m40c": "sc9mc_logic0040ll_base_rvt_c40_ff_typical_min_1p21v_m40c.db",
}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def setup_source(selected):
    corners = "\n".join(f"    {key} {name}" for key, name in selected.items())
    return """# Source from inside dc_shell; default is TT, not a timing signoff.
# To select another provided corner before sourcing:
# set QINGYU_STDCELL_CORNER ss_125c
set qy_setup_dir [file normalize [file dirname [info script]]]
if {![info exists QINGYU_STDCELL_CORNER]} { set QINGYU_STDCELL_CORNER tt_25c }
array set qy_db_names {
""" + corners + """
}
if {![info exists qy_db_names($QINGYU_STDCELL_CORNER)]} {
    error "Unknown corner: $QINGYU_STDCELL_CORNER"
}
set qy_db_dir [file join $qy_setup_dir db]
set qy_db_file [file join $qy_db_dir $qy_db_names($QINGYU_STDCELL_CORNER)]
if {![file isfile $qy_db_file]} { error "Missing DB file: $qy_db_file" }
set_app_var search_path [linsert [get_app_var search_path] 0 $qy_db_dir]
set_app_var target_library [list $qy_db_file]
set_app_var link_library [list * $qy_db_file]
read_db $qy_db_file
printvar target_library
printvar link_library
list_libs
puts "Standard-cell library setup completed. SRAM libraries are still required for macro synthesis."
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        default=ROOT.parent / "H77.SMIC 40nm工艺库PDK")
    parser.add_argument("--output", type=Path,
                        default=ROOT.parent / "output/eda/qingyu_stdcell_db.zip")
    parser.add_argument("--corners", nargs="+", choices=list(CORNERS),
                        default=list(CORNERS))
    args = parser.parse_args()
    selected = {key: CORNERS[key] for key in args.corners}
    if "tt_25c" not in selected:
        parser.error("include tt_25c so the default load script has its library")
    source = args.source.resolve()
    output = args.output.resolve()
    if output.suffix.lower() != ".zip":
        parser.error("--output must end with .zip")
    destination = ROOT / "local_pdk/stdcell/db"
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    parts = archive_parts(source)
    with SplitZipReader(parts) as reader, zipfile.ZipFile(reader) as archive:
        repair_disk_offsets(archive, reader)
        for corner, name in selected.items():
            member = PREFIX + "db/" + name
            info = archive.getinfo(member)
            target = destination / name
            with archive.open(info) as stream, target.open("wb") as sink:
                shutil.copyfileobj(stream, sink, length=1024 * 1024)
            entries.append({"corner": corner, "member": member,
                            "bytes": target.stat().st_size,
                            "sha256": sha256(target),
                            "zip_crc32": f"{info.CRC:08x}"})
    report = {
        "contains_proprietary_data": True,
        "external_upload_performed": False,
        "dc_read_test_performed": False,
        "source": str(source),
        "files": entries,
        "scope": "standard cells only; no specified SRAM macros",
    }
    texts = {
        "load_stdcell.tcl": setup_source(selected),
        "README.txt": (
            "PRIVATE STANDARD-CELL LIBRARIES: authorized contest use only.\n"
            "Unzip in your contest account Desktop directory. In dc_shell run:\n"
            "source ~/Desktop/qingyu_stdcell_db/load_stdcell.tcl\n"
            "The default corner is TT 1.10V/25C. Included corners: "
            + ", ".join(selected) + ".\n"
            "If included, select another corner before sourcing, for example:\n"
            "set QINGYU_STDCELL_CORNER ss_125c\n"
            "This verifies loading only when run in DC. No SRAM macro data or\n"
            "contest timing/area/power pass is provided by this package.\n"
        ),
        "provenance.json": json.dumps(report, ensure_ascii=True, indent=2) + "\n",
    }
    payloads = {"db/" + name: (destination / name).read_bytes()
                for name in selected.values()}
    readme = ROOT / "local_pdk/stdcell/docs/README-smic-logic0040ll-sc9mc_base_rvt_c40.txt"
    if readme.is_file():
        payloads["vendor_readme.txt"] = readme.read_bytes()
    payloads.update({name: value.encode("utf-8") for name, value in texts.items()})
    payloads["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(payloads.items())).encode("ascii")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for name, data in sorted(payloads.items()):
            archive.writestr("qingyu_stdcell_db/" + name, data)
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None
        for name, data in payloads.items():
            assert archive.read("qingyu_stdcell_db/" + name) == data, name
    temporary.replace(output)
    print(json.dumps({"archive": str(output), "bytes": output.stat().st_size,
                      "sha256": sha256(output), "db_corners": len(selected),
                      "external_upload_performed": False}, indent=2))


if __name__ == "__main__":
    main()
