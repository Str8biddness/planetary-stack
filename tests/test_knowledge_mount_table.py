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
