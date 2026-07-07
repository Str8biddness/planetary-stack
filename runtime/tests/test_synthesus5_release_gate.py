from pathlib import Path

import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import subprocess

from synthesus5_release_gate import (
    _clean_worktree_check,
    _candidate_tag_check,
    _knowledge_artifact_check,
    build_report,
    evaluate_launch_tiers,
    ReleaseCheck,
)


def test_static_release_gate_report_has_commercial_surfaces():
    report = build_report(run_runtime=False)

    assert report["schema"] == "synthesus.release_gate.v1"
    assert report["product"] == "Synthesus 5 CHAL"
    assert "business_bot_api" in report["monetizable_surfaces"]
    assert "npc_runtime_api" in report["monetizable_surfaces"]
    assert any(check["id"] == "runtime:focused-suite" and check["status"] == "skipped" for check in report["checks"])
    assert any(check["id"] == "runtime:chal-smoke" and check["status"] == "skipped" for check in report["checks"])
    assert any(tier["tier"] == "demo" and tier["status"] == "ready" for tier in report["launch_tiers"])
    assert any(tier["tier"] == "private_beta" and tier["status"] == "needs-runtime-gate" for tier in report["launch_tiers"])
    assert any(tier["tier"] == "paid_consumer_launch" and tier["status"] == "blocked" for tier in report["launch_tiers"])


def test_paid_launch_requires_all_critical_checks_to_pass():
    checks = [
        ReleaseCheck("docs:release", "Release notes", "pass", "critical", "ok"),
        ReleaseCheck("runtime:focused-suite", "Focused suite", "pass", "critical", "ok"),
        ReleaseCheck("runtime:chal-smoke", "CHAL smoke", "pass", "critical", "ok"),
        ReleaseCheck("knowledge:cold-start", "Knowledge", "pass", "critical", "ok"),
    ]

    tiers = {tier.tier: tier.status for tier in evaluate_launch_tiers(checks)}

    assert tiers["demo"] == "ready"
    assert tiers["private_beta"] == "ready"
    assert tiers["paid_consumer_launch"] == "ready"


def test_blocked_knowledge_cloud_blocks_paid_launch():
    checks = [
        ReleaseCheck("docs:release", "Release notes", "pass", "critical", "ok"),
        ReleaseCheck("runtime:focused-suite", "Focused suite", "pass", "critical", "ok"),
        ReleaseCheck("runtime:chal-smoke", "CHAL smoke", "pass", "critical", "ok"),
        ReleaseCheck("knowledge:cold-start", "Knowledge", "blocked", "critical", "FAISS/embedder dim mismatch"),
    ]

    tiers = {tier.tier: tier.status for tier in evaluate_launch_tiers(checks)}

    assert tiers["demo"] == "ready"
    assert tiers["private_beta"] == "limited-beta"
    assert tiers["paid_consumer_launch"] == "blocked"


def test_missing_source_manifest_provenance_is_release_blocker(monkeypatch):
    def fake_run(command, *, timeout):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=(
                "Knowledge Cloud cold-start validation failed: "
                "Knowledge Cloud source-manifest provenance failed: "
                "manifest build.source_manifest fingerprint is missing\n"
            ),
        )

    monkeypatch.setattr("synthesus5_release_gate._run", fake_run)

    check = _knowledge_artifact_check()

    assert check.status == "blocked"
    assert check.id == "knowledge:cold-start"
    assert "build.source_manifest" in check.detail


def test_knowledge_cold_start_summary_is_preserved_on_blocker(monkeypatch):
    summary = {
        "schema": "synthesus.knowledge_cold_start.summary.v1",
        "ok": False,
        "retrieval_semantics": {
            "faiss_dim": 384,
            "embedder_dim": 128,
            "profile_embedder_dim": 128,
            "errors": ["FAISS/embedder dim mismatch: faiss=384, embedder=128"],
        },
        "source_manifest_provenance": {
            "errors": ["manifest build.source_manifest fingerprint is missing"],
        },
    }

    def fake_run(command, *, timeout):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=(
                "cold_start_summary="
                + json.dumps(summary)
                + "\nKnowledge Cloud cold-start validation failed: "
                "FAISS/embedder dim mismatch: faiss=384, embedder=128\n"
            ),
        )

    monkeypatch.setattr("synthesus5_release_gate._run", fake_run)

    check = _knowledge_artifact_check()

    assert check.status == "blocked"
    assert check.diagnostics["retrieval_semantics"]["faiss_dim"] == 384
    assert check.diagnostics["retrieval_semantics"]["embedder_dim"] == 128
    assert "build.source_manifest" in check.diagnostics["source_manifest_provenance"]["errors"][0]


