from pathlib import Path
from types import SimpleNamespace

import pytest

from synthesus_knowledge_cloud.__main__ import main
from synthesus_knowledge_cloud.build import plan_build, run_build, stamp_existing_manifest
from synthesus_knowledge_cloud.manifest import build_manifest, write_manifest


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


def test_stamp_manifest_rejects_runtime_semantic_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True)
    (artifacts / "faiss.index").write_bytes(b"fake-index")
    (artifacts / "faiss_metadata.json").write_text("[{}]", encoding="utf-8")
    (artifacts / "models" / "swarm_embedder.pkl").write_bytes(b"fake-model")
    original_manifest = build_manifest(artifacts, ["."], kind="test")
    original_manifest["generated_at"] = "preserve-me"
    write_manifest(original_manifest, artifacts / "manifest.json")

    fake_faiss = SimpleNamespace(read_index=lambda _path: SimpleNamespace(ntotal=1, d=384))
    fake_joblib = SimpleNamespace(load=lambda _path: {"dim": 128})
    monkeypatch.setitem(__import__("sys").modules, "faiss", fake_faiss)
    monkeypatch.setitem(__import__("sys").modules, "joblib", fake_joblib)

    with pytest.raises(RuntimeError, match="FAISS/embedder dim mismatch"):
        stamp_existing_manifest(repo_root=tmp_path, artifact_root=artifacts)
    assert "build" not in (artifacts / "manifest.json").read_text(encoding="utf-8")

    assert main(["stamp-manifest", "--repo-root", str(tmp_path), "--artifact-root", str(artifacts)]) == 1


def test_stamp_manifest_rejects_profile_embed_dim_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True)
    (artifacts / "faiss.index").write_bytes(b"fake-index")
    (artifacts / "faiss_metadata.json").write_text("[{}]", encoding="utf-8")
    (artifacts / "models" / "swarm_embedder.pkl").write_bytes(b"fake-model")
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "\n".join(
            [
                "name: profile-dim-contract",
                "embedding:",
                "  dim: 128",
                "outputs: {}",
                "sources: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    original_manifest = build_manifest(artifacts, ["."], kind="test")
    write_manifest(original_manifest, artifacts / "manifest.json")

    fake_faiss = SimpleNamespace(read_index=lambda _path: SimpleNamespace(ntotal=1, d=384))
    fake_joblib = SimpleNamespace(load=lambda _path: {"dim": 384})
    monkeypatch.setitem(__import__("sys").modules, "faiss", fake_faiss)
    monkeypatch.setitem(__import__("sys").modules, "joblib", fake_joblib)

    with pytest.raises(RuntimeError, match="swarm embedder profile dim mismatch"):
        stamp_existing_manifest(repo_root=tmp_path, artifact_root=artifacts, profile_path=profile)
    assert "build" not in (artifacts / "manifest.json").read_text(encoding="utf-8")

    assert (
        main(
            [
                "stamp-manifest",
                "--repo-root",
                str(tmp_path),
                "--artifact-root",
                str(artifacts),
                "--profile",
                str(profile),
            ]
        )
        == 1
    )
