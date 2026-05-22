from pathlib import Path

from synthesus_knowledge_cloud.build import plan_build, run_build


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_plan_build_derives_sample_sizes() -> None:
    plan = plan_build(REPO_ROOT / "profiles" / "public-base.yaml", repo_root=REPO_ROOT)
    assert plan.profile_name == "public-base"
    assert plan.sample_jeopardy == int(250_000 * 0.35)
    assert plan.sample_conceptnet == int(250_000 * 0.30)
    assert plan.embed_dim == 128
    assert "jeopardy" in plan.sources


def test_run_build_dry_run() -> None:
    report = run_build(REPO_ROOT / "profiles" / "public-base.yaml", repo_root=REPO_ROOT, execute=False)
    assert not report.executed
    assert report.exit_code is None
    assert report.ok  # dry-run is always "ok" if source planes validate
