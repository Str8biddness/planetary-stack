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
    "knowledge_cloud/learned_transitions.json": (
        "/mnt/params/learned_transitions",
        MountType.PARAMETER_DISK,
        "learned_transition_priors",
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
    "knowledge.meta.db": (
        "/mnt/provenance/knowledge_metadata",
        MountType.SOURCE_PROVENANCE,
        "source_provenance",
        True,
        "local",
    ),
}

VOLATILE_MOUNT_SPECS: tuple[tuple[str, MountType, str, bool, str, str], ...] = (
    (
        "/mnt/cache/hot_context",
        MountType.CACHE_SEED,
        "hot_context_cache",
        False,
        "local",
        "volatile L1 hot-context cache; never source-controlled",
    ),
    (
        "/mnt/mem/writeback",
        MountType.WRITEBACK_MEMORY,
        "memory_writeback",
        False,
        "local",
        "volatile episodic/crystallized writeback boundary; never source-controlled",
    ),
)

COLD_START_REQUIRED_MOUNTS: tuple[str, ...] = (
    "/mnt/rom/world_lore",
    "/mnt/params/transitions",
    "/mnt/params/chaining_patterns",
    "/mnt/params/learned_transitions",
    "/mnt/params/swarm_embedder",
    "/mnt/corpus/faiss",
    "/mnt/provenance/faiss_metadata",
    "/mnt/rom/knowledge_nodes",
    "/mnt/provenance/kndb_metadata",
    "/mnt/provenance/knowledge_metadata",
    "/mnt/cache/hot_context",
    "/mnt/mem/writeback",
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
class RetrievalSemanticReport:
    faiss_vectors: int | None
    faiss_dim: int | None
    metadata_records: int | None
    embedder_dim: int | None
    profile_embedder_dim: int | None = None
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_metadata(self) -> dict[str, Any]:
        return {
            "faiss_vectors": self.faiss_vectors,
            "faiss_dim": self.faiss_dim,
            "metadata_records": self.metadata_records,
            "embedder_dim": self.embedder_dim,
            "profile_embedder_dim": self.profile_embedder_dim,
            "semantic_integrity_ok": self.ok,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class SourceManifestProvenanceReport:
    path: str | None
    sha256: str | None
    size: int | None
    kind: str | None
    artifact_count: int | None
    roots: tuple[str, ...]
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_metadata(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size": self.size,
            "kind": self.kind,
            "artifact_count": self.artifact_count,
            "roots": list(self.roots),
            "source_manifest_provenance_ok": self.ok,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class ManifestCoverageReport:
    expected_artifacts: tuple[str, ...]
    mounted_artifacts: tuple[str, ...]
    missing_artifacts: tuple[str, ...]
    missing_mount_paths: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing_artifacts

    def as_metadata(self) -> dict[str, Any]:
        return {
            "expected_artifacts": list(self.expected_artifacts),
            "mounted_artifacts": list(self.mounted_artifacts),
            "missing_artifacts": list(self.missing_artifacts),
            "missing_mount_paths": list(self.missing_mount_paths),
            "coverage_complete": self.complete,
        }


@dataclass(frozen=True)
class MountTableBootReport:
    manifest_path: str
    manifest_version: str | None
    mounts: tuple[Mount, ...]
    integrity: tuple[MountIntegrityReport, ...]
    coverage: ManifestCoverageReport | None = None
    retrieval_semantics: RetrievalSemanticReport | None = None
    source_manifest_provenance: SourceManifestProvenanceReport | None = None

    @property
    def ok(self) -> bool:
        semantic_ok = self.retrieval_semantics is None or self.retrieval_semantics.ok
        provenance_ok = (
            self.source_manifest_provenance is None
            or self.source_manifest_provenance.ok
        )
        return all(report.ok for report in self.integrity) and semantic_ok and provenance_ok

    @property
    def active_mount_paths(self) -> tuple[str, ...]:
        return tuple(mount.mount_path for mount in self.mounts if mount.is_active)

    def missing_active_mounts(self, required_mounts: tuple[str, ...]) -> tuple[str, ...]:
        active = set(self.active_mount_paths)
        return tuple(mount_path for mount_path in required_mounts if mount_path not in active)

    @property
    def missing_known_mount_paths(self) -> tuple[str, ...]:
        if self.coverage is None:
            return ()
        return self.coverage.missing_mount_paths

    def assert_cold_start_ready(
        self,
        required_mounts: tuple[str, ...] = COLD_START_REQUIRED_MOUNTS,
    ) -> None:
        if not all(report.ok for report in self.integrity):
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
        runtime_errors: list[str] = []
        if self.retrieval_semantics is not None and not self.retrieval_semantics.ok:
            runtime_errors.append(
                "retrieval semantic integrity failed: "
                + "; ".join(self.retrieval_semantics.errors)
            )
        if (
            self.source_manifest_provenance is not None
            and not self.source_manifest_provenance.ok
        ):
            runtime_errors.append(
                "source-manifest provenance failed: "
                + "; ".join(self.source_manifest_provenance.errors)
            )
        if runtime_errors:
            raise ValueError(
                "Knowledge Cloud cold-start runtime validation failed: "
                + " | ".join(runtime_errors)
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
        source_manifest_metadata = self._source_manifest_provenance_metadata(manifest)

        mounts: list[Mount] = []
        reports: list[MountIntegrityReport] = []
        mounted_artifacts: set[str] = set()

        for item in manifest.get("artifacts", []):
            relative_path = str(item.get("path", "")).replace("\\", "/")
            spec = self._artifact_specs.get(relative_path)
            if not relative_path or spec is None:
                continue
            if relative_path in mounted_artifacts:
                if strict:
                    raise ValueError(
                        f"Duplicate Knowledge Cloud artifact mount entry: {relative_path}"
                    )
                continue

            mount_path, mount_type, namespace, read_only, locality = spec
            report = self._verify_artifact(root, relative_path, mount_path, item)
            reports.append(report)
            mounted_artifacts.add(relative_path)
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
                        metadata=self._mount_metadata(
                            report,
                            source_manifest_metadata,
                        ),
                    ),
                    locality=locality,
                    trust_level=1.0 if report.ok else 0.0,
                    latency_profile="fast" if locality == "local" else "medium",
                    is_active=report.ok,
                )
            )

        mounts.extend(self._volatile_mounts())

        return MountTableBootReport(
            manifest_path=str(manifest_path),
            manifest_version=str(manifest.get("version")) if manifest.get("version") is not None else None,
            mounts=tuple(mounts),
            integrity=tuple(reports),
            coverage=self._coverage_report(mounted_artifacts),
        )

    def validate_cold_start_bundle(
        self,
        root_dir: str | Path,
        manifest_name: str = "manifest.json",
        *,
        required_mounts: tuple[str, ...] = COLD_START_REQUIRED_MOUNTS,
        validate_retrieval_semantics: bool = False,
        validate_source_manifest_provenance: bool = False,
    ) -> MountTableBootReport:
        report = self.boot(root_dir, manifest_name=manifest_name, strict=True)
        retrieval_semantics = None
        source_manifest_provenance = None
        if validate_retrieval_semantics:
            retrieval_semantics = self.validate_retrieval_semantics(root_dir)
        if validate_source_manifest_provenance:
            source_manifest_provenance = self.validate_source_manifest_provenance(root_dir)
        if retrieval_semantics is not None or source_manifest_provenance is not None:
            report = MountTableBootReport(
                manifest_path=report.manifest_path,
                manifest_version=report.manifest_version,
                mounts=report.mounts,
                integrity=report.integrity,
                coverage=report.coverage,
                retrieval_semantics=retrieval_semantics,
                source_manifest_provenance=source_manifest_provenance,
            )
        report.assert_cold_start_ready(required_mounts)
        return report

    def validate_source_manifest_provenance(
        self,
        root_dir: str | Path,
        manifest_name: str = "manifest.json",
    ) -> SourceManifestProvenanceReport:
        """Verify artifact manifest provenance points at a source-plane manifest."""
        root = Path(root_dir)
        errors: list[str] = []
        path: str | None = None
        sha256: str | None = None
        size: int | None = None
        kind: str | None = None
        artifact_count: int | None = None
        roots: tuple[str, ...] = ()

        try:
            manifest = json.loads((root / manifest_name).read_text(encoding="utf-8"))
        except Exception as exc:
            return SourceManifestProvenanceReport(
                path=None,
                sha256=None,
                size=None,
                kind=None,
                artifact_count=None,
                roots=(),
                errors=(f"Knowledge Cloud manifest load failed: {exc}",),
            )

        source_manifest = manifest.get("build", {}).get("source_manifest")
        if not isinstance(source_manifest, dict):
            return SourceManifestProvenanceReport(
                path=None,
                sha256=None,
                size=None,
                kind=None,
                artifact_count=None,
                roots=(),
                errors=("manifest build.source_manifest fingerprint is missing",),
            )

        return self._source_manifest_provenance_report(source_manifest)

    @staticmethod
    def _source_manifest_provenance_report(
        source_manifest: dict[str, Any],
    ) -> SourceManifestProvenanceReport:
        errors: list[str] = []
        path: str | None = None
        sha256: str | None = None
        size: int | None = None
        kind: str | None = None
        artifact_count: int | None = None
        roots: tuple[str, ...] = ()

        path_value = source_manifest.get("path")
        sha_value = source_manifest.get("sha256")
        size_value = source_manifest.get("size")
        kind_value = source_manifest.get("kind")
        artifact_count_value = source_manifest.get("artifact_count")
        roots_value = source_manifest.get("roots")

        path = str(path_value) if path_value is not None else None
        sha256 = str(sha_value) if sha_value is not None else None
        kind = str(kind_value) if kind_value is not None else None
        if isinstance(size_value, int):
            size = size_value
        if isinstance(artifact_count_value, int):
            artifact_count = artifact_count_value
        if isinstance(roots_value, list):
            roots = tuple(str(root) for root in roots_value)

        if path != "manifests/source_manifest.json":
            errors.append("manifest build.source_manifest.path must be manifests/source_manifest.json")
        if sha256 is None or len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256.lower()):
            errors.append("manifest build.source_manifest.sha256 must be a 64-character hex digest")
        if size is None or size <= 0:
            errors.append("manifest build.source_manifest.size must be a positive integer")
        if kind != "synthesus-knowledge-source-plane":
            errors.append("manifest build.source_manifest.kind must be synthesus-knowledge-source-plane")
        if artifact_count is None or artifact_count <= 0:
            errors.append("manifest build.source_manifest.artifact_count must be a positive integer")
        if not roots:
            errors.append("manifest build.source_manifest.roots must be a non-empty list")

        return SourceManifestProvenanceReport(
            path=path,
            sha256=sha256,
            size=size,
            kind=kind,
            artifact_count=artifact_count,
            roots=roots,
            errors=tuple(errors),
        )

    def _source_manifest_provenance_metadata(
        self,
        manifest: dict[str, Any],
    ) -> dict[str, Any] | None:
        source_manifest = manifest.get("build", {}).get("source_manifest")
        if not isinstance(source_manifest, dict):
            return None
        return self._source_manifest_provenance_report(source_manifest).as_metadata()

    def validate_retrieval_semantics(self, root_dir: str | Path) -> RetrievalSemanticReport:
        """Verify mounted FAISS, metadata, and embedder artifacts can work together."""
        root = Path(root_dir)
        errors: list[str] = []
        faiss_vectors: int | None = None
        faiss_dim: int | None = None
        metadata_records: int | None = None
        embedder_dim: int | None = None
        profile_embedder_dim: int | None = None

        try:
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            declared_dim = (
                manifest.get("build", {})
                .get("extra", {})
                .get("embed_dim")
            )
            if declared_dim is not None:
                profile_embedder_dim = int(declared_dim)
        except Exception as exc:
            errors.append(f"Knowledge Cloud manifest profile load failed: {exc}")

        try:
            import faiss  # type: ignore

            index = faiss.read_index(str(root / "faiss.index"))
            faiss_vectors = int(index.ntotal)
            faiss_dim = int(index.d)
        except Exception as exc:
            errors.append(f"FAISS load failed: {exc}")

        try:
            metadata = json.loads((root / "faiss_metadata.json").read_text(encoding="utf-8"))
            if isinstance(metadata, list):
                metadata_records = len(metadata)
            elif isinstance(metadata, dict):
                metadata_records = len(metadata)
            else:
                errors.append("faiss_metadata.json must be a list or object")
        except Exception as exc:
            errors.append(f"FAISS metadata load failed: {exc}")

        try:
            import joblib  # type: ignore

            embedder = joblib.load(root / "models" / "swarm_embedder.pkl")
            if isinstance(embedder, dict):
                embedder_dim = int(embedder["dim"])
            else:
                dim = getattr(embedder, "dim", None)
                if dim is None:
                    errors.append("swarm_embedder.pkl has no dim field")
                else:
                    embedder_dim = int(dim)
        except Exception as exc:
            errors.append(f"Swarm embedder load failed: {exc}")

        if faiss_vectors is not None and metadata_records is not None and faiss_vectors != metadata_records:
            errors.append(
                f"FAISS/metadata count mismatch: faiss={faiss_vectors}, metadata={metadata_records}"
            )
        if faiss_dim is not None and embedder_dim is not None and faiss_dim != embedder_dim:
            errors.append(f"FAISS/embedder dim mismatch: faiss={faiss_dim}, embedder={embedder_dim}")
        if (
            faiss_dim is not None
            and profile_embedder_dim is not None
            and faiss_dim != profile_embedder_dim
        ):
            errors.append(
                "FAISS/profile dim mismatch: "
                f"faiss={faiss_dim}, profile={profile_embedder_dim}"
            )
        if (
            embedder_dim is not None
            and profile_embedder_dim is not None
            and embedder_dim != profile_embedder_dim
        ):
            errors.append(
                "Embedder/profile dim mismatch: "
                f"embedder={embedder_dim}, profile={profile_embedder_dim}"
            )

        return RetrievalSemanticReport(
            faiss_vectors=faiss_vectors,
            faiss_dim=faiss_dim,
            metadata_records=metadata_records,
            embedder_dim=embedder_dim,
            profile_embedder_dim=profile_embedder_dim,
            errors=tuple(errors),
        )

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
    def _mount_metadata(
        report: MountIntegrityReport,
        source_manifest_metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        metadata = report.as_metadata()
        if source_manifest_metadata is not None:
            if source_manifest_metadata.get("source_manifest_provenance_ok") is True:
                metadata["source_manifest_provenance"] = source_manifest_metadata
            else:
                metadata["source_manifest_provenance_ok"] = False
                metadata["source_manifest_provenance_errors"] = list(
                    source_manifest_metadata.get("errors", [])
                )
        return metadata

    @staticmethod
    def _partition_id(relative_path: str) -> str:
        return "kc_" + relative_path.replace("/", "_").replace(".", "_")

    def _coverage_report(self, mounted_artifacts: set[str]) -> ManifestCoverageReport:
        expected = tuple(sorted(self._artifact_specs))
        mounted = tuple(sorted(mounted_artifacts))
        missing = tuple(path for path in expected if path not in mounted_artifacts)
        missing_mount_paths = tuple(self._artifact_specs[path][0] for path in missing)
        return ManifestCoverageReport(
            expected_artifacts=expected,
            mounted_artifacts=mounted,
            missing_artifacts=missing,
            missing_mount_paths=missing_mount_paths,
        )

    @staticmethod
    def _volatile_mounts() -> list[Mount]:
        mounts: list[Mount] = []
        for mount_path, mount_type, namespace, read_only, locality, description in VOLATILE_MOUNT_SPECS:
            mounts.append(
                Mount(
                    mount_path=mount_path,
                    mount_type=mount_type,
                    partition=Partition(
                        partition_id="kc_" + mount_path.strip("/").replace("/", "_"),
                        namespace=namespace,
                        is_read_only=read_only,
                        metadata={
                            "relative_path": None,
                            "integrity_ok": True,
                            "volatile": True,
                            "artifact_backed": False,
                            "description": description,
                        },
                    ),
                    locality=locality,
                    trust_level=1.0,
                    latency_profile="fast",
                    is_active=True,
                )
            )
        return mounts

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
    "ManifestCoverageReport",
    "MountIntegrityReport",
    "MountTableBootReport",
    "RetrievalSemanticReport",
    "SourceManifestProvenanceReport",
    "VOLATILE_MOUNT_SPECS",
]
