"""Build provenance capture for Knowledge Cloud manifests.

The provenance block makes manifests auditable: any consumer can read it and
know exactly which package version, profile, embedder fingerprint, dataset
versions, and host produced a bundle.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__ as _PACKAGE_VERSION


def _read_version() -> str:
    # Prefer the in-package constant; fall back to VERSION file at repo root.
    if _PACKAGE_VERSION:
        return _PACKAGE_VERSION
    version_path = Path(__file__).resolve().parents[1] / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return "0.0.0"


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        value = out.stdout.strip()
        return value or None
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None


def git_info(repo_root: str | Path) -> dict[str, str | None]:
    root = Path(repo_root).resolve()
    return {
        "commit": _git(["rev-parse", "HEAD"], root),
        "short_commit": _git(["rev-parse", "--short", "HEAD"], root),
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], root),
        "dirty": _git(["status", "--porcelain"], root) not in (None, ""),
    }


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def embedder_fingerprint(artifact_root: str | Path, *, rel: str = "models/swarm_embedder.pkl") -> dict[str, Any] | None:
    root = Path(artifact_root).resolve()
    path = root / rel
    digest = _sha256(path)
    if digest is None:
        return None
    return {
        "path": rel,
        "sha256": digest,
        "size": path.stat().st_size,
    }


def source_manifest_fingerprint(
    repo_root: str | Path,
    *,
    rel: str = "manifests/source_manifest.json",
) -> dict[str, Any] | None:
    root = Path(repo_root).resolve()
    path = root / rel
    digest = _sha256(path)
    if digest is None:
        return None
    fingerprint: dict[str, Any] = {
        "path": rel,
        "sha256": digest,
        "size": path.stat().st_size,
    }
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fingerprint
    artifacts = manifest.get("artifacts")
    fingerprint.update(
        {
            "kind": manifest.get("kind"),
            "generated_at": manifest.get("generated_at"),
            "roots": manifest.get("roots"),
            "artifact_count": len(artifacts) if isinstance(artifacts, list) else 0,
        }
    )
    return fingerprint


def dataset_versions(repo_root: str | Path) -> dict[str, Any]:
    """Read declared dataset versions from sources/*.yaml without a YAML hard dep."""
    sources_dir = Path(repo_root).resolve() / "sources"
    if not sources_dir.exists():
        return {}
    versions: dict[str, Any] = {}
    for path in sorted(sources_dir.glob("*.yaml")):
        name = path.stem
        if name == "datasets":
            continue
        info: dict[str, Any] = {}
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in ("version", "id", "name", "source_type", "license"):
                info[key] = value
        if info:
            versions[name] = info
    return versions


@dataclass(frozen=True)
class Provenance:
    package_version: str
    generated_by: str
    profile: str | None
    git_commit: str | None
    git_short_commit: str | None
    git_branch: str | None
    git_dirty: bool
    python_version: str
    platform: str
    host: str | None
    embedder: dict[str, Any] | None
    source_manifest: dict[str, Any] | None
    datasets: dict[str, Any]
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Drop trivially empty optional keys for compactness.
        if not data["extra"]:
            data.pop("extra")
        return data


def capture_provenance(
    repo_root: str | Path,
    *,
    artifact_root: str | Path | None = None,
    profile: str | None = None,
    generated_by: str = "synthesus-knowledge-cloud",
    extra: dict[str, Any] | None = None,
) -> Provenance:
    repo = Path(repo_root).resolve()
    artifacts = Path(artifact_root).resolve() if artifact_root else (repo / "artifacts")
    g = git_info(repo)
    return Provenance(
        package_version=_read_version(),
        generated_by=generated_by,
        profile=profile,
        git_commit=g.get("commit"),
        git_short_commit=g.get("short_commit"),
        git_branch=g.get("branch"),
        git_dirty=bool(g.get("dirty")),
        python_version=sys.version.split()[0],
        platform=platform.platform(aliased=True, terse=True),
        host=os.environ.get("HOSTNAME") or platform.node() or None,
        embedder=embedder_fingerprint(artifacts),
        source_manifest=source_manifest_fingerprint(repo),
        datasets=dataset_versions(repo),
        extra=extra or {},
    )


def stamp_manifest(manifest: dict[str, Any], provenance: Provenance, *, now: datetime | None = None) -> dict[str, Any]:
    manifest = dict(manifest)
    manifest["build"] = provenance.to_dict()
    manifest["manifest_revised_at"] = (now or datetime.now(timezone.utc)).isoformat()
    return manifest
