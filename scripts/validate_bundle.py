#!/usr/bin/env python3
"""Validate a Synthesus Knowledge Cloud artifact bundle against manifest.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="artifacts", help="Artifact root containing manifest.json")
    parser.add_argument("--manifest-name", default="manifest.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest_path = root / args.manifest_name
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    failures: list[str] = []
    for item in manifest.get("artifacts", []):
        rel = item["path"].replace("\\", "/")
        path = root / rel
        if not path.exists():
            failures.append(f"missing {rel}")
            continue
        size = path.stat().st_size
        if size != int(item["size"]):
            failures.append(f"size mismatch {rel}: expected {item['size']}, got {size}")
            continue
        digest = sha256_file(path)
        if digest != item["sha256"]:
            failures.append(f"sha256 mismatch {rel}")
            continue
        print(f"ok {rel}")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print(f"validated {len(manifest.get('artifacts', []))} artifacts under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
