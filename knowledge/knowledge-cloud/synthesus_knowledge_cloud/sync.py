"""Mirror-aware, parallel, resumable Knowledge Cloud bundle sync.

Design goals:
- Tolerate transient network failures with bounded retries and exponential backoff.
- Fail over across multiple mirrors before giving up on an artifact.
- Resume partial downloads using HTTP Range requests so the 770 MB FAISS index
  does not have to start over after a flap.
- Verify size and SHA-256 before swapping a temp file into place.
- Stream in parallel for many small artifacts without exceeding a worker budget.
- Treat local file:// mirrors as first-class so the same code path runs in tests.
"""

from __future__ import annotations

import concurrent.futures as _cf
import hashlib
import json
import logging
import os
import shutil
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .manifest import sha256_file
from .mirrors import DEFAULT_MIRRORS, DEFAULT_PRIMARY, resolve_mirrors

DEFAULT_BASE_URL = DEFAULT_PRIMARY
DEFAULT_USER_AGENT = "Synthesus-Knowledge-Cloud-Sync/2.0"
DEFAULT_WORKERS = 4
DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT = 120
CHUNK_SIZE = 1024 * 1024
LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArtifactResult:
    path: str
    status: str  # "skipped" | "downloaded" | "resumed"
    bytes: int
    mirror: str | None
    attempts: int = 1


