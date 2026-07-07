"""Fast Knowledge Cloud hardware health check for Synthesus 5."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = REPO_ROOT.parent / "synthesus-knowledge-cloud" / "artifacts"

GOLDEN_QUERIES = [
    "What is the capital of France?",
    "Who wrote the theory of relativity?",
    "What is the largest planet in our solar system?",
    "Who is the main character in the Great Gatsby?",
    "What is the chemical symbol for gold?",
]

LATENCY_THRESHOLD_MS = 100.0

logger = logging.getLogger("knowledge_health_check")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_items(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["path"].replace("\\", "/"): item for item in manifest.get("artifacts", [])}


def _verify_manifest_hashes(artifact_root: Path) -> list[str]:
    manifest_path = artifact_root / "manifest.json"
    if not manifest_path.exists():
        return [f"missing manifest.json under {artifact_root}"]

    manifest = _load_json(manifest_path)
    errors: list[str] = []
    for rel_path, item in _manifest_items(manifest).items():
        path = artifact_root / rel_path
        if not path.exists():
            errors.append(f"missing artifact {rel_path}")
            continue
        if path.stat().st_size != int(item["size"]):
            errors.append(f"size mismatch {rel_path}: expected {item['size']}, got {path.stat().st_size}")
            continue
        if _sha256_file(path) != item["sha256"]:
            errors.append(f"sha256 mismatch {rel_path}")
    return errors


def _metadata_count(artifact_root: Path) -> int:
    metadata_path = artifact_root / "faiss_metadata.json"
    if metadata_path.exists():
        metadata = _load_json(metadata_path)
        if isinstance(metadata, list):
            return len(metadata)
        if isinstance(metadata, dict):
            return len(metadata)

    sqlite_path = artifact_root / "knowledge.kndb.meta.db"
    if sqlite_path.exists():
        with sqlite3.connect(sqlite_path) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0])
    return 0


def _load_metadata_records(artifact_root: Path) -> list[dict[str, Any]]:
    metadata = _load_json(artifact_root / "faiss_metadata.json")
    if not isinstance(metadata, list):
        raise ValueError("faiss_metadata.json must be a list for golden-query search")
    return metadata


def _load_embedder(artifact_root: Path):
    packages_root = REPO_ROOT / "packages"
    for path in (packages_root, packages_root / "knowledge"):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)

    from knowledge.swarm_embedder import SwarmEmbedder

    return SwarmEmbedder(model_dir=artifact_root / "models")


def _validate_retrieval_semantics(artifact_root: Path) -> tuple[bool, list[str]]:
    packages_root = REPO_ROOT / "packages"
    for path in (packages_root, packages_root / "knowledge", packages_root / "core"):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)

    try:
        from knowledge.mount_table import KnowledgeCloudMountTable
    except Exception as exc:
        return False, [f"retrieval semantic validator import failed: {exc}"]

    report = KnowledgeCloudMountTable().validate_retrieval_semantics(artifact_root)
    return report.ok, list(report.errors)


def _run_golden_queries(artifact_root: Path, top_k: int = 5) -> tuple[list[float], list[str]]:
    import faiss

    index = faiss.read_index(str(artifact_root / "faiss.index"))
    metadata = _load_metadata_records(artifact_root)
    embedder = _load_embedder(artifact_root)
    errors: list[str] = []
    latencies: list[float] = []

    for query in GOLDEN_QUERIES:
        start = time.perf_counter()
        vector = embedder.embed_texts([query]).astype(np.float32)
        if index.d != vector.shape[1]:
            errors.append(f"dimension mismatch for {query!r}: index {index.d}, embedder {vector.shape[1]}")
            continue
        scores, indices = index.search(vector, top_k)
        latency_ms = (time.perf_counter() - start) * 1000.0
        latencies.append(latency_ms)
        hits = [idx for idx in indices[0] if 0 <= idx < len(metadata)]
        if not hits:
            errors.append(f"empty metadata-backed results for golden query: {query}")
        elif not any(float(score) > 0 for score in scores[0]):
            errors.append(f"non-positive scores for golden query: {query}")
    return latencies, errors


def _check_kal_mounts() -> tuple[int, list[str]]:
    packages_root = REPO_ROOT / "packages"
    for path in (packages_root, packages_root / "knowledge", packages_root / "core"):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)

    try:
        from knowledge.kal_adapter import CHALMemoryController
    except Exception as exc:
        return 0, [f"KAL import failed: {exc}"]

    try:
        controller = CHALMemoryController()
        mounts = controller.get_mounts()
    except Exception as exc:
        return 0, [f"KAL mount initialization failed: {exc}"]

    required = {"ROM", "PARAMETER_DISK", "GROUNDING_CORPUS", "WRITEBACK_MEMORY"}
    observed = {mount.mount_type.value for mount in mounts}
    missing = sorted(required - observed)
    errors = [f"missing KAL mount type {item}" for item in missing]
    return len(mounts), errors


def run_health_check(
    artifact_root: str | Path = DEFAULT_ARTIFACT_ROOT,
    *,
    latency_threshold_ms: float = LATENCY_THRESHOLD_MS,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    artifact_root = Path(artifact_root).resolve()
    errors: list[str] = []

    start = time.perf_counter()
    errors.extend(_verify_manifest_hashes(artifact_root))

    faiss_total = 0
    try:
        import faiss

        index = faiss.read_index(str(artifact_root / "faiss.index"))
        faiss_total = int(index.ntotal)
    except Exception as exc:
        errors.append(f"FAISS load failed: {exc}")

    metadata_total = 0
    try:
        metadata_total = _metadata_count(artifact_root)
        if faiss_total and metadata_total != faiss_total:
            errors.append(f"FAISS/metadata count mismatch: faiss={faiss_total}, metadata={metadata_total}")
    except Exception as exc:
        errors.append(f"metadata validation failed: {exc}")

    retrieval_semantics_ok = False
    try:
        retrieval_semantics_ok, semantic_errors = _validate_retrieval_semantics(artifact_root)
        errors.extend(semantic_errors)
    except Exception as exc:
        errors.append(f"retrieval semantic validation failed: {exc}")

    latencies: list[float] = []
    if faiss_total and retrieval_semantics_ok:
        try:
            latencies, golden_errors = _run_golden_queries(artifact_root)
            errors.extend(golden_errors)
        except Exception as exc:
            errors.append(f"golden query validation failed: {exc}")

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    if latencies and avg_latency > latency_threshold_ms:
        errors.append(f"golden query latency exceeded threshold: {avg_latency:.2f}ms > {latency_threshold_ms:.2f}ms")

    mount_count, mount_errors = _check_kal_mounts()
    errors.extend(mount_errors)

    report = {
        "status": "PASS" if not errors else "FAIL",
        "artifact_root": str(artifact_root),
        "errors": errors,
        "stats": {
            "faiss_vectors": faiss_total,
            "metadata_records": metadata_total,
            "kal_mounts": mount_count,
            "avg_golden_query_latency_ms": avg_latency,
            "duration_ms": (time.perf_counter() - start) * 1000.0,
        },
    }

    output_path = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "synthesus_knowledge_health_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    logger.info("wrote health report to %s", output_path)
    if errors:
        logger.error("Knowledge health check failed: %s", errors)
    else:
        logger.info("Knowledge health check passed")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a fast Synthesus Knowledge Cloud hardware health check")
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    parser.add_argument("--latency-threshold-ms", type=float, default=LATENCY_THRESHOLD_MS)
    parser.add_argument("--report-path", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    report = run_health_check(
        args.artifact_root,
        latency_threshold_ms=args.latency_threshold_ms,
        report_path=args.report_path,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
