"""Resumable download of the official V2 archive, with MD5 and SHA256 checks.

The MD5/size identify the immutable Google object observed by the source check.
Partial downloads are kept. Progress is saved next to the target every2 seconds.
Optional extraction rejects links and paths outside its dedicated directory.
"""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import time
import urllib.request

URL = "https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_v0.02.tar.gz"
EXPECTED_BYTES = 2428923189
EXPECTED_MD5 = "6b74f3901214cb2c2934e98196829835"


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def save(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digests(path):
    md5, sha = hashlib.md5(), hashlib.sha256()
    if path.exists():
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                md5.update(block)
                sha.update(block)
    return md5, sha


def extract(archive_path, destination, status_path):
    destination = destination.resolve()
    marker = destination / ".qingyu_extraction.json"
    if destination.exists() and any(destination.iterdir()):
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")).get("source_md5") != EXPECTED_MD5:
            raise ValueError("existing nonempty destination is not a resumable extraction from this source")
    destination.mkdir(parents=True, exist_ok=True)
    save(marker, {"state": "extracting", "source_md5": EXPECTED_MD5, "timestamp_utc": timestamp()})
    count, wav_count = 0, 0
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("unsafe archive path")
            target = destination.joinpath(*relative.parts).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("archive target escapes destination")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError("archive links and special files are not allowed")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
            if target.stat().st_size != member.size:
                raise OSError("extracted file size mismatch")
            count += 1
            wav_count += target.suffix.lower() == ".wav"
            if count % 1000 == 0:
                save(status_path, {"state": "extracting", "files": count, "wav_files": wav_count,
                                   "destination": str(destination), "timestamp_utc": timestamp()})
                print(json.dumps({"state": "extracting", "files": count}), flush=True)
    result = {"state": "extracted", "source_md5": EXPECTED_MD5, "files": count,
              "wav_files": wav_count, "timestamp_utc": timestamp()}
    save(marker, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/downloads/speech_commands_v0.02.tar.gz"))
    parser.add_argument("--extract-to", type=Path)
    parser.add_argument("--retries", type=int, default=12)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".part")
    status_path = output.with_name(output.name + ".status.json")
    manifest_path = output.with_name(output.name + ".manifest.json")
    if output.exists():
        md5, sha = digests(output)
        if output.stat().st_size != EXPECTED_BYTES or md5.hexdigest() != EXPECTED_MD5:
            raise ValueError("existing completed target has incorrect size/checksum; preserved without overwrite")
    else:
        if partial.exists() and partial.stat().st_size > EXPECTED_BYTES:
            raise ValueError("partial download is larger than expected")
        md5, sha = digests(partial)
        offset = partial.stat().st_size if partial.exists() else 0
        initial_offset, started = offset, time.monotonic()
        retries, last_status, last_log = 0, 0.0, 0.0
        while offset < EXPECTED_BYTES:
            try:
                request = urllib.request.Request(URL, headers={"Range": f"bytes={offset}-",
                                                               "If-Match": f'"{EXPECTED_MD5}"'})
                with urllib.request.urlopen(request, timeout=45) as response:
                    if response.headers.get("ETag", "").strip('"') != EXPECTED_MD5:
                        raise ValueError("source ETag changed")
                    if offset and (response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")):
                        raise ValueError("server did not honor resume offset")
                    with partial.open("ab") as target:
                        while offset < EXPECTED_BYTES:
                            block = response.read(min(256 * 1024, EXPECTED_BYTES - offset))
                            if not block:
                                raise OSError("source ended before expected size")
                            target.write(block)
                            md5.update(block)
                            sha.update(block)
                            offset += len(block)
                            now = time.monotonic()
                            if now - last_status >= 2:
                                target.flush()
                                progress = {"state": "downloading", "source_url": URL, "bytes": offset,
                                            "expected_bytes": EXPECTED_BYTES, "percent": 100 * offset / EXPECTED_BYTES,
                                            "bytes_per_second": (offset - initial_offset) / max(now - started, 1e-9),
                                            "retries": retries, "timestamp_utc": timestamp()}
                                save(status_path, progress)
                                last_status = now
                                if now - last_log >= 10:
                                    print(json.dumps(progress), flush=True)
                                    last_log = now
                retries = 0
            except Exception as error:
                retries += 1
                save(status_path, {"state": "retrying" if retries <= args.retries else "failed",
                                   "bytes": offset, "expected_bytes": EXPECTED_BYTES,
                                   "error": str(error), "retries": retries, "timestamp_utc": timestamp()})
                if retries > args.retries or isinstance(error, ValueError):
                    raise
                time.sleep(min(2 * retries, 15))
        if md5.hexdigest() != EXPECTED_MD5:
            save(status_path, {"state": "checksum_failed", "bytes": offset,
                               "actual_md5": md5.hexdigest(), "expected_md5": EXPECTED_MD5})
            raise OSError("full archive MD5 mismatch; partial preserved")
        partial.replace(output)
    manifest = {"state": "downloaded", "source_url": URL, "bytes": EXPECTED_BYTES,
                "md5": md5.hexdigest(), "sha256": sha.hexdigest(), "timestamp_utc": timestamp()}
    save(manifest_path, manifest)
    save(status_path, manifest)
    print(json.dumps(manifest), flush=True)
    if args.extract_to:
        result = extract(output, args.extract_to, status_path)
        save(status_path, result)
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
