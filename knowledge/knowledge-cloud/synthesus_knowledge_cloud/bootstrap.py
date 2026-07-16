"""One-shot bootstrap for local Synthesus installs.

`bootstrap` resolves the data root Synthesus expects, syncs the runtime bundle
into it, verifies the manifest, and writes a small `.bootstrap.json` marker
recording the mirror, manifest revision, and package version used. This is the
target UX for "I just installed Synthesus locally and want the cloud now."
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .manifest import validate_manifest
from .mirrors import resolve_mirrors
from .sync import SyncReport, sync_bundle


DEFAULT_SYNTHESUS_CACHE = Path.home() / ".synthesus" / "data"


def resolve_target(target: str | Path | None = None) -> Path:
    """Resolve the target data root.

    Precedence: explicit ``target`` > ``SYNTHESUS_DATA_DIR`` env > XDG default.
    """
    if target:
        return Path(target).expanduser().resolve()
    env_target = os.environ.get("SYNTHESUS_DATA_DIR")
    if env_target:
        return Path(env_target).expanduser().resolve()
    return DEFAULT_SYNTHESUS_CACHE


@dataclass
class BootstrapReport:
    target: Path
    mirrors: list[str]
    sync: SyncReport
    verified: bool
    marker_path: Path

    @property
    def ok(self) -> bool:
        return self.sync.ok and self.verified


def write_marker(target: Path, *, mirrors: list[str], manifest_mirror: str | None) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    marker_path = target / ".bootstrap.json"
    payload: dict[str, Any] = {
        "package_version": __version__,
        "mirrors": mirrors,
        "manifest_mirror": manifest_mirror,
        "bootstrapped_at": datetime.now(timezone.utc).isoformat(),
    }
    marker_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return marker_path


def bootstrap(
    target: str | Path | None = None,
    *,
    base_url: str | None = None,
    mirrors: list[str] | None = None,
    manifest_name: str = "manifest.json",
    workers: int = 4,
    force: bool = False,
) -> BootstrapReport:
    effective = mirrors if mirrors is not None else resolve_mirrors(base_url)
    resolved_target = resolve_target(target)
    resolved_target.mkdir(parents=True, exist_ok=True)

    sync_report = sync_bundle(
        resolved_target,
        mirrors=effective,
        manifest_name=manifest_name,
        force=force,
        workers=workers,
    )

    verified = False
    if sync_report.ok:
        try:
            validation = validate_manifest(resolved_target, manifest_name)
            verified = validation.ok
        except Exception:
            verified = False

    marker = write_marker(
        resolved_target,
        mirrors=effective,
        manifest_mirror=sync_report.manifest_mirror,
    )

    return BootstrapReport(
        target=resolved_target,
        mirrors=list(effective),
        sync=sync_report,
        verified=verified,
        marker_path=marker,
    )
