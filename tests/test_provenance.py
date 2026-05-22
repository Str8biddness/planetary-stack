import json
from pathlib import Path

from synthesus_knowledge_cloud.manifest import build_manifest, write_manifest
from synthesus_knowledge_cloud.provenance import (
    capture_provenance,
    dataset_versions,
    embedder_fingerprint,
    stamp_manifest,
)


def test_provenance_captures_git_and_versions(tmp_path: Path) -> None:
    # Use the real repo root for git info; the function tolerates non-git too.
    repo_root = Path(__file__).resolve().parents[1]
    prov = capture_provenance(repo_root, profile="public-base")
    data = prov.to_dict()
    assert data["package_version"]
    assert data["python_version"]
    assert data["profile"] == "public-base"
    # Real repo has datasets/.
    if (repo_root / "sources").exists():
        assert isinstance(data["datasets"], dict)


def test_dataset_versions_reads_yaml_keys(tmp_path: Path) -> None:
    repo = tmp_path
    src = repo / "sources"
    src.mkdir()
    (src / "thing.yaml").write_text(
        'version: "1"\nid: thing\nname: Thing\nlicense:\n  spdx: MIT\n',
        encoding="utf-8",
    )
    versions = dataset_versions(repo)
    assert "thing" in versions
    assert versions["thing"]["version"] == "1"


def test_embedder_fingerprint_round_trip(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    (artifacts / "models").mkdir(parents=True)
    (artifacts / "models" / "swarm_embedder.pkl").write_bytes(b"x" * 256)
    fp = embedder_fingerprint(artifacts)
    assert fp is not None
    assert fp["size"] == 256
    assert len(fp["sha256"]) == 64


def test_stamp_manifest_adds_build_block(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "a.txt").write_text("a", encoding="utf-8")
    manifest = build_manifest(artifacts, ["."], kind="test")
    prov = capture_provenance(tmp_path, artifact_root=artifacts, profile="public-base")
    stamped = stamp_manifest(manifest, prov)
    assert "build" in stamped
    assert stamped["build"]["profile"] == "public-base"
    assert "manifest_revised_at" in stamped
    write_manifest(stamped, artifacts / "manifest.json")
    loaded = json.loads((artifacts / "manifest.json").read_text(encoding="utf-8"))
    assert loaded["build"]["package_version"]
