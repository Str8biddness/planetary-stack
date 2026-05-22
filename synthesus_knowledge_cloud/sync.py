"""Download and verify Synthesus Knowledge Cloud bundles."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .manifest import sha256_file

DEFAULT_BASE_URL = os.environ.get(
    "SYNTHESUS_KNOWLEDGE_CLOUD_URL",
    "https://zo.pub/syntech/synthesus-knowledge",
).rstrip("/")


def read_bytes(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return Path(parsed.path).read_bytes()
    request = urllib.request.Request(url, headers={"User-Agent": "Synthesus-Knowledge-Cloud-Sync/1.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def fetch_manifest(base_url: str = DEFAULT_BASE_URL, manifest_name: str = "manifest.json") -> dict:
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
            request = urllib.request.Request(data_url, headers={"User-Agent": "Synthesus-Knowledge-Cloud-Sync/1.1"})
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


def sync_bundle(
    dest: str | Path = "./data",
    *,
    base_url: str = DEFAULT_BASE_URL,
    manifest_name: str = "manifest.json",
    force: bool = False,
) -> list[str]:
    dest_root = Path(dest).resolve()
    manifest = fetch_manifest(base_url, manifest_name)
    artifacts = manifest.get("artifacts", [])
    if not artifacts:
        raise ValueError("manifest has no artifacts")
    messages = [download_artifact(base_url, item, dest_root, force=force) for item in artifacts]
    manifest_dest = dest_root / manifest_name
    manifest_dest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    messages.append(f"wrote {manifest_dest}")
    return messages
