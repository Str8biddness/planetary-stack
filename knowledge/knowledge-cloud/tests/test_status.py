import json
from pathlib import Path

from synthesus_knowledge_cloud.manifest import build_manifest, write_manifest
from synthesus_knowledge_cloud.status import status_report


def _make_remote(remote: Path) -> None:
    (remote / "models").mkdir(parents=True, exist_ok=True)
    (remote / "models" / "swarm_embedder.pkl").write_bytes(b"x" * 1024)
    (remote / "world_lore.json").write_text(json.dumps({"entries": []}), encoding="utf-8")
    manifest = build_manifest(remote, ["."], kind="test")
    write_manifest(manifest, remote / "manifest.json")


def test_status_all_ok(tmp_path: Path) -> None:
    remote = tmp_path / "remote"
    local = tmp_path / "local"
    remote.mkdir()
    local.mkdir()
    _make_remote(remote)
    # Copy remote into local exactly.
    for path in remote.rglob("*"):
        if path.is_file() and path.name != "manifest.json":
            target = local / path.relative_to(remote)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
    report = status_report(local, mirrors=[f"file://{remote}"])
    assert report.remote_manifest_present
    assert all(a.state == "ok" for a in report.artifacts)
    assert report.extras == []


def test_status_drift(tmp_path: Path) -> None:
    remote = tmp_path / "remote"
    local = tmp_path / "local"
    remote.mkdir()
    local.mkdir()
    _make_remote(remote)
    # Local is empty: every artifact should be "missing".
    report = status_report(local, mirrors=[f"file://{remote}"])
    states = sorted({a.state for a in report.artifacts})
    assert states == ["missing"]


def test_status_size_and_sha_mismatch_and_extras(tmp_path: Path) -> None:
    remote = tmp_path / "remote"
    local = tmp_path / "local"
    remote.mkdir()
    local.mkdir()
    _make_remote(remote)
    # Mirror local with deliberate drift.
    (local / "models").mkdir()
    (local / "models" / "swarm_embedder.pkl").write_bytes(b"x" * 512)  # size mismatch
    (local / "world_lore.json").write_text("{}", encoding="utf-8")  # both size + sha mismatch
    (local / "stray.txt").write_text("extra", encoding="utf-8")
    report = status_report(local, mirrors=[f"file://{remote}"])
    states = {a.path: a.state for a in report.artifacts}
    assert states["models/swarm_embedder.pkl"] in {"size_mismatch", "sha_mismatch"}
    assert states["world_lore.json"] in {"size_mismatch", "sha_mismatch"}
    assert "stray.txt" in report.extras