@dataclass
class SyncReport:
    mirrors: list[str]
    manifest_mirror: str | None = None
    results: list[ArtifactResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_messages(self) -> list[str]:
        msgs = [f"{r.status} {r.path}" for r in self.results]
        for failure in self.failures:
            msgs.append(f"FAIL {failure}")
        return msgs


def _read_file_url(url: str) -> bytes:
    parsed = urlparse(url)
    return Path(parsed.path).read_bytes()


def _http_get_bytes(url: str, *, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _read_bytes_with_failover(rel_path: str, mirrors: list[str], *, timeout: int = DEFAULT_TIMEOUT) -> tuple[bytes, str]:
    last_err: Exception | None = None
    for mirror in mirrors:
        url = f"{mirror.rstrip('/')}/{rel_path.lstrip('/')}"
        try:
            parsed = urlparse(url)
            if parsed.scheme == "file":
                if not Path(parsed.path).exists():
                    raise FileNotFoundError(parsed.path)
                return _read_file_url(url), mirror
            return _http_get_bytes(url, timeout=timeout), mirror
        except (urllib.error.URLError, FileNotFoundError, OSError, ValueError) as exc:
            LOG.warning("manifest fetch failed at %s: %s", mirror, exc)
            last_err = exc
            continue
    raise RuntimeError(f"all mirrors failed for {rel_path}: {last_err}")


def fetch_manifest(
    base_url: str | None = None,
    *,
    mirrors: list[str] | None = None,
    manifest_name: str = "manifest.json",
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[dict, str]:
    """Fetch the manifest, returning ``(manifest, mirror_url)``."""
    effective = mirrors if mirrors is not None else resolve_mirrors(base_url)
    raw, mirror = _read_bytes_with_failover(manifest_name, effective, timeout=timeout)
    return json.loads(raw.decode("utf-8")), mirror


def _open_remote(url: str, *, start: int = 0, timeout: int = DEFAULT_TIMEOUT):
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if start > 0:
        headers["Range"] = f"bytes={start}-"
    request = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(request, timeout=timeout)


def _stream_to_file(
    url: str,
    dest_tmp: Path,
    *,
    resume: bool,
    expected_size: int,
    expected_sha: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[str, int]:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        src = Path(parsed.path)
        shutil.copyfile(src, dest_tmp)
        if dest_tmp.stat().st_size != expected_size:
            raise ValueError(f"size mismatch: expected {expected_size}, got {dest_tmp.stat().st_size}")
        digest = sha256_file(dest_tmp)
        if digest != expected_sha:
            raise ValueError("sha256 mismatch")
        return "downloaded", dest_tmp.stat().st_size

    start = dest_tmp.stat().st_size if (resume and dest_tmp.exists()) else 0
    if start >= expected_size:
        start = 0
    if start > 0:
        digest = hashlib.sha256()
        with dest_tmp.open("rb") as fh:
            while True:
                buf = fh.read(CHUNK_SIZE)
                if not buf:
                    break
                digest.update(buf)
        mode = "ab"
        status = "resumed"
    else:
        digest = hashlib.sha256()
        mode = "wb"
        status = "downloaded"
        if dest_tmp.exists():
            dest_tmp.unlink()

    response = _open_remote(url, start=start, timeout=timeout)
    try:
        # If the server doesn't honor Range, response status is 200 with full body — discard our partial.
        if start > 0 and response.status == 200:
            response.close()
            if dest_tmp.exists():
                dest_tmp.unlink()
            return _stream_to_file(
                url,
                dest_tmp,
                resume=False,
                expected_size=expected_size,
                expected_sha=expected_sha,
                timeout=timeout,
            )
        with dest_tmp.open(mode) as fh:
            total = start
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                fh.write(chunk)
                digest.update(chunk)
                total += len(chunk)
    finally:
        response.close()

    if total != expected_size:
        raise ValueError(f"size mismatch: expected {expected_size}, got {total}")
    if digest.hexdigest() != expected_sha:
        raise ValueError("sha256 mismatch")
    return status, total


def _backoff_seconds(attempt: int) -> float:
    return min(30.0, 1.5 * (2 ** (attempt - 1)))


def _download_one(
    item: dict,
    dest_root: Path,
    mirrors: list[str],
    *,
    force: bool,
    retries: int,
    timeout: int,
) -> ArtifactResult:
    rel = item["path"].replace("\\", "/")
    expected_size = int(item["size"])
    expected_sha = item["sha256"]
    dest = dest_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)

    if not force and dest.exists() and dest.stat().st_size == expected_size and sha256_file(dest) == expected_sha:
        return ArtifactResult(path=rel, status="skipped", bytes=expected_size, mirror=None, attempts=0)

    tmp = dest.parent / f".{dest.name}.part"
    last_error: Exception | None = None
    attempts = 0
    for mirror in mirrors:
        url = f"{mirror.rstrip('/')}/{rel}"
        for attempt in range(1, retries + 1):
            attempts += 1
            try:
                status, total = _stream_to_file(
                    url,
                    tmp,
                    resume=True,
                    expected_size=expected_size,
                    expected_sha=expected_sha,
                    timeout=timeout,
                )
                os.replace(tmp, dest)
                return ArtifactResult(path=rel, status=status, bytes=total, mirror=mirror, attempts=attempts)
            except (urllib.error.URLError, FileNotFoundError, OSError, ValueError, TimeoutError) as exc:
                last_error = exc
                LOG.warning("download failed (%s attempt %s): %s", rel, attempt, exc)
                # On hash/size mismatch the partial file is poisoned: drop it.
                if isinstance(exc, ValueError) and tmp.exists():
                    tmp.unlink(missing_ok=True)
                if attempt < retries:
                    time.sleep(_backoff_seconds(attempt))
        # Mirror exhausted; try the next one without keeping partial.
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    if tmp.exists():
        tmp.unlink(missing_ok=True)
    raise RuntimeError(f"{rel}: all mirrors exhausted ({last_error})")


def sync_bundle(
    dest: str | Path = "./data",
    *,
    base_url: str | None = None,
    mirrors: list[str] | None = None,
    manifest_name: str = "manifest.json",
    force: bool = False,
    workers: int = DEFAULT_WORKERS,
    retries: int = DEFAULT_RETRIES,
    timeout: int = DEFAULT_TIMEOUT,
) -> SyncReport:
    effective = mirrors if mirrors is not None else resolve_mirrors(base_url)
    report = SyncReport(mirrors=list(effective))
    dest_root = Path(dest).resolve()
    dest_root.mkdir(parents=True, exist_ok=True)

    try:
        manifest, manifest_mirror = fetch_manifest(
            mirrors=effective,
            manifest_name=manifest_name,
            timeout=timeout,
        )
    except Exception as exc:
        report.failures.append(f"manifest: {exc}")
        return report
    report.manifest_mirror = manifest_mirror

    artifacts = manifest.get("artifacts", [])
    if not artifacts:
        report.failures.append("manifest has no artifacts")
        return report

    lock = threading.Lock()

    def task(item: dict) -> None:
        try:
            result = _download_one(
                item,
                dest_root,
                effective,
                force=force,
                retries=retries,
                timeout=timeout,
            )
            with lock:
                report.results.append(result)
        except Exception as exc:  # pragma: no cover - exercised via failure tests
            with lock:
                report.failures.append(f"{item.get('path', '?')}: {exc}")

    workers = max(1, int(workers))
    if workers == 1 or len(artifacts) == 1:
        for item in artifacts:
            task(item)
    else:
        with _cf.ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(task, artifacts))

    if report.ok:
        manifest_dest = dest_root / manifest_name
        manifest_dest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report.results.append(ArtifactResult(path=manifest_name, status="wrote-manifest", bytes=0, mirror=manifest_mirror, attempts=0))
    return report
