"""Inspect a local split ZIP and extract only selected standard-cell Liberty files.

No network access and no full-archive concatenation/extraction are performed.
The source archive is opened read-only. Cadence cds.lib and HSPICE .lib files
are not treated as standard-cell Liberty libraries.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import io
import json
import re
import shutil
from pathlib import Path
from zipfile import ZipFile


class SplitZipReader(io.RawIOBase):
    """Seekable virtual concatenation, backed by read-only part handles."""

    def __init__(self, parts: list[Path]):
        super().__init__()
        self.paths = parts
        self.sizes = [part.stat().st_size for part in parts]
        self.starts = [0]
        for size in self.sizes:
            self.starts.append(self.starts[-1] + size)
        self.handles = [part.open("rb") for part in parts]
        self.position = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            target = offset
        elif whence == io.SEEK_CUR:
            target = self.position + offset
        elif whence == io.SEEK_END:
            target = self.starts[-1] + offset
        else:
            raise ValueError("invalid seek origin")
        if target < 0:
            raise ValueError("negative seek")
        self.position = target
        return target

    def read(self, size=-1):
        remaining = max(0, self.starts[-1] - self.position)
        if size < 0:
            size = remaining
        size = min(size, remaining)
        blocks = []
        while size:
            disk = bisect.bisect_right(self.starts, self.position) - 1
            local = self.position - self.starts[disk]
            count = min(size, self.sizes[disk] - local)
            handle = self.handles[disk]
            handle.seek(local)
            block = handle.read(count)
            if len(block) != count:
                raise OSError("unexpected short read from split ZIP part")
            blocks.append(block)
            self.position += count
            size -= count
        return b"".join(blocks)

    def close(self):
        for handle in getattr(self, "handles", []):
            handle.close()
        super().close()


def archive_parts(source: Path) -> list[Path]:
    final = source / "pdk.zip" if source.is_dir() else source
    matches = []
    for path in final.parent.glob(final.stem + ".z[0-9][0-9]"):
        matches.append((int(path.suffix[2:]), path))
    matches.sort()
    if matches and [n for n, _ in matches] != list(range(1, len(matches) + 1)):
        raise ValueError("split ZIP part sequence has a gap")
    if not final.is_file():
        raise FileNotFoundError(final)
    return [path for _, path in matches] + [final]


def repair_disk_offsets(archive: ZipFile, reader: SplitZipReader):
    # Python adds the apparent concatenation displacement to every entry,
    # while a split ZIP stores each local-header offset relative to its disk.
    # Determine that displacement from the central directory as seen on the
    # final part; do not assume equal-sized parts or copy the entire archive.
    with ZipFile(reader.paths[-1]) as last_part:
        relative_directory = last_part.start_dir
    displacement = archive.start_dir - relative_directory
    infos = archive.infolist()
    for info in infos:
        if not 0 <= info.volume < len(reader.paths):
            raise ValueError(f"invalid disk number for {info.filename}")
        disk_offset = info.header_offset - displacement
        if not 0 <= disk_offset < reader.sizes[info.volume]:
            raise ValueError(f"invalid disk-relative offset for {info.filename}")
        info.header_offset = reader.starts[info.volume] + disk_offset
    # Recompute the overlap limits used by ZipFile.open after offset repair.
    boundary = archive.start_dir
    for info in sorted(infos, key=lambda entry: entry.header_offset, reverse=True):
        info._end_offset = boundary
        boundary = info.header_offset


def checksum(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def liberty_summary(path: Path):
    summary = {"cell_count": 0}
    header = []
    cell_pattern = re.compile(r"^\s*cell\s*\(\s*([^\)]+)\s*\)")
    with path.open("r", encoding="ascii", errors="replace") as stream:
        for number, line in enumerate(stream):
            if number < 500:
                header.append(line)
            if cell_pattern.match(line):
                summary["cell_count"] += 1
    text = "".join(header)
    for key in ("time_unit", "voltage_unit", "current_unit", "leakage_power_unit",
                "nom_voltage", "nom_temperature", "nom_process"):
        match = re.search(r"\b" + key + r"\s*:\s*([^;]+);", text)
        if match:
            summary[key] = match.group(1).strip().strip('"')
    capacitance = re.search(r"capacitive_load_unit\s*\(([^)]+)\)", text)
    if capacitance:
        summary["capacitive_load_unit"] = capacitance.group(1).strip()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--all-corners", action="store_true",
                        help="also extract FF Liberty corners; default is TT and SS")
    args = parser.parse_args()
    parts = archive_parts(args.source.resolve())
    output = args.output.resolve()
    report = {
        "source": str(args.source.resolve()),
        "parts": [{"name": path.name, "bytes": path.stat().st_size} for path in parts],
        "method": "read-only virtual concatenation with per-disk local-header offsets",
        "contains_proprietary_data": True,
        "external_upload_performed": False,
        "extracted": [],
    }
    with SplitZipReader(parts) as reader, ZipFile(reader) as archive:
        repair_disk_offsets(archive, reader)
        infos = archive.infolist()
        report["entry_count"] = len(infos)
        report["total_uncompressed_bytes"] = sum(info.file_size for info in infos)
        prefix = "pdk/sc9mc_base_rvt_c40/r1p1/"
        libraries = [info for info in infos
                     if info.filename.startswith(prefix + "lib/")
                     and info.filename.endswith(".lib")]
        report["standard_cell_liberty_corners"] = [
            {"member": info.filename, "bytes": info.file_size, "disk": info.volume}
            for info in libraries
        ]
        report["standard_cell_db_corners"] = [
            {"member": info.filename, "bytes": info.file_size}
            for info in infos if info.filename.startswith(prefix + "db/")
            and info.filename.endswith(".db")
        ]
        macro_terms = ("sram", "spsram", "dpsram", "memory", "memcompiler",
                       "ramcompiler", "16x128", "16x1024", "16x4096")
        macro_names = [info.filename for info in infos
                       if any(term in info.filename.lower() for term in macro_terms)]
        report["specified_sram_macro_check"] = {
            "status": "name_matches_found" if macro_names else "not_found_by_member_names",
            "searched_terms": list(macro_terms),
            "matched_members": macro_names,
            "limitation": "Member names only; nested archives and cell contents not exhaustively searched.",
        }
        report["nested_archives"] = [info.filename for info in infos
            if info.filename.lower().endswith((".zip", ".rar", ".7z", ".tgz", ".tar.gz"))]
        selected = [info for info in libraries if args.all_corners
                    or "_tt_" in info.filename or "_ss_" in info.filename]
        selected += [info for info in infos if info.filename.startswith(prefix)
                     and Path(info.filename).name.lower().startswith("readme-smic-")]
        for info in selected:
            subdirectory = "lib" if info.filename.endswith(".lib") else "docs"
            destination = output / "stdcell" / subdirectory / Path(info.filename).name
            if not destination.resolve().is_relative_to(output):
                raise ValueError("unsafe extraction destination")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            entry = {"member": info.filename, "path": str(destination),
                     "bytes": destination.stat().st_size, "sha256": checksum(destination),
                     "zip_crc32": f"{info.CRC:08x}"}
            if subdirectory == "lib":
                entry["liberty"] = liberty_summary(destination)
            report["extracted"].append(entry)
            print(json.dumps({"extracted": destination.name, "bytes": entry["bytes"],
                              "liberty": entry.get("liberty")}, ensure_ascii=False), flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"report": str(args.report.resolve()), "entries": report["entry_count"],
                      "sram_check": report["specified_sram_macro_check"]["status"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
