from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from knowledge.kal_adapter import CHALMemoryController
from knowledge.mount_table import KnowledgeCloudMountTable, MountType


def _write_artifact(root: Path, relative_path: str, content: bytes) -> dict:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "path": relative_path,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _write_manifest(root: Path, artifacts: list[dict]) -> None:
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "version": "1",
                "generated_at": "2026-05-28T00:00:00+00:00",
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )


def test_mount_table_boots_manifest_artifacts_as_chal_mounts(tmp_path: Path):
    artifacts = [
        _write_artifact(tmp_path, "knowledge_cloud/world_lore.json", b'{"lore": []}\n'),
        _write_artifact(tmp_path, "faiss.index", b"index-bytes"),
        _write_artifact(tmp_path, "faiss_metadata.json", b'{"sources": []}\n'),
    ]
    _write_manifest(tmp_path, artifacts)

    report = KnowledgeCloudMountTable().boot(tmp_path, strict=True)
    mounts = {mount.mount_path: mount for mount in report.mounts}

    assert report.ok is True
    assert mounts["/mnt/rom/world_lore"].mount_type == MountType.ROM
    assert mounts["/mnt/corpus/faiss"].mount_type == MountType.GROUNDING_CORPUS
    assert mounts["/mnt/provenance/faiss_metadata"].mount_type == MountType.SOURCE_PROVENANCE
    assert mounts["/mnt/rom/world_lore"].partition.metadata["integrity_ok"] is True


def test_mount_table_deactivates_failed_integrity_without_strict_mode(tmp_path: Path):
    item = _write_artifact(tmp_path, "knowledge_cloud/world_lore.json", b'{"lore": []}\n')
    item["sha256"] = "0" * 64
    _write_manifest(tmp_path, [item])

    report = KnowledgeCloudMountTable().boot(tmp_path)
    mount = report.mounts[0]

    assert report.ok is False
    assert mount.is_active is False
    assert mount.trust_level == 0.0
    assert mount.partition.metadata["sha256_ok"] is False


def test_mount_table_strict_mode_rejects_failed_integrity(tmp_path: Path):
    item = _write_artifact(tmp_path, "knowledge_cloud/world_lore.json", b'{"lore": []}\n')
    item["size"] = 999
    _write_manifest(tmp_path, [item])

    with pytest.raises(ValueError):
        KnowledgeCloudMountTable().boot(tmp_path, strict=True)


def test_kal_controller_boots_from_manifest_before_default_mounts(tmp_path: Path):
    artifacts = [
        _write_artifact(tmp_path, "knowledge_cloud/world_lore.json", b'{"lore": []}\n'),
        _write_artifact(tmp_path, "models/swarm_embedder.pkl", b"model-bytes"),
    ]
    _write_manifest(tmp_path, artifacts)

    controller = CHALMemoryController(knowledge_root=tmp_path, strict_mount_integrity=True)
    report = controller.get_mount_boot_report()
    mounts = {mount.mount_path: mount for mount in controller.get_mounts()}

    assert report is not None
    assert report.ok is True
    assert "/mnt/rom/world_lore" in mounts
    assert "/mnt/params/swarm_embedder" in mounts
    assert "/mnt/rom/lore" not in mounts


def test_kal_hot_context_serves_repeated_mounted_queries(tmp_path: Path):
    _write_manifest(
        tmp_path,
        [_write_artifact(tmp_path, "knowledge_cloud/world_lore.json", b'{"lore": []}\n')],
    )

    class FakeKnowledgeCloud:
        def __init__(self):
            self.calls = 0

        def lookup(self, text: str, trust: float):
            self.calls += 1
            return {
                "response": f"grounded:{text}:{trust:.0f}",
                "confidence": 0.86,
                "source": "fake-rom",
            }

    controller = CHALMemoryController(
        knowledge_root=tmp_path,
        strict_mount_integrity=True,
        hot_context_limit=2,
    )
    fake_cloud = FakeKnowledgeCloud()
    controller._knowledge_cloud = fake_cloud
    controller._runtime = None

    first_response, first_telemetry = controller.query(" Where is the lore? ")
    second_response, second_telemetry = controller.query("where   is the lore?")
    stats = controller.get_hot_context_stats()

    assert first_response == second_response
    assert fake_cloud.calls == 1
    assert first_telemetry.operation_id == "kc_lookup"
    assert first_telemetry.cache_hit is False
    assert first_telemetry.metadata["hot_context"] is False
    assert first_telemetry.metadata["mounts"][0]["mount_path"] == "/mnt/rom/world_lore"
    assert second_telemetry.operation_id == "hot_context_hit"
    assert second_telemetry.cache_hit is True
    assert second_telemetry.metadata["hot_context"] is True
    assert stats["entries"] == 1
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_kal_hot_context_lru_eviction(tmp_path: Path):
    _write_manifest(
        tmp_path,
        [_write_artifact(tmp_path, "knowledge_cloud/world_lore.json", b'{"lore": []}\n')],
    )

    class FakeKnowledgeCloud:
        def __init__(self):
            self.calls: list[str] = []

        def lookup(self, text: str, trust: float):
            self.calls.append(text)
            return {"response": text.upper(), "confidence": 0.75}

    controller = CHALMemoryController(
        knowledge_root=tmp_path,
        strict_mount_integrity=True,
        hot_context_limit=1,
    )
    fake_cloud = FakeKnowledgeCloud()
    controller._knowledge_cloud = fake_cloud
    controller._runtime = None

    controller.query("alpha")
    controller.query("beta")
    _, telemetry = controller.query("alpha")

    assert fake_cloud.calls == ["alpha", "beta", "alpha"]
    assert telemetry.operation_id == "kc_lookup"
    assert controller.get_hot_context_stats()["entries"] == 1
