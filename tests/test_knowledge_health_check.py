from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from knowledge.health_check import run_health_check


def _record_artifact(root: Path, relative_path: str) -> dict:
    path = root / relative_path
    content = path.read_bytes()
    return {
        "path": relative_path,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _write_artifact(root: Path, relative_path: str, content: bytes) -> dict:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return _record_artifact(root, relative_path)


def test_health_check_reports_semantic_mismatch_before_golden_queries(
    tmp_path: Path,
    monkeypatch,
):
    import faiss
    import joblib

    artifacts = [
        _write_artifact(tmp_path, "knowledge_cloud/world_lore.json", b'{"lore": []}\n'),
        _write_artifact(tmp_path, "knowledge_cloud/transitions.json", b'{"edges": []}\n'),
        _write_artifact(tmp_path, "knowledge_cloud/chaining_patterns.json", b'{"patterns": []}\n'),
        _write_artifact(tmp_path, "knowledge_cloud/learned_transitions.json", b'{"learned": []}\n'),
        _write_artifact(tmp_path, "knowledge.kndb", b"kndb"),
        _write_artifact(tmp_path, "knowledge.kndb.meta.db", b"kndb-meta"),
        _write_artifact(tmp_path, "knowledge.meta.db", b"knowledge-meta"),
    ]

    model_path = tmp_path / "models" / "swarm_embedder.pkl"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"dim": 2}, model_path)

    index = faiss.IndexFlatIP(3)
    index.add(np.zeros((2, 3), dtype=np.float32))
    faiss.write_index(index, str(tmp_path / "faiss.index"))

    (tmp_path / "faiss_metadata.json").write_text(
        json.dumps([{"id": "one"}, {"id": "two"}]),
        encoding="utf-8",
    )

    artifacts.extend(
        [
            _record_artifact(tmp_path, "models/swarm_embedder.pkl"),
            _record_artifact(tmp_path, "faiss.index"),
            _record_artifact(tmp_path, "faiss_metadata.json"),
        ]
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"version": "1", "artifacts": artifacts}),
        encoding="utf-8",
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("golden queries should be skipped when retrieval semantics fail")

    monkeypatch.setattr("knowledge.health_check._run_golden_queries", fail_if_called)
    monkeypatch.setattr("knowledge.health_check._check_kal_mounts", lambda: (4, []))

    report = run_health_check(tmp_path, report_path=tmp_path / "report.json")

    assert report["status"] == "FAIL"
    assert report["errors"] == ["FAISS/embedder dim mismatch: faiss=3, embedder=2"]
    assert report["stats"]["faiss_vectors"] == 2
    assert report["stats"]["metadata_records"] == 2
