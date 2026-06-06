#!/usr/bin/env python3
"""Validate a Knowledge Cloud artifact bundle as cold-start CHAL hardware."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
if str(PACKAGES) not in sys.path:
    sys.path.insert(0, str(PACKAGES))

from knowledge.mount_table import COLD_START_REQUIRED_MOUNTS, KnowledgeCloudMountTable


def _default_root() -> Path:
    configured = os.environ.get("SYNTHESUS_KNOWLEDGE_ROOT")
    if configured:
        return Path(configured)
    companion_artifacts = ROOT.parent / "synthesus-knowledge-cloud" / "artifacts"
    if companion_artifacts.exists():
        return companion_artifacts
    return ROOT / "data"


def validate(root: Path) -> int:
    report = KnowledgeCloudMountTable().validate_cold_start_bundle(
        root,
        validate_retrieval_semantics=True,
        validate_source_manifest_provenance=True,
    )
    print(f"Knowledge Cloud cold-start bundle OK: {root}")
    print(f"manifest={report.manifest_path} version={report.manifest_version or 'unknown'}")
    print(f"active_mounts={len(report.active_mount_paths)} checked_artifacts={len(report.integrity)}")
    if report.retrieval_semantics is not None:
        metadata = report.retrieval_semantics.as_metadata()
        print(
            "retrieval_semantics="
            f"faiss_vectors={metadata['faiss_vectors']} "
            f"metadata_records={metadata['metadata_records']} "
            f"faiss_dim={metadata['faiss_dim']} "
            f"embedder_dim={metadata['embedder_dim']}"
        )
    if report.source_manifest_provenance is not None:
        metadata = report.source_manifest_provenance.as_metadata()
        print(
            "source_manifest="
            f"path={metadata['path']} "
            f"sha256={metadata['sha256']} "
            f"artifacts={metadata['artifact_count']}"
        )
    for mount_path in COLD_START_REQUIRED_MOUNTS:
        print(f"mounted {mount_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a local Knowledge Cloud artifact bundle can boot as Synthesus 5 "
            "CHAL-mounted hardware from a cold start."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_default_root(),
        help="Artifact bundle root containing manifest.json.",
    )
    args = parser.parse_args()

    try:
        return validate(args.root)
    except Exception as exc:
        print(f"Knowledge Cloud cold-start validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
