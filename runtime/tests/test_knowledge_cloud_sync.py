from pathlib import Path

from knowledge_integration.cloud_sync import CloudArtifact, build_manifest, sync_artifacts


def test_build_manifest_hashes_files(tmp_path: Path):
    payload = tmp_path / "artifact.bin"
    payload.write_bytes(b"hello world")

    manifest = build_manifest(tmp_path, ["artifact.bin"])

    assert manifest["version"] == "1"
    assert len(manifest["artifacts"]) == 1
    item = manifest["artifacts"][0]
    assert item["path"] == "artifact.bin"
    assert item["size"] == 11
    assert len(item["sha256"]) == 64


def test_sync_artifacts_disabled_when_no_base_url(tmp_path: Path):
    report = sync_artifacts(tmp_path, [CloudArtifact("missing.bin")], base_url="", mode="auto")

    assert report["disabled"] is True
    assert report["downloaded"] == []
