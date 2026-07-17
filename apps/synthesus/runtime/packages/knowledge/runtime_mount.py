"""Runtime discovery and validation for mounted Knowledge Cloud artifacts."""

from __future__ import annotations

import os
from pathlib import Path

from knowledge.mount_table import KnowledgeCloudMountTable, MountTableBootReport


def knowledge_root_candidates(
    runtime_root: str | Path,
    *,
    configured_root: str | Path | None = None,
) -> tuple[Path, ...]:
    """Return Knowledge Cloud artifact roots in deterministic priority order."""
    configured = configured_root
    if configured is None:
        configured = os.environ.get("SYNTHESUS_KNOWLEDGE_ROOT")
    if configured:
        return (Path(configured).expanduser().resolve(),)

    runtime = Path(runtime_root).resolve()
    candidates = [
        runtime.parents[2] / "knowledge" / "knowledge-cloud" / "artifacts",
        runtime.parent.parent / "synthesus-knowledge-cloud" / "artifacts",
        runtime.parent / "synthesus-knowledge-cloud" / "artifacts",
        runtime / "data",
    ]

    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def resolve_knowledge_root(
    runtime_root: str | Path,
    *,
    configured_root: str | Path | None = None,
    required: bool = False,
) -> Path | None:
    """Resolve the first artifact root containing a versioned manifest."""
    candidates = knowledge_root_candidates(
        runtime_root,
        configured_root=configured_root,
    )
    explicit = configured_root is not None or bool(
        os.environ.get("SYNTHESUS_KNOWLEDGE_ROOT")
    )

    for candidate in candidates:
        if (candidate / "manifest.json").is_file():
            return candidate

    searched = ", ".join(str(candidate) for candidate in candidates)
    if explicit or required:
        raise FileNotFoundError(
            "Knowledge Cloud manifest.json was not found; searched: " + searched
        )
    return None


def validate_runtime_knowledge_root(
    artifact_root: str | Path,
) -> MountTableBootReport:
    """Run the full runtime admission gate and return its reusable boot report."""
    return KnowledgeCloudMountTable().validate_cold_start_bundle(
        artifact_root,
        validate_retrieval_semantics=True,
        validate_source_manifest_provenance=True,
    )


__all__ = [
    "knowledge_root_candidates",
    "resolve_knowledge_root",
    "validate_runtime_knowledge_root",
]
