"""Profile-aware Knowledge Cloud rebuild orchestrator.

The orchestrator's job is to take a profile (e.g. `public-base`), validate the
source planes, plan a deterministic build, and either execute the heavy
pipeline or emit the plan as a dry-run. Provenance is always captured so the
resulting `artifacts/manifest.json` is auditable.

The actual heavy lifting (FAISS index, KNDatabase, embedder fit) is delegated
to `pipelines/build/run_population.py` — this module wraps it with profile
arguments, source validation, and manifest stamping.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .manifest import (
    DEFAULT_SOURCE_ROOTS,
    build_manifest,
    validate_runtime_bundle_semantics,
    verify_source_manifest,
    write_manifest,
)
from .profiles import load_profile
from .provenance import capture_provenance, stamp_manifest
from .source_planes import validate_source_planes


@dataclass
class BuildPlan:
    profile_name: str
    profile_path: Path
    repo_root: Path
    artifact_root: Path
    sample_jeopardy: int | None
    sample_conceptnet: int | None
    embed_dim: int
    outputs: dict[str, bool]
    sources: list[str]
    artifact_roots: list[str] = field(default_factory=lambda: ["."])

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "profile_path": str(self.profile_path),
            "repo_root": str(self.repo_root),
            "artifact_root": str(self.artifact_root),
            "sample_jeopardy": self.sample_jeopardy,
            "sample_conceptnet": self.sample_conceptnet,
            "embed_dim": self.embed_dim,
            "outputs": self.outputs,
            "sources": self.sources,
        }


def _derive_sample_sizes(profile: dict[str, Any]) -> tuple[int | None, int | None]:
    limits = profile.get("limits", {}) or {}
    total = limits.get("max_entries")
    fractions = limits.get("max_source_fraction", {}) or {}
    if not total:
        return None, None
    j = int(total * float(fractions.get("jeopardy", 0.0))) if "jeopardy" in fractions else None
    c = int(total * float(fractions.get("conceptnet", 0.0))) if "conceptnet" in fractions else None
    return j, c


def plan_build(
    profile_path: str | Path,
    *,
    repo_root: str | Path = ".",
    artifact_root: str | Path | None = None,
) -> BuildPlan:
    profile = load_profile(profile_path)
    sample_j, sample_c = _derive_sample_sizes(profile)
    repo = Path(repo_root).resolve()
    artifacts = Path(artifact_root).resolve() if artifact_root else (repo / "artifacts")
    return BuildPlan(
        profile_name=profile.get("name", Path(profile_path).stem),
        profile_path=Path(profile_path).resolve(),
        repo_root=repo,
        artifact_root=artifacts,
        sample_jeopardy=sample_j,
        sample_conceptnet=sample_c,
        embed_dim=int((profile.get("embedding", {}) or {}).get("dim", 128)),
        outputs=dict(profile.get("outputs", {}) or {}),
        sources=list(profile.get("sources", []) or []),
    )


@dataclass
class BuildReport:
    plan: BuildPlan
    executed: bool
    exit_code: int | None
    manifest_path: Path | None
    artifact_count: int
    provenance: dict[str, Any] | None
    stdout_tail: str | None
    stderr_tail: str | None

    @property
    def ok(self) -> bool:
        if not self.executed:
            return True
        return self.exit_code == 0


def _stamp_artifact_manifest(plan: BuildPlan) -> tuple[Path, dict[str, Any]]:
    manifest = build_manifest(
        plan.artifact_root,
        ["."],
        kind="synthesus-knowledge-artifacts",
    )
    provenance = capture_provenance(
        plan.repo_root,
        artifact_root=plan.artifact_root,
        profile=plan.profile_name,
        generated_by="synthesus-kc build",
        extra={
            "embed_dim": plan.embed_dim,
            "sample_jeopardy": plan.sample_jeopardy,
            "sample_conceptnet": plan.sample_conceptnet,
            "outputs": plan.outputs,
            "sources": plan.sources,
        },
    )
    manifest = stamp_manifest(manifest, provenance)
    path = plan.artifact_root / "manifest.json"
    write_manifest(manifest, path)
    return path, manifest


def _require_runtime_bundle_semantics(plan: BuildPlan, *, require_profile_dim: bool = True) -> None:
    expected_embed_dim = plan.embed_dim if require_profile_dim else None
    validation = validate_runtime_bundle_semantics(plan.artifact_root, expected_embed_dim=expected_embed_dim)
    if not validation.ok:
        failures = "; ".join(validation.failures)
        raise RuntimeError(f"runtime bundle semantic validation failed: {failures}")


def _require_source_manifest_current(repo_root: Path) -> None:
    validation = verify_source_manifest(repo_root)
    if not validation.ok:
        failures = "; ".join(validation.failures)
        raise RuntimeError(f"source manifest validation failed: {failures}")


def stamp_existing_manifest(
    *,
    repo_root: str | Path = ".",
    artifact_root: str | Path | None = None,
    profile_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repo_root).resolve()
    artifacts = Path(artifact_root).resolve() if artifact_root else (repo / "artifacts")
    if profile_path:
        plan = plan_build(profile_path, repo_root=repo, artifact_root=artifacts)
    else:
        plan = BuildPlan(
            profile_name="(adhoc)",
            profile_path=Path("(adhoc)"),
            repo_root=repo,
            artifact_root=artifacts,
            sample_jeopardy=None,
            sample_conceptnet=None,
            embed_dim=128,
            outputs={},
            sources=[],
        )

    _require_source_manifest_current(repo)
    _require_runtime_bundle_semantics(plan, require_profile_dim=profile_path is not None)

    # Preserve original bundle generated_at if a previous manifest exists.
    existing_generated_at: str | None = None
    existing_path = artifacts / "manifest.json"
    if existing_path.exists():
        try:
            existing = json.loads(existing_path.read_text(encoding="utf-8"))
            existing_generated_at = existing.get("generated_at")
        except Exception:
            existing_generated_at = None

    path, manifest = _stamp_artifact_manifest(plan)
    if existing_generated_at:
        manifest["generated_at"] = existing_generated_at
        write_manifest(manifest, path)
    return path, manifest


def _run_pipeline(plan: BuildPlan) -> tuple[int, str, str]:
    cmd = [
        sys.executable,
        "-m",
        "pipelines.build.run_population",
        "--data-dir",
        str(plan.artifact_root),
        "--dim",
        str(plan.embed_dim),
    ]
    if plan.sample_jeopardy is not None:
        cmd += ["--sample-jeopardy", str(plan.sample_jeopardy)]
    if plan.sample_conceptnet is not None:
        cmd += ["--sample-conceptnet", str(plan.sample_conceptnet)]
    proc = subprocess.run(
        cmd,
        cwd=str(plan.repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_build(
    profile_path: str | Path,
    *,
    repo_root: str | Path = ".",
    artifact_root: str | Path | None = None,
    execute: bool = False,
) -> BuildReport:
    plan = plan_build(profile_path, repo_root=repo_root, artifact_root=artifact_root)
    validation = validate_source_planes(plan.repo_root)
    if not validation.ok:
        return BuildReport(
            plan=plan,
            executed=False,
            exit_code=None,
            manifest_path=None,
            artifact_count=0,
            provenance=None,
            stdout_tail=None,
            stderr_tail="; ".join(validation.errors),
        )
    try:
        _require_source_manifest_current(plan.repo_root)
    except RuntimeError as exc:
        return BuildReport(
            plan=plan,
            executed=False,
            exit_code=None,
            manifest_path=None,
            artifact_count=0,
            provenance=None,
            stdout_tail=None,
            stderr_tail=str(exc),
        )

    if not execute:
        return BuildReport(
            plan=plan,
            executed=False,
            exit_code=None,
            manifest_path=None,
            artifact_count=0,
            provenance=None,
            stdout_tail=json.dumps(plan.to_dict(), indent=2, ensure_ascii=False),
            stderr_tail=None,
        )

    exit_code, stdout, stderr = _run_pipeline(plan)
    if exit_code != 0:
        return BuildReport(
            plan=plan,
            executed=True,
            exit_code=exit_code,
            manifest_path=None,
            artifact_count=0,
            provenance=None,
            stdout_tail=stdout[-2000:] if stdout else None,
            stderr_tail=stderr[-2000:] if stderr else None,
        )

    try:
        _require_runtime_bundle_semantics(plan)
    except RuntimeError as exc:
        return BuildReport(
            plan=plan,
            executed=True,
            exit_code=1,
            manifest_path=None,
            artifact_count=0,
            provenance=None,
            stdout_tail=stdout[-2000:] if stdout else None,
            stderr_tail=str(exc),
        )

    manifest_path, manifest = _stamp_artifact_manifest(plan)
    return BuildReport(
        plan=plan,
        executed=True,
        exit_code=exit_code,
        manifest_path=manifest_path,
        artifact_count=len(manifest.get("artifacts", [])),
        provenance=manifest.get("build"),
        stdout_tail=stdout[-2000:] if stdout else None,
        stderr_tail=stderr[-2000:] if stderr else None,
    )
