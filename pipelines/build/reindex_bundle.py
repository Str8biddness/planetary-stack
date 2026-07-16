#!/usr/bin/env python3
"""Rebuild a FAISS index from existing vector-aligned metadata and embedder."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from synthesus_knowledge_cloud.json_stream import iter_json_array


QUERY_FIELDS = ("pattern", "question", "prompt", "query", "instruction")
FALLBACK_FIELDS = ("response", "answer", "text", "content")


def record_to_text(record: Any) -> str:
    """Select the query-side text used by the runtime retrieval contract."""
    if not isinstance(record, dict):
        return str(record)
    for field in (*QUERY_FIELDS, *FALLBACK_FIELDS):
        value = record.get(field)
        if value is not None and str(value).strip():
            return str(value)
    return " "


def rebuild_index(
    metadata_path: str | Path,
    embedder_path: str | Path,
    output_path: str | Path,
    *,
    batch_size: int = 2048,
    expected_count: int | None = None,
) -> tuple[int, int]:
    """Build an atomic IndexFlatIP artifact compatible with the persisted model."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    import faiss
    import joblib
    import numpy as np

    model = joblib.load(embedder_path)
    if not isinstance(model, dict) or not {"tfidf", "svd", "dim"}.issubset(model):
        raise ValueError("embedder must contain tfidf, svd, and dim")
    dimension = int(model["dim"])
    tfidf = model["tfidf"]
    svd = model["svd"]
    index = faiss.IndexFlatIP(dimension)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.unlink(missing_ok=True)

    texts: list[str] = []
    count = 0

    def flush() -> None:
        nonlocal count
        if not texts:
            return
        sparse = tfidf.transform(texts)
        dense = svd.transform(sparse).astype(np.float32)
        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        dense /= np.where(norms == 0, 1.0, norms)
        vectors = np.ascontiguousarray(dense, dtype=np.float32)
        if vectors.shape[1] != dimension:
            raise ValueError(
                f"embedder produced {vectors.shape[1]} dimensions; expected {dimension}"
            )
        index.add(vectors)
        count += len(texts)
        texts.clear()

    try:
        for record in iter_json_array(metadata_path):
            texts.append(record_to_text(record))
            if len(texts) >= batch_size:
                flush()
                if count % 50_000 < batch_size:
                    print(f"indexed {count:,} records", flush=True)
        flush()
        if expected_count is not None and count != expected_count:
            raise ValueError(f"metadata count mismatch: expected {expected_count}, got {count}")
        faiss.write_index(index, str(temporary))
        os.replace(temporary, output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    return count, dimension


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--embedder", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--expected-count", type=int)
    args = parser.parse_args(argv)
    count, dimension = rebuild_index(
        args.metadata,
        args.embedder,
        args.output,
        batch_size=args.batch_size,
        expected_count=args.expected_count,
    )
    print(f"wrote {args.output}: vectors={count:,}, dim={dimension}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