def test_knowledge_cold_start_summary_is_preserved_on_pass(monkeypatch):
    summary = {
        "schema": "synthesus.knowledge_cold_start.summary.v1",
        "ok": True,
        "retrieval_semantics": {
            "faiss_dim": 128,
            "embedder_dim": 128,
            "profile_embedder_dim": 128,
            "errors": [],
        },
        "source_manifest_provenance": {"errors": []},
    }

    def fake_run(command, *, timeout):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="cold_start_summary=" + json.dumps(summary) + "\nKnowledge Cloud cold-start bundle OK\n",
        )

    monkeypatch.setattr("synthesus5_release_gate._run", fake_run)

    check = _knowledge_artifact_check()

    assert check.status == "pass"
    assert check.diagnostics["ok"] is True
    assert check.diagnostics["retrieval_semantics"]["profile_embedder_dim"] == 128


def test_clean_worktree_gate_passes_when_git_status_is_empty(monkeypatch):
    def fake_run(command, *, timeout):
        return subprocess.CompletedProcess(command, 0, stdout="")

    monkeypatch.setattr("synthesus5_release_gate._run", fake_run)

    check = _clean_worktree_check()

    assert check.status == "pass"
    assert check.id == "git:clean-worktree"


def test_clean_worktree_gate_blocks_dirty_release_candidate(monkeypatch):
    def fake_run(command, *, timeout):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=" M tools/synthesus5_release_gate.py\n?? tools/results/latest.json\n",
        )

    monkeypatch.setattr("synthesus5_release_gate._run", fake_run)

    check = _clean_worktree_check()

    assert check.status == "fail"
    assert check.id == "git:clean-worktree"
    assert "Dirty entries: 2" in check.detail
    assert "tools/synthesus5_release_gate.py" in check.detail


def test_release_gate_can_require_clean_worktree(monkeypatch):
    monkeypatch.setattr(
        "synthesus5_release_gate._clean_worktree_check",
        lambda: ReleaseCheck("git:clean-worktree", "Clean release worktree", "pass", "critical", "ok"),
    )

    report = build_report(run_runtime=False, require_clean_worktree=True)

    assert report["require_clean_worktree"] is True
    assert any(check["id"] == "git:clean-worktree" and check["status"] == "pass" for check in report["checks"])


def test_candidate_tag_gate_rejects_invalid_tag():
    check = _candidate_tag_check("latest")

    assert check.status == "fail"
    assert check.id == "git:candidate-tag"
    assert "synthesus5-rcN" in check.detail


def test_candidate_tag_gate_blocks_existing_local_tag(monkeypatch):
    def fake_run(command, *, timeout):
        assert command[:3] == ["git", "tag", "--list"]
        return subprocess.CompletedProcess(command, 0, stdout="synthesus5-rc1\n")

    monkeypatch.setattr("synthesus5_release_gate._run", fake_run)

    check = _candidate_tag_check("synthesus5-rc1")

    assert check.status == "fail"
    assert "Local tag already exists" in check.detail


def test_candidate_tag_gate_blocks_existing_remote_tag(monkeypatch):
    def fake_run(command, *, timeout):
        if command[:3] == ["git", "tag", "--list"]:
            return subprocess.CompletedProcess(command, 0, stdout="")
        assert command[:3] == ["git", "ls-remote", "--tags"]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="abc123\trefs/tags/synthesus5-rc1\n",
        )

    monkeypatch.setattr("synthesus5_release_gate._run", fake_run)

    check = _candidate_tag_check("synthesus5-rc1")

    assert check.status == "fail"
    assert "Remote tag already exists" in check.detail


def test_candidate_tag_gate_accepts_available_rc_tag(monkeypatch):
    calls = []

    def fake_run(command, *, timeout):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="")

    monkeypatch.setattr("synthesus5_release_gate._run", fake_run)

    check = _candidate_tag_check("v5.0.0-rc.1")

    assert check.status == "pass"
    assert check.diagnostics["tag"] == "v5.0.0-rc.1"
    assert calls[0] == ["git", "tag", "--list", "v5.0.0-rc.1"]
    assert calls[1][:3] == ["git", "ls-remote", "--tags"]


def test_release_gate_can_validate_candidate_tag(monkeypatch):
    monkeypatch.setattr(
        "synthesus5_release_gate._candidate_tag_check",
        lambda tag: ReleaseCheck(
            "git:candidate-tag",
            "Release candidate tag",
            "pass",
            "critical",
            "ok",
            diagnostics={"tag": tag},
        ),
    )

    report = build_report(run_runtime=False, candidate_tag="synthesus5-rc1")

    assert report["candidate_tag"] == "synthesus5-rc1"
    assert any(check["id"] == "git:candidate-tag" and check["status"] == "pass" for check in report["checks"])
