"""Knowledge Cloud CHAL mount-table boot and manifest integrity checks."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from core.chal.interfaces import Mount, MountType, Partition
except ImportError:
    try:
        from chal.interfaces import Mount, MountType, Partition
    except ImportError:
        interfaces_path = Path(__file__).resolve().parents[1] / "core" / "chal" / "interfaces.py"
        spec = importlib.util.spec_from_file_location("_synthesus_chal_interfaces", interfaces_path)
        if spec is None or spec.loader is None:
            raise
        interfaces = sys.modules.get(spec.name)
        if interfaces is None:
            interfaces = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = interfaces
            spec.loader.exec_module(interfaces)
        Mount = interfaces.Mount
        MountType = interfaces.MountType
        Partition = interfaces.Partition


DEFAULT_MOUNT_SPECS: dict[str, tuple[str, MountType, str, bool, str]] = {
    "knowledge_cloud/world_lore.json": (
        "/mnt/rom/world_lore",
        MountType.ROM,
        "game_lore",
        True,
        "local",
    ),
    "knowledge_cloud/evolution.json": (
        "/mnt/rom/evolution",
        MountType.ROM,
        "evolution",
        True,
        "local",
    ),
    "knowledge_cloud/transitions.json": (
        "/mnt/params/transitions",
        MountType.PARAMETER_DISK,
        "transition_rules",
        True,
        "local",
    ),
    "knowledge_cloud/chaining_patterns.json": (
        "/mnt/params/chaining_patterns",
        MountType.PARAMETER_DISK,
        "reasoning_rules",
        True,
        "local",
    ),
    "models/swarm_embedder.pkl": (
        "/mnt/params/swarm_embedder",
        MountType.PARAMETER_DISK,
        "embedding_model",
        True,
        "local",
    ),
    "faiss.index": (
        "/mnt/corpus/faiss",
        MountType.GROUNDING_CORPUS,
        "semantic_index",
        True,
        "local",
    ),
    "faiss_metadata.json": (
        "/mnt/provenance/faiss_metadata",
        MountType.SOURCE_PROVENANCE,
        "source_provenance",
        True,
        "local",
    ),
    "knowledge.kndb": (
        "/mnt/rom/knowledge_nodes",
        MountType.ROM,
        "knowledge_nodes",
        True,
        "local",
    ),
    "knowledge.kndb.meta.db": (
        "/mnt/provenance/kndb_metadata",
        MountType.SOURCE_PROVENANCE,
        "source_provenance",
        True,
        "local",
    ),
}

COLD_START_REQUIRED_MOUNTS: tuple[str, ...] = (
    "/mnt/rom/world_lore",
    "/mnt/params/transitions",
    "/mnt/params/chaining_patterns",
    "/mnt/params/swarm_embedder",
    "/mnt/corpus/faiss",
    "/mnt/provenance/faiss_metadata",
    "/mnt/rom/knowledge_nodes",
    "/mnt/provenance/kndb_metadata",
)


@dataclass(frozen=True)
class MountIntegrityReport:
    relative_path: str
    mount_path: str
    exists: bool
    size_ok: bool
    sha256_ok: bool
    expected_size: int | None
    actual_size: int | None
    expected_sha256: str | None
    actual_sha256: str | None

    @property
    def ok(self) -> bool:
        return self.exists and self.size_ok and self.sha256_ok

    def as_metadata(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "mount_path": self.mount_path,
            "exists": self.exists,
            "size_ok": self.size_ok,
            "sha256_ok": self.sha256_ok,
            "expected_size": self.expected_size,
            "actual_size": self.actual_size,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "integrity_ok": self.ok,
        }


@dataclass(frozen=True)
class MountTableBootReport:
    manifest_path: str
    manifest_version: str | None
    mounts: tuple[Mount, ...]
    integrity: tuple[MountIntegrityReport, ...]

    @property
    def ok(self) -> bool:
        return all(report.ok for report in self.integrity)

    @property
    def active_mount_paths(self) -> tuple[str, ...]:
        return tuple(mount.mount_path for mount in self.mounts if mount.is_active)

    def missing_active_mounts(self, required_mounts: tuple[str, ...]) -> tuple[str, ...]:
        active = set(self.active_mount_paths)
        return tuple(mount_path for mount_path in required_mounts if mount_path not in active)

    def assert_cold_start_ready(
        self,
        required_mounts: tuple[str, ...] = COLD_START_REQUIRED_MOUNTS,
    ) -> None:
        if not self.ok:
            failed = ", ".join(
                report.relative_path for report in self.integrity if not report.ok
            )
            raise ValueError(f"Knowledge Cloud bundle integrity failed: {failed}")
        missing = self.missing_active_mounts(required_mounts)
        if missing:
            raise ValueError(
                "Knowledge Cloud cold-start bundle missing required active mounts: "
                + ", ".join(missing)
            )


class KnowledgeCloudMountTable:
    """Boots Knowledge Cloud artifacts as explicit CHAL hardware mounts."""

    def __init__(self, artifact_specs: dict[str, tuple[str, MountType, str, bool, str]] | None = None):
        self._artifact_specs = artifact_specs or DEFAULT_MOUNT_SPECS

    def boot(
        self,
        root_dir: str | Path,
        manifest_name: str = "manifest.json",
        *,
        strict: bool = False,
    ) -> MountTableBootReport:
        root = Path(root_dir)
        manifest_path = root / manifest_name
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        mounts: list[Mount] = []
        reports: list[MountIntegrityReport] = []

        for item in manifest.get("artifacts", []):
            relative_path = str(item.get("path", "")).replace("\\", "/")
            spec = self._artifact_specs.get(relative_path)
            if not relative_path or spec is None:
                continue

            mount_path, mount_type, namespace, read_only, locality = spec
            report = self._verify_artifact(root, relative_path, mount_path, item)
            reports.append(report)
            if strict and not report.ok:
                raise ValueError(f"Knowledge Cloud artifact integrity failed: {relative_path}")

            mounts.append(
                Mount(
                    mount_path=mount_path,
                    mount_type=mount_type,
                    partition=Partition(
                        partition_id=self._partition_id(relative_path),
                        namespace=namespace,
                        is_read_only=read_only,
                        metadata=report.as_metadata(),
                    ),
                    locality=locality,
                    trust_level=1.0 if report.ok else 0.0,
                    latency_profile="fast" if locality == "local" else "medium",
                    is_active=report.ok,
                )
            )

        return MountTableBootReport(
            manifest_path=str(manifest_path),
            manifest_version=str(manifest.get("version")) if manifest.get("version") is not None else None,
            mounts=tuple(mounts),
            integrity=tuple(reports),
        )

    def validate_cold_start_bundle(
        self,
        root_dir: str | Path,
        manifest_name: str = "manifest.json",
        *,
        required_mounts: tuple[str, ...] = COLD_START_REQUIRED_MOUNTS,
    ) -> MountTableBootReport:
        report = self.boot(root_dir, manifest_name=manifest_name, strict=True)
        report.assert_cold_start_ready(required_mounts)
        return report

    def _verify_artifact(
        self,
        root: Path,
        relative_path: str,
        mount_path: str,
        manifest_item: dict[str, Any],
    ) -> MountIntegrityReport:
        path = root / relative_path
        expected_size = manifest_item.get("size")
        expected_sha = manifest_item.get("sha256")

        if not path.exists():
            return MountIntegrityReport(
                relative_path=relative_path,
                mount_path=mount_path,
                exists=False,
                size_ok=False,
                sha256_ok=False,
                expected_size=expected_size,
                actual_size=None,
                expected_sha256=expected_sha,
                actual_sha256=None,
            )

        actual_size = path.stat().st_size
        actual_sha = self._sha256_file(path)
        return MountIntegrityReport(
            relative_path=relative_path,
            mount_path=mount_path,
            exists=True,
            size_ok=expected_size is None or actual_size == expected_size,
            sha256_ok=expected_sha is None or actual_sha == expected_sha,
            expected_size=expected_size,
            actual_size=actual_size,
            expected_sha256=expected_sha,
            actual_sha256=actual_sha,
        )

    @staticmethod
    def _partition_id(relative_path: str) -> str:
        return "kc_" + relative_path.replace("/", "_").replace(".", "_")

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


__all__ = [
    "COLD_START_REQUIRED_MOUNTS",
    "DEFAULT_MOUNT_SPECS",
    "KnowledgeCloudMountTable",
    "MountIntegrityReport",
    "MountTableBootReport",
]
