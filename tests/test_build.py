import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from synthesus_knowledge_cloud.__main__ import main
from synthesus_knowledge_cloud.build import _run_pipeline, plan_build, run_build, stamp_existing_manifest
from synthesus_knowledge_cloud.manifest import build_manifest, verify_source_manifest, write_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_current_source_manifest(repo: Path) -> None:
    sources = repo / "sources"
    manifests = repo / "manifests"
    sources.mkdir()
    manifests.mkdir()
    (sources / "sample.yaml").write_text("id: sample\n", encoding="utf-8")
    source_manifest = build_manifest(repo, ["sources"], kind="synthesus-knowledge-source-plane")
    write_manifest(source_manifest, manifests / "source_manifest.json")


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


def test_run_pipeline_stages_and_atomically_installs_canonical_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "faiss.index").write_bytes(b"old-index")
    expected = {
        "faiss.index",
        "faiss_metadata.json",
        "knowledge.kndb",
        "knowledge.kndb.meta.db",
        "knowledge.meta.db",
        "models/swarm_embedder.pkl",
    }

    def fake_run(command, **_kwargs):
        assert "--artifact-root" in command
        assert "--data-dir" not in command
        staging = Path(command[command.index("--artifact-root") + 1])
        for rel in expected:
            path = staging / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"new:{rel}".encode())
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("synthesus_knowledge_cloud.build.subprocess.run", fake_run)
    plan = SimpleNamespace(
        artifact_root=artifacts,
        repo_root=tmp_path,
        embed_dim=128,
        sample_jeopardy=10,
        sample_conceptnet=20,
    )

    exit_code, stdout, stderr = _run_pipeline(plan)

    assert (exit_code, stdout, stderr) == (0, "ok", "")
    for rel in expected:
        assert (artifacts / rel).read_bytes() == f"new:{rel}".encode()


def test_stamp_manifest_rejects_runtime_semantic_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_current_source_manifest(tmp_path)
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
    _write_current_source_manifest(tmp_path)
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


def test_stamp_manifest_rejects_stale_source_manifest(tmp_path: Path) -> None:
    _write_current_source_manifest(tmp_path)
    (tmp_path / "sources" / "sample.yaml").write_text("id: changed\n", encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "sample.txt").write_text("hello", encoding="utf-8")
    original_manifest = build_manifest(artifacts, ["."], kind="test")
    write_manifest(original_manifest, artifacts / "manifest.json")

    with pytest.raises(RuntimeError, match="source manifest validation failed"):
        stamp_existing_manifest(repo_root=tmp_path, artifact_root=artifacts)
    assert "build" not in (artifacts / "manifest.json").read_text(encoding="utf-8")

    assert main(["stamp-manifest", "--repo-root", str(tmp_path), "--artifact-root", str(artifacts)]) == 1


def test_verify_source_manifest_rejects_duplicate_artifact_paths(tmp_path: Path) -> None:
    _write_current_source_manifest(tmp_path)
    manifest_path = tmp_path / "manifests" / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"].append(dict(manifest["artifacts"][0]))
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    result = verify_source_manifest(tmp_path)

    assert not result.ok
    assert result.failures[0] == "duplicate artifact path: sources/sample.yaml"
