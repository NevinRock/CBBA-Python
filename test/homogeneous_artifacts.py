"""Portable minimal evidence for homogeneous audits; standard library only.

The gzip JSONL stores exact trial records and run-time source witnesses.
Public metadata omits machine-local absolute paths.
It excludes derived figures/reports, redundant source copies and execution logs.
"""
import argparse
import base64
from contextlib import contextmanager
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile

BUNDLE_NAME = "audit_evidence.jsonl.gz"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def public_metadata(payload, private_field):
    record = json.loads(payload)
    if private_field not in record:
        return payload
    del record[private_field]
    return json.dumps(record, indent=2).encode("utf-8")


def pack_evidence(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(f"Preserve existing evidence: {destination}")
    raw = json.loads((source / "raw_files_sha256.json").read_text(encoding="utf-8"))
    preflight = json.loads((source / "preflight.json").read_text(encoding="utf-8"))
    names = set(raw) | {"raw_files_sha256.json", "preflight.json"}
    names |= {"source_snapshot/" + name.replace("\\", "/") for name in preflight["source_sha256"]}
    public_records = {}
    for name, field in (("manifest.json", "config_path"), ("preflight.json", "python_executable")):
        if name not in names:
            continue
        original = (source / name).read_bytes()
        if name in raw and sha(original) != raw[name]:
            raise ValueError(f"Raw hash mismatch: {name}")
        public_records[name] = public_metadata(original, field)
    public_raw = {name: sha(public_records[name]) if name in public_records else digest
                  for name, digest in raw.items()}
    public_records["raw_files_sha256.json"] = json.dumps(public_raw, indent=2).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 and no source filename make compressed bytes reproducible.
    with destination.open("xb") as stream:
        with gzip.GzipFile(fileobj=stream, filename="", mode="wb", mtime=0, compresslevel=9) as compressed:
            for name in sorted(names):
                payload = (source / name).read_bytes()
                if name in raw and sha(payload) != raw[name]:
                    raise ValueError(f"Raw hash mismatch: {name}")
                payload = public_records.get(name, payload)
                record = {"path": name, "sha256": sha(payload),
                          "bytes_base64": base64.b64encode(payload).decode("ascii")}
                compressed.write((json.dumps(record, separators=(",", ":")) + "\n").encode("utf-8"))
    return {"records": len(names), "bytes": destination.stat().st_size,
            "sha256": sha(destination.read_bytes())}


def unpack_evidence(bundle, destination):
    destination = Path(destination).resolve()
    seen = set()
    with gzip.open(bundle, "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            name = record["path"]
            parts = PurePosixPath(name)
            if parts.is_absolute() or ".." in parts.parts or "\\" in name or ":" in name or name in seen:
                raise ValueError(f"Unsafe or duplicate evidence path: {name}")
            target = (destination / name).resolve()
            if not target.is_relative_to(destination):
                raise ValueError(f"Evidence escaped destination: {name}")
            payload = base64.b64decode(record["bytes_base64"], validate=True)
            if sha(payload) != record["sha256"]:
                raise ValueError(f"Evidence hash mismatch: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(payload)
            seen.add(name)
    return len(seen)


@contextmanager
def evidence_directory(output):
    """Yield a raw layout, transparently unpacking a compact candidate to temp."""
    output = Path(output).resolve()
    if (output / "paired_inputs").is_dir() and (output / "diagnostics").is_dir():
        yield output
        return
    bundle = output / BUNDLE_NAME
    if not bundle.is_file():
        raise FileNotFoundError(f"Need paired_inputs/ + diagnostics/, or {BUNDLE_NAME}; CSV alone cannot audit schedules")
    with tempfile.TemporaryDirectory(prefix="cbba-evidence-") as temp:
        raw = Path(temp)
        unpack_evidence(bundle, raw)
        if (output / "trials.csv").read_text(encoding="utf-8") != (raw / "trials.csv").read_text(encoding="utf-8"):
            raise ValueError("Published trials.csv differs from audit evidence")
        yield raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(pack_evidence(args.source, args.destination), indent=2))


if __name__ == "__main__":
    main()
