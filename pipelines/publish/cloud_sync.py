"""Cloud-backed artifact sync for the Synthesus knowledge layer.

The repo treats the local `data/` tree as a cache. A remote HTTP store can
publish a `manifest.json` plus the generated knowledge artifacts, and the app
can bootstrap missing files automatically when it starts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

DEFAULT_CLOUD_URL = "https://zo.pub/syntech/synthesus-knowledge"
DEFAULT_MANIFEST_NAME = "manifest.json"
DEFAULT_SYNC_MODE = "auto"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Synthesus Cloud Sync)"


@dataclass(frozen=True)
class CloudArtifact:
    """Represents a synchronizable artifact in the cloud.

    Attributes:
        relative_path: The path of the artifact relative to the root directory.
        required: Whether this artifact is mandatory for the system to function.
            Defaults to True.
    """
    relative_path: str
    required: bool = True


DEFAULT_KNOWLEDGE_ARTIFACTS: tuple[CloudArtifact, ...] = (
    CloudArtifact("faiss.index"),
    CloudArtifact("faiss_metadata.json"),
    CloudArtifact("models/swarm_embedder.pkl", required=False),
    CloudArtifact("knowledge_cloud/world_lore.json"),
    CloudArtifact("knowledge_cloud/evolution.json", required=False),
    CloudArtifact("knowledge_cloud/transitions.json", required=False),
    CloudArtifact("knowledge_cloud/learned_transitions.json", required=False),
    CloudArtifact("knowledge_cloud/chaining_patterns.json", required=False),
    CloudArtifact("knowledge.kndb", required=False),
    CloudArtifact("knowledge.kndb.meta.db", required=False),
    CloudArtifact("knowledge.meta.db", required=False),
)

_BOOTSTRAP_CACHE: dict[tuple[str, str, str, str], dict] = {}


def _http_request(url: str) -> urllib.request.Request:
    """Creates a decorated HTTP request object.

    Args:
        url: The destination URL.

    Returns:
        A Request object configured with standard headers and User-Agent.
    """
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, */*;q=0.8",
            "User-Agent": DEFAULT_USER_AGENT,
        },
    )


def bootstrap_knowledge_cache(
    local_root: str | Path,
    base_url: str | None = None,
    mode: str | None = None,
    manifest_name: str = DEFAULT_MANIFEST_NAME,
) -> dict:
    """Synchronizes knowledge artifacts into a local cache directory.

    This function serves as the primary entry point for ensuring the local
    environment has the necessary knowledge files. It uses an internal cache
    to avoid redundant sync operations within the same process.

    Args:
        local_root: Path to the local directory where artifacts should be stored.
        base_url: The remote base URL for artifacts. If None, uses the system default.
        mode: Sync mode ('auto', 'on', 'off'). If None, uses the system default.
        manifest_name: Name of the manifest file on the remote server.

    Returns:
        A report dictionary detailing the results of the synchronization.
    """
    root = str(Path(local_root).resolve())
    resolved_base = (base_url or default_cloud_url()).strip()
    resolved_mode = (mode or default_sync_mode()).strip().lower()
    cache_key = (root, resolved_base, resolved_mode, manifest_name)
    cached = _BOOTSTRAP_CACHE.get(cache_key)
    if cached is not None:
        return cached

    report = sync_artifacts(
        local_root=root,
        artifacts=DEFAULT_KNOWLEDGE_ARTIFACTS,
        base_url=resolved_base,
        manifest_name=manifest_name,
        mode=resolved_mode,
    )
    _BOOTSTRAP_CACHE[cache_key] = report
    return report


def default_cloud_url() -> str:
    """Retrieves the default cloud URL for knowledge artifacts.

    Checks the 'SYNTHESUS_KNOWLEDGE_CLOUD_URL' environment variable before
    falling back to the hardcoded DEFAULT_CLOUD_URL.

    Returns:
        The resolved base URL string.
    """
    return os.environ.get("SYNTHESUS_KNOWLEDGE_CLOUD_URL", DEFAULT_CLOUD_URL).strip()


def default_sync_mode() -> str:
    """Retrieves the default synchronization mode.

    Checks the 'SYNTHESUS_KNOWLEDGE_SYNC_MODE' environment variable before
    falling back to the hardcoded DEFAULT_SYNC_MODE.

    Returns:
        The resolved sync mode string (e.g., 'auto', 'on', 'off').
    """
    return os.environ.get("SYNTHESUS_KNOWLEDGE_SYNC_MODE", DEFAULT_SYNC_MODE).strip().lower()


def _sha256_file(path: Path) -> str:
    """Computes the SHA-256 hash of a file.

    Args:
        path: Path to the file to hash.

    Returns:
        The hex-encoded SHA-256 digest of the file content.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json_url(url: str, timeout: int = 30) -> dict:
    """Fetches and parses a JSON object from a URL.

    Args:
        url: The URL to fetch.
        timeout: Network timeout in seconds.

    Returns:
        The parsed JSON content as a dictionary.
    """
    request = _http_request(url)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def _download_file(url: str, dest: Path, expected_sha256: str | None = None, expected_size: int | None = None) -> None:
    """Downloads a remote file to a local destination with optional verification.

    The file is downloaded to a temporary location first and moved to the final
    destination only after successful verification of size and hash.

    Args:
        url: The remote URL of the file.
        dest: The local Path where the file should be saved.
        expected_sha256: Optional SHA-256 hash for integrity verification.
        expected_size: Optional file size in bytes for verification.

    Raises:
        ValueError: If size or hash verification fails.
        Exception: For network or filesystem errors.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=dest.name + ".", dir=str(dest.parent))
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)

    digest = hashlib.sha256()
    total = 0

    try:
        with urllib.request.urlopen(_http_request(url), timeout=120) as response, open(tmp_path, "wb") as fh:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                digest.update(chunk)
                total += len(chunk)

        if expected_size is not None and total != expected_size:
            raise ValueError(f"size mismatch for {url}: expected {expected_size}, got {total}")
        if expected_sha256 is not None and digest.hexdigest() != expected_sha256:
            raise ValueError(f"sha256 mismatch for {url}")

        os.replace(tmp_path, dest)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def build_manifest(root_dir: str | Path, artifacts: Sequence[str]) -> dict:
    """Constructs a manifest dictionary for a set of local files.

    Args:
        root_dir: The root directory for the artifacts.
        artifacts: A sequence of relative paths to include in the manifest.

    Returns:
        A dictionary containing manifest metadata and artifact details.
    """
    root = Path(root_dir)
    items = []
    for rel in artifacts:
        path = root / rel
        if not path.exists():
            continue
        items.append(
            {
                "path": rel.replace("\\", "/"),
                "size": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return {
        "version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": items,
    }


def write_manifest(root_dir: str | Path, artifacts: Sequence[str], manifest_name: str = DEFAULT_MANIFEST_NAME) -> Path:
    """Generates and writes a manifest file to disk.

    Args:
        root_dir: The root directory for artifacts and the manifest.
        artifacts: A sequence of relative paths to include.
        manifest_name: The filename for the generated manifest.

    Returns:
        The Path to the newly created manifest file.
    """
    root = Path(root_dir)
    manifest = build_manifest(root, artifacts)
    manifest_path = root / manifest_name
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest_path


def _manifest_index(manifest: dict) -> dict[str, dict]:
    """Indexes a manifest by artifact path for fast lookup.

    Args:
        manifest: The manifest dictionary.

    Returns:
        A mapping from relative artifact paths to their manifest entries.
    """
    items = manifest.get("artifacts", [])
    index: dict[str, dict] = {}
    for item in items:
        path = str(item.get("path", "")).replace("\\", "/")
        if path:
            index[path] = item
    return index


def sync_artifacts(
    local_root: str | Path,
    artifacts: Sequence[CloudArtifact],
    base_url: str | None = None,
    manifest_name: str = DEFAULT_MANIFEST_NAME,
    mode: str | None = None,
) -> dict:
    """Synchronizes local files with a remote cloud manifest.

    Checks local files against remote metadata (size/hash) and downloads
    any missing or outdated artifacts.

    Args:
        local_root: Local directory to sync.
        artifacts: Sequence of CloudArtifact objects defining what to sync.
        base_url: Remote base URL. Defaults to the system default.
        manifest_name: Name of the manifest file.
        mode: Sync mode ('auto', 'on', 'off').

    Returns:
        A synchronization report dictionary.
    """
    local_root = Path(local_root)
    if base_url is None:
        base_url = default_cloud_url().rstrip("/")
    else:
        base_url = base_url.rstrip("/")
    mode = (mode or default_sync_mode()).strip().lower()

    report = {
        "base_url": base_url,
        "mode": mode,
        "downloaded": [],
        "skipped": [],
        "missing_remote": [],
        "disabled": False,
    }

    if mode in {"off", "false", "0", "none"}:
        report["disabled"] = True
        return report

    if not base_url:
        report["disabled"] = True
        return report

    manifest_url = f"{base_url}/{manifest_name.lstrip('/')}"
    try:
        manifest = _read_json_url(manifest_url)
        remote = _manifest_index(manifest)
    except Exception as exc:
        logger.warning("Synthesus cloud sync: manifest unavailable at %s (%s)", manifest_url, exc)
        report["disabled"] = True
        return report

    for artifact in artifacts:
        rel = artifact.relative_path.replace("\\", "/")
        local_path = local_root / rel
        remote_item = remote.get(rel)
        expected_size = remote_item.get("size") if remote_item else None
        expected_sha = remote_item.get("sha256") if remote_item else None

        if local_path.exists() and expected_size is not None and local_path.stat().st_size == expected_size:
            report["skipped"].append(rel)
            continue

        if remote_item is None:
            if artifact.required:
                report["missing_remote"].append(rel)
            continue

        remote_url = f"{base_url}/{rel}"
        logger.info("Synthesus cloud sync: downloading %s", rel)
        _download_file(remote_url, local_path, expected_sha256=expected_sha, expected_size=expected_size)
        report["downloaded"].append(rel)

    return report


def _parse_artifacts(values: list[str]) -> list[CloudArtifact]:
    """Parses artifact strings from CLI arguments.

    Expected format: "path/to/file" or "path/to/file:optional".

    Args:
        values: List of artifact specification strings.

    Returns:
        A list of CloudArtifact objects.
    """
    artifacts: list[CloudArtifact] = []
    for value in values:
        if ":" in value:
            rel, flag = value.split(":", 1)
            artifacts.append(CloudArtifact(relative_path=rel, required=flag.lower() != "optional"))
        else:
            artifacts.append(CloudArtifact(relative_path=value))
    return artifacts


def main() -> int:
    """Main CLI entry point for the cloud sync tool.

    Returns:
        0 on success, non-zero on failure.
    """
    parser = argparse.ArgumentParser(description="Sync Synthesus knowledge artifacts from a cloud manifest")
    parser.add_argument("--root", default="./data", help="Local data root to sync into")
    parser.add_argument("--base-url", default="", help="Cloud base URL (defaults to SYNTHESUS_KNOWLEDGE_CLOUD_URL)")
    parser.add_argument("--mode", default="", help="Sync mode: auto, on, off")
    parser.add_argument("--manifest-name", default=DEFAULT_MANIFEST_NAME)
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="Relative artifact path to sync. Append ':optional' to make it non-required.",
    )
    parser.add_argument("--write-manifest", action="store_true", help="Write a local manifest instead of syncing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    artifacts = _parse_artifacts(args.artifact)
    if args.write_manifest:
        if not artifacts:
            raise SystemExit("--write-manifest requires at least one --artifact")
        manifest_path = write_manifest(args.root, [a.relative_path for a in artifacts], args.manifest_name)
        print(manifest_path)
        return 0

    report = sync_artifacts(args.root, artifacts, base_url=args.base_url or None, manifest_name=args.manifest_name, mode=args.mode or None)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
