from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from synthesus5_release_gate import build_report, evaluate_launch_tiers, ReleaseCheck


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
