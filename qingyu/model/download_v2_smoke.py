"""Read a bounded prefix of the official V2 archive for a few WAV smoke inputs.

No full dataset download/extraction is performed. These first archive entries
are not representative of all classes and must never be called a test set.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import urllib.request

URL = "https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_v0.02.tar.gz"


class BoundedStream:
    def __init__(self, response, limit):
        self.response, self.remaining = response, limit

    def read(self, count=-1):
        if self.remaining <= 0:
            raise OSError("compressed archive prefix budget exhausted")
        count = self.remaining if count < 0 else min(count, self.remaining)
        data = self.response.read(count)
        self.remaining -= len(data)
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=4)
    parser.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
    args = parser.parse_args()
    if not 1 <= args.samples <= 32 or args.max_bytes <= 0:
        parser.error("samples must be 1..32 and max-bytes positive")
    args.output.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(URL, headers={"Range": f"bytes=0-{args.max_bytes - 1}"})
    records = []
    with urllib.request.urlopen(request, timeout=30) as response:
        headers = {key: response.headers.get(key) for key in ("ETag", "Last-Modified", "Content-Range")}
        bounded = BoundedStream(response, args.max_bytes)
        with tarfile.open(fileobj=bounded, mode="r|gz") as archive:
            for member in archive:
                path = PurePosixPath(member.name)
                if not member.isfile() or path.suffix.lower() != ".wav" or "_background_noise_" in path.parts:
                    continue
                if path.is_absolute() or ".." in path.parts or len(path.parts) != 2 or member.size > 128000:
                    raise ValueError("unexpected archive member name/type/size")
                payload = archive.extractfile(member).read()
                if len(payload) != member.size:
                    raise OSError("incomplete WAV payload")
                target = args.output.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                records.append({"archive_member": member.name, "bytes": len(payload),
                                "sha256": hashlib.sha256(payload).hexdigest()})
                if len(records) == args.samples:
                    break
    if len(records) != args.samples:
        raise OSError("archive prefix did not contain enough speech WAVs")
    manifest = {"kind": "OFFICIAL_V2_ARCHIVE_PREFIX_WAV_SMOKE", "source_url": URL,
                "source_headers": headers, "compressed_byte_budget": args.max_bytes,
                "compressed_bytes_read": args.max_bytes - bounded.remaining,
                "representative_dataset": False, "official_accuracy_evaluation": False,
                "samples": records}
    (args.output / "download_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "downloaded_official_v2_wav_smoke", "samples": len(records),
                      "compressed_bytes_read": manifest["compressed_bytes_read"]}))


if __name__ == "__main__":
    main()
