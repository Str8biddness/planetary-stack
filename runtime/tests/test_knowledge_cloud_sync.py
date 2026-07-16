import hashlib
from pathlib import Path

import knowledge_integration.cloud_sync as cloud_sync
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


def test_sync_artifacts_persists_manifest_and_skips_hash_verified_file(tmp_path: Path, monkeypatch):
    payload = b"verified artifact"
    artifact_path = tmp_path / "artifact.bin"
    artifact_path.write_bytes(payload)
    manifest = {
        "version": "1",
        "artifacts": [
            {
                "path": "artifact.bin",
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
    }
    monkeypatch.setattr(cloud_sync, "_read_json_url", lambda _url: manifest)

    report = sync_artifacts(
        tmp_path,
        [CloudArtifact("artifact.bin")],
        base_url="https://example.test",
        mode="auto",
    )

    assert report["skipped"] == ["artifact.bin"]
    assert (tmp_path / "manifest.json").exists()
    assert '"artifact.bin"' in (tmp_path / "manifest.json").read_text(encoding="utf-8")


def test_sync_artifacts_redownloads_same_size_hash_mismatch(tmp_path: Path, monkeypatch):
    expected = b"right"
    artifact_path = tmp_path / "artifact.bin"
    artifact_path.write_bytes(b"wrong")
    manifest = {
        "version": "1",
        "artifacts": [
            {
                "path": "artifact.bin",
                "size": len(expected),
                "sha256": hashlib.sha256(expected).hexdigest(),
            }
        ],
    }
    monkeypatch.setattr(cloud_sync, "_read_json_url", lambda _url: manifest)

    def fake_download(_url, dest, expected_sha256=None, expected_size=None):
        assert expected_sha256 == hashlib.sha256(expected).hexdigest()
        assert expected_size == len(expected)
        dest.write_bytes(expected)

    monkeypatch.setattr(cloud_sync, "_download_file", fake_download)

    report = sync_artifacts(
        tmp_path,
        [CloudArtifact("artifact.bin")],
        base_url="https://example.test",
        mode="auto",
    )

    assert report["downloaded"] == ["artifact.bin"]
    assert artifact_path.read_bytes() == expected
