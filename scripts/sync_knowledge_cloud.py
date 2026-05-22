#!/usr/bin/env python3
"""Download and verify the Synthesus Knowledge Cloud bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_BASE_URL = os.environ.get(
    "SYNTHESUS_KNOWLEDGE_CLOUD_URL",
    "https://zo.pub/syntech/synthesus-knowledge",
).rstrip("/")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_bytes(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return Path(parsed.path).read_bytes()
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Synthesus-Knowledge-Cloud-Sync/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def fetch_manifest(base_url: str, manifest_name: str) -> dict:
    raw = read_bytes(f"{base_url.rstrip('/')}/{manifest_name.lstrip('/')}")
    return json.loads(raw.decode("utf-8"))


def download_artifact(base_url: str, item: dict, dest_root: Path, force: bool = False) -> str:
    rel = item["path"].replace("\\", "/")
    dest = dest_root / rel
    expected_size = int(item["size"])
    expected_sha = item["sha256"]

    if not force and dest.exists() and dest.stat().st_size == expected_size and sha256_file(dest) == expected_sha:
        return f"skipped {rel}"

    dest.parent.mkdir(parents=True, exist_ok=True)
    data_url = f"{base_url.rstrip('/')}/{rel}"
    parsed = urlparse(data_url)

    fd, tmp_name = tempfile.mkstemp(prefix=dest.name + ".", dir=str(dest.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        if parsed.scheme == "file":
            shutil.copyfile(Path(parsed.path), tmp)
        else:
            request = urllib.request.Request(
                data_url,
                headers={"User-Agent": "Synthesus-Knowledge-Cloud-Sync/1.0"},
            )
            digest = hashlib.sha256()
            total = 0
            with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as fh:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
            if total != expected_size:
                raise ValueError(f"size mismatch for {rel}: expected {expected_size}, got {total}")
            if digest.hexdigest() != expected_sha:
                raise ValueError(f"sha256 mismatch for {rel}")

        if tmp.stat().st_size != expected_size:
            raise ValueError(f"size mismatch for {rel}: expected {expected_size}, got {tmp.stat().st_size}")
        if sha256_file(tmp) != expected_sha:
            raise ValueError(f"sha256 mismatch for {rel}")
        os.replace(tmp, dest)
        return f"downloaded {rel}"
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", default="./data", help="Destination cache root")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL or file:// artifact root")
    parser.add_argument("--manifest-name", default="manifest.json")
    parser.add_argument("--force", action="store_true", help="Redownload even when local files verify")
    args = parser.parse_args()

    dest = Path(args.dest).resolve()
    manifest = fetch_manifest(args.base_url, args.manifest_name)
    artifacts = manifest.get("artifacts", [])
    if not artifacts:
        raise SystemExit("manifest has no artifacts")

    for item in artifacts:
        print(download_artifact(args.base_url, item, dest, force=args.force))

    manifest_dest = dest / args.manifest_name
    manifest_dest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {manifest_dest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
