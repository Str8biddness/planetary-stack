#!/usr/bin/env python3
"""Evaluate Synthesus 5 release readiness for consumer/commercial packaging."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "tools" / "results" / "synthesus5_release_gate_latest.json"
RC_TAG_PATTERN = re.compile(r"^(?:synthesus5-rc[1-9][0-9]*|v?\d+\.\d+\.\d+-rc\.?[1-9][0-9]*)$")


@dataclass(frozen=True)
class ReleaseCheck:
    id: str
    label: str
    status: str
    severity: str
    detail: str
    command: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LaunchTier:
    tier: str
    status: str
    rationale: str


def _run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def _tail(text: str, lines: int = 10) -> str:
    content = text.strip().splitlines()
    return "\n".join(content[-lines:])


def _extract_cold_start_summary(text: str) -> dict[str, Any]:
    for line in text.splitlines():
        if not line.startswith("cold_start_summary="):
            continue
        try:
            payload = json.loads(line.split("=", 1)[1])
        except json.JSONDecodeError:
            return {"parse_error": "invalid cold_start_summary JSON"}
        return payload if isinstance(payload, dict) else {"parse_error": "cold_start_summary was not an object"}
    return {}


def _path_check(path: str, label: str, severity: str = "critical") -> ReleaseCheck:
    target = ROOT / path
    if target.exists():
        return ReleaseCheck(
            id=f"path:{path}",
            label=label,
            status="pass",
            severity=severity,
            detail=f"Found {path}.",
        )
    return ReleaseCheck(
        id=f"path:{path}",
        label=label,
        status="fail",
        severity=severity,
        detail=f"Missing required release artifact: {path}.",
    )


def _command_check(
    check_id: str,
    label: str,
    command: list[str],
    *,
    timeout: int,
    severity: str = "critical",
) -> ReleaseCheck:
    command_text = " ".join(command)
    try:
        completed = _run(command, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return ReleaseCheck(
            id=check_id,
            label=label,
            status="fail",
            severity=severity,
            detail=f"Timed out after {timeout}s.\n{_tail(exc.stdout or '')}",
            command=command_text,
        )

    if completed.returncode == 0:
        return ReleaseCheck(
            id=check_id,
            label=label,
            status="pass",
            severity=severity,
            detail=_tail(completed.stdout) or "Command passed.",
            command=command_text,
        )
    return ReleaseCheck(
        id=check_id,
        label=label,
        status="fail",
        severity=severity,
        detail=_tail(completed.stdout) or f"Command exited {completed.returncode}.",
        command=command_text,
    )


def _clean_worktree_check() -> ReleaseCheck:
    command = ["git", "status", "--porcelain", "--untracked-files=all"]
    command_text = " ".join(command)
    try:
        completed = _run(command, timeout=30)
    except subprocess.TimeoutExpired as exc:
        return ReleaseCheck(
            id="git:clean-worktree",
            label="Clean release worktree",
            status="fail",
            severity="critical",
            detail=f"Timed out after 30s.\n{_tail(exc.stdout or '')}",
            command=command_text,
        )

    output = completed.stdout or ""
    if completed.returncode != 0:
        return ReleaseCheck(
            id="git:clean-worktree",
            label="Clean release worktree",
            status="fail",
            severity="critical",
            detail=_tail(output) or f"git status exited {completed.returncode}.",
            command=command_text,
        )

    dirty_entries = [line for line in output.splitlines() if line.strip()]
    if dirty_entries:
        return ReleaseCheck(
            id="git:clean-worktree",
            label="Clean release worktree",
            status="fail",
            severity="critical",
            detail=(
                "Release candidate tagging requires a clean source/docs worktree. "
                f"Dirty entries: {len(dirty_entries)}.\n{_tail(output, lines=20)}"
            ),
            command=command_text,
        )

    return ReleaseCheck(
        id="git:clean-worktree",
        label="Clean release worktree",
        status="pass",
        severity="critical",
        detail="git status --porcelain returned no source/docs changes.",
        command=command_text,
    )


def _candidate_tag_check(tag: str) -> ReleaseCheck:
    normalized = tag.strip()
    if not normalized:
        return ReleaseCheck(
            id="git:candidate-tag",
            label="Release candidate tag",
            status="fail",
            severity="critical",
            detail="Release candidate tag cannot be empty.",
        )
    if not RC_TAG_PATTERN.fullmatch(normalized):
        return ReleaseCheck(
            id="git:candidate-tag",
            label="Release candidate tag",
            status="fail",
            severity="critical",
            detail=(
                "Release candidate tag must use `synthesus5-rcN` or semantic RC form "
                "like `v5.0.0-rc1` / `v5.0.0-rc.1`."
            ),
        )

    local_command = ["git", "tag", "--list", normalized]
    local_command_text = " ".join(local_command)
    try:
        local = _run(local_command, timeout=30)
    except subprocess.TimeoutExpired as exc:
        return ReleaseCheck(
            id="git:candidate-tag",
            label="Release candidate tag",
            status="fail",
            severity="critical",
            detail=f"Timed out while checking local tags.\n{_tail(exc.stdout or '')}",
            command=local_command_text,
        )
    if local.returncode != 0:
        return ReleaseCheck(
            id="git:candidate-tag",
            label="Release candidate tag",
            status="fail",
            severity="critical",
            detail=_tail(local.stdout or "") or f"git tag exited {local.returncode}.",
            command=local_command_text,
        )
    if (local.stdout or "").strip():
        return ReleaseCheck(
            id="git:candidate-tag",
            label="Release candidate tag",
            status="fail",
            severity="critical",
            detail=f"Local tag already exists: {normalized}.",
            command=local_command_text,
        )

    remote_command = [
        "git",
        "ls-remote",
        "--tags",
        "origin",
        f"refs/tags/{normalized}",
        f"refs/tags/{normalized}^{{}}",
    ]
    remote_command_text = " ".join(remote_command)
    try:
        remote = _run(remote_command, timeout=45)
    except subprocess.TimeoutExpired as exc:
        return ReleaseCheck(
            id="git:candidate-tag",
            label="Release candidate tag",
            status="fail",
            severity="critical",
            detail=f"Timed out while checking remote tags.\n{_tail(exc.stdout or '')}",
            command=remote_command_text,
        )
    if remote.returncode != 0:
        return ReleaseCheck(
            id="git:candidate-tag",
            label="Release candidate tag",
            status="fail",
            severity="critical",
            detail=_tail(remote.stdout or "") or f"git ls-remote exited {remote.returncode}.",
            command=remote_command_text,
        )
    if (remote.stdout or "").strip():
        return ReleaseCheck(
            id="git:candidate-tag",
            label="Release candidate tag",
            status="fail",
            severity="critical",
            detail=f"Remote tag already exists on origin: {normalized}.",
            command=remote_command_text,
        )

    return ReleaseCheck(
        id="git:candidate-tag",
        label="Release candidate tag",
        status="pass",
        severity="critical",
        detail=f"Candidate tag is valid and available locally/remotely: {normalized}.",
        command=f"{local_command_text} && {remote_command_text}",
        diagnostics={"tag": normalized},
    )


def _knowledge_artifact_check() -> ReleaseCheck:
    command = [sys.executable, "tools/validate_knowledge_cold_start.py"]
    command_text = " ".join(command)
    try:
        completed = _run(command, timeout=90)
    except subprocess.TimeoutExpired as exc:
        return ReleaseCheck(
            id="knowledge:cold-start",
            label="Knowledge Cloud cold-start integrity",
            status="fail",
            severity="critical",
            detail=f"Timed out after 90s. Paid launch stays blocked until cold-start validation completes.\n{_tail(exc.stdout or '')}",
            command=command_text,
        )

    output = completed.stdout or ""
    diagnostics = _extract_cold_start_summary(output)
    if completed.returncode == 0:
        return ReleaseCheck(
            id="knowledge:cold-start",
            label="Knowledge Cloud cold-start integrity",
            status="pass",
            severity="critical",
            detail=_tail(output) or "Knowledge Cloud cold-start validation passed.",
            command=command_text,
            diagnostics=diagnostics,
        )

    generated_bundle_blockers = (
        "FAISS/embedder dim mismatch",
        "FAISS/profile dim mismatch",
        "Embedder/profile dim mismatch",
        "manifest build.source_manifest fingerprint is missing",
        "Knowledge Cloud source-manifest provenance failed",
    )
    status = "blocked" if any(marker in output for marker in generated_bundle_blockers) else "fail"
    return ReleaseCheck(
        id="knowledge:cold-start",
        label="Knowledge Cloud cold-start integrity",
        status=status,
        severity="critical",
        detail=_tail(output) or f"Knowledge Cloud validation exited {completed.returncode}.",
        command=command_text,
        diagnostics=diagnostics,
    )


def collect_release_checks(
    *,
    run_runtime: bool,
    run_focused_suite: bool,
    require_clean_worktree: bool = False,
    candidate_tag: str | None = None,
) -> list[ReleaseCheck]:
    checks = [
        _path_check("README.md", "Repository positioning"),
        _path_check("docs/roadmap/SYNTHESUS_5_CHAL_BLUEPRINT.md", "Synthesus 5 architecture blueprint"),
        _path_check("docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md", "Implementation checklist"),
        _path_check("docs/PHASE20_PRODUCTION_API.md", "Production API contract"),
        _path_check("docs/release/SYNTHESUS_5_RC1_RELEASE_NOTES.md", "Release candidate notes"),
        _path_check("docs/product/COMMERCIAL_PACKAGING.md", "Commercial packaging plan"),
        _path_check("tools/synthesus5_focused_suite.py", "Focused CHAL release suite"),
        _path_check("tools/synthesus5_chal_smoke.py", "Public CHAL API smoke command"),
        _command_check(
            "compile:release-gate",
            "Release gate compiles",
            [sys.executable, "-m", "py_compile", "tools/synthesus5_release_gate.py"],
            timeout=30,
        ),
    ]

    if require_clean_worktree:
        checks.append(_clean_worktree_check())

    if candidate_tag is not None:
        checks.append(_candidate_tag_check(candidate_tag))

    if run_focused_suite:
        checks.append(
            _command_check(
                "runtime:focused-suite",
                "Focused Synthesus 5 release suite",
                [sys.executable, "tools/synthesus5_focused_suite.py"],
                timeout=240,
            )
        )
    else:
        checks.append(
            ReleaseCheck(
                id="runtime:focused-suite",
                label="Focused Synthesus 5 release suite",
                status="skipped",
                severity="critical",
                detail="Skipped by default. Run with --run-focused-suite before tagging a release candidate.",
                command=f"{sys.executable} tools/synthesus5_focused_suite.py",
            )
        )

    if run_runtime:
        checks.append(
            _command_check(
                "runtime:chal-smoke",
                "CHAL API smoke",
                [sys.executable, "tools/synthesus5_chal_smoke.py"],
                timeout=90,
            )
        )
        checks.append(_knowledge_artifact_check())
    else:
        checks.append(
            ReleaseCheck(
                id="runtime:chal-smoke",
                label="CHAL API smoke",
                status="skipped",
                severity="critical",
                detail="Skipped by default. Run with --run-runtime for launch-gate validation.",
                command=f"{sys.executable} tools/synthesus5_chal_smoke.py",
            )
        )
        checks.append(
            ReleaseCheck(
                id="knowledge:cold-start",
                label="Knowledge Cloud cold-start integrity",
                status="skipped",
                severity="critical",
                detail="Skipped by default. Run with --run-runtime before any paid launch.",
                command=f"{sys.executable} tools/validate_knowledge_cold_start.py",
            )
        )

    return checks


def evaluate_launch_tiers(checks: list[ReleaseCheck]) -> list[LaunchTier]:
    runtime_skipped = any(check.id.startswith("runtime:") and check.status == "skipped" for check in checks)
    runtime_blocked = any(check.id.startswith("runtime:") and check.status in {"fail", "blocked"} for check in checks)
    docs_blocked = any(
        check.status in {"fail", "blocked", "skipped"}
        and not check.id.startswith(("runtime:", "knowledge:"))
        for check in checks
        if check.severity == "critical"
    )
    knowledge_blocked = any(
        check.id.startswith("knowledge:") and check.status in {"fail", "blocked", "skipped"}
        for check in checks
    )
    critical_open = [
        check.id
        for check in checks
        if check.severity == "critical" and check.status in {"fail", "blocked", "skipped"}
    ]

    demo_status = "ready" if not docs_blocked else "blocked"
    beta_status = "needs-runtime-gate" if runtime_skipped and not docs_blocked else (
        "limited-beta" if knowledge_blocked and not docs_blocked and not runtime_blocked else ("ready" if not critical_open else "blocked")
    )
    paid_status = "blocked" if critical_open else "ready"

    return [
        LaunchTier(
            tier="demo",
            status=demo_status,
            rationale="Use for controlled demos when docs, API contract, and smoke tooling are present.",
        ),
        LaunchTier(
            tier="private_beta",
            status=beta_status,
            rationale="Requires CHAL smoke and release gate evidence before onboarding real users.",
        ),
        LaunchTier(
            tier="paid_consumer_launch",
            status=paid_status,
            rationale="Requires zero critical failures, passing Knowledge Cloud cold-start integrity, and current release notes.",
        ),
    ]


def build_report(
    *,
    run_runtime: bool,
    run_focused_suite: bool = False,
    require_clean_worktree: bool = False,
    candidate_tag: str | None = None,
) -> dict[str, Any]:
    checks = collect_release_checks(
        run_runtime=run_runtime,
        run_focused_suite=run_focused_suite,
        require_clean_worktree=require_clean_worktree,
        candidate_tag=candidate_tag,
    )
    tiers = evaluate_launch_tiers(checks)
    critical_blockers = [
        asdict(check)
        for check in checks
        if check.severity == "critical" and check.status in {"fail", "blocked", "skipped"}
    ]
    return {
        "schema": "synthesus.release_gate.v1",
        "product": "Synthesus 5 CHAL",
        "positioning": "bounded synthetic intelligence runtime for NPCs, business bots, and inspectable agent services",
        "run_runtime": run_runtime,
        "run_focused_suite": run_focused_suite,
        "require_clean_worktree": require_clean_worktree,
        "candidate_tag": candidate_tag,
        "checks": [asdict(check) for check in checks],
        "launch_tiers": [asdict(tier) for tier in tiers],
        "critical_blockers": critical_blockers,
        "monetizable_surfaces": [
            "business_bot_api",
            "npc_runtime_api",
            "character_pack_studio",
            "knowledge_cloud_managed_bundle",
            "enterprise_aivm_runtime",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Synthesus 5 commercial release readiness report.")
    parser.add_argument("--run-runtime", action="store_true", help="Run CHAL smoke and Knowledge Cloud cold-start checks.")
    parser.add_argument("--run-focused-suite", action="store_true", help="Run the focused Synthesus 5 release suite.")
    parser.add_argument(
        "--require-clean-worktree",
        action="store_true",
        help="Require git status --porcelain to be clean before RC tagging.",
    )
    parser.add_argument(
        "--candidate-tag",
        help=(
            "Validate an available release-candidate tag before RC tagging "
            "(for example `synthesus5-rc1` or `v5.0.0-rc1`)."
        ),
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON report output path.")
    parser.add_argument("--fail-on-blocker", action="store_true", help="Exit non-zero when critical blockers remain.")
    args = parser.parse_args()

    report = build_report(
        run_runtime=args.run_runtime,
        run_focused_suite=args.run_focused_suite,
        require_clean_worktree=args.require_clean_worktree,
        candidate_tag=args.candidate_tag,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"Release gate report: {output}")

    if args.fail_on_blocker and report["critical_blockers"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
