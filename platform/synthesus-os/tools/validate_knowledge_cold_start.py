#!/usr/bin/env python3
"""Validate a Knowledge Cloud artifact bundle as cold-start CHAL hardware."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
if str(PACKAGES) not in sys.path:
    sys.path.insert(0, str(PACKAGES))

from knowledge.mount_table import (
    COLD_START_REQUIRED_MOUNTS,
    KnowledgeCloudMountTable,
    MountTableBootReport,
)


def _default_root() -> Path:
    configured = os.environ.get("SYNTHESUS_KNOWLEDGE_ROOT")
    if configured:
        return Path(configured)
    companion_artifacts = ROOT.parent / "synthesus-knowledge-cloud" / "artifacts"
    if companion_artifacts.exists():
        return companion_artifacts
    return ROOT / "data"


def _cold_start_summary(report: MountTableBootReport) -> dict:
    retrieval_semantics = (
        report.retrieval_semantics.as_metadata()
        if report.retrieval_semantics is not None
        else None
    )
    source_manifest_provenance = (
        report.source_manifest_provenance.as_metadata()
        if report.source_manifest_provenance is not None
        else None
    )
    return {
        "schema": "synthesus.knowledge_cold_start.summary.v1",
        "ok": report.ok,
        "manifest": report.manifest_path,
        "manifest_version": report.manifest_version,
        "active_mounts": list(report.active_mount_paths),
        "missing_required_mounts": list(report.missing_active_mounts(COLD_START_REQUIRED_MOUNTS)),
        "integrity_failures": [
            item.as_metadata() for item in report.integrity if not item.ok
        ],
        "retrieval_semantics": retrieval_semantics,
        "source_manifest_provenance": source_manifest_provenance,
    }


def _validate_report(root: Path) -> MountTableBootReport:
    table = KnowledgeCloudMountTable()
    report = table.boot(root, strict=True)
    return MountTableBootReport(
        manifest_path=report.manifest_path,
        manifest_version=report.manifest_version,
        mounts=report.mounts,
        integrity=report.integrity,
        coverage=report.coverage,
        retrieval_semantics=table.validate_retrieval_semantics(root),
        source_manifest_provenance=table.validate_source_manifest_provenance(root),
    )


def validate(root: Path) -> int:
    report = _validate_report(root)
    print("cold_start_summary=" + json.dumps(_cold_start_summary(report), sort_keys=True))
    report.assert_cold_start_ready(COLD_START_REQUIRED_MOUNTS)
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
