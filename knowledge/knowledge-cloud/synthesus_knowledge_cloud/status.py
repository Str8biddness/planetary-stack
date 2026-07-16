"""Local vs remote bundle drift inspection.

`status` answers "what would change if I synced right now?" without
downloading or modifying anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .manifest import sha256_file
from .mirrors import resolve_mirrors
from .sync import fetch_manifest


@dataclass
class ArtifactDrift:
    path: str
    state: str  # missing | size_mismatch | sha_mismatch | ok | extra
    expected_size: int | None = None
    actual_size: int | None = None
    expected_sha: str | None = None
    actual_sha: str | None = None


@dataclass
class StatusReport:
    local_root: Path
    mirrors: list[str]
    remote_mirror: str | None
    remote_manifest_present: bool
    remote_generated_at: str | None
    remote_revised_at: str | None
    artifacts: list[ArtifactDrift]
    extras: list[str]

    @property
    def drift(self) -> list[ArtifactDrift]:
        return [a for a in self.artifacts if a.state != "ok"]

    def summary(self) -> str:
        counts: dict[str, int] = {}
        for a in self.artifacts:
            counts[a.state] = counts.get(a.state, 0) + 1
        parts = [f"{k}={v}" for k, v in sorted(counts.items())]
        return (
            f"local={self.local_root} mirrors={','.join(self.mirrors)} "
            f"remote_mirror={self.remote_mirror or '(none)'} "
            f"artifacts={len(self.artifacts)} extras={len(self.extras)} "
            f"states[{','.join(parts)}]"
        )


def _index_remote_paths(manifest: dict[str, Any]) -> set[str]:
    out = set()
    for item in manifest.get("artifacts", []):
        out.add(item["path"].replace("\\", "/"))
    return out


def status_report(
    local_root: str | Path,
    *,
    base_url: str | None = None,
    mirrors: list[str] | None = None,
    manifest_name: str = "manifest.json",
    deep: bool = True,
) -> StatusReport:
    root = Path(local_root).resolve()
    effective = mirrors if mirrors is not None else resolve_mirrors(base_url)

    remote_manifest: dict[str, Any] | None
    remote_mirror: str | None
    try:
        remote_manifest, remote_mirror = fetch_manifest(mirrors=effective, manifest_name=manifest_name)
    except Exception:
        remote_manifest = None
        remote_mirror = None

    drift: list[ArtifactDrift] = []
    if remote_manifest:
        for item in remote_manifest.get("artifacts", []):
            rel = item["path"].replace("\\", "/")
            local = root / rel
            expected_size = int(item["size"])
            expected_sha = item["sha256"]
            if not local.exists():
                drift.append(ArtifactDrift(path=rel, state="missing", expected_size=expected_size, expected_sha=expected_sha))
                continue
            actual_size = local.stat().st_size
            if actual_size != expected_size:
                drift.append(
                    ArtifactDrift(
                        path=rel,
                        state="size_mismatch",
                        expected_size=expected_size,
                        actual_size=actual_size,
                        expected_sha=expected_sha,
                    )
                )
                continue
            if deep:
                actual_sha = sha256_file(local)
                if actual_sha != expected_sha:
                    drift.append(
                        ArtifactDrift(
                            path=rel,
                            state="sha_mismatch",
                            expected_size=expected_size,
                            actual_size=actual_size,
                            expected_sha=expected_sha,
                            actual_sha=actual_sha,
                        )
                    )
                    continue
            drift.append(
                ArtifactDrift(
                    path=rel,
                    state="ok",
                    expected_size=expected_size,
                    actual_size=actual_size,
                    expected_sha=expected_sha,
                )
            )

    remote_paths = _index_remote_paths(remote_manifest) if remote_manifest else set()
    extras: list[str] = []
    if root.exists():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.name == manifest_name and path.parent == root:
                continue
            rel = path.relative_to(root).as_posix()
            if rel not in remote_paths:
                extras.append(rel)

    return StatusReport(
        local_root=root,
        mirrors=list(effective),
        remote_mirror=remote_mirror,
        remote_manifest_present=remote_manifest is not None,
        remote_generated_at=(remote_manifest or {}).get("generated_at"),
        remote_revised_at=(remote_manifest or {}).get("manifest_revised_at"),
        artifacts=drift,
        extras=extras,
    )
