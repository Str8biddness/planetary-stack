#!/usr/bin/env python3
"""Ingest YOUR documents into the local Synthesus grounding index.

Usage:
    python tools/ingest_docs.py <file_or_folder> [more...]

Reads .txt/.md files, chunks + embeds them locally (nothing leaves the machine),
and APPENDS to data/user_faiss.index (the index the runtime grounds on). Then run
the runtime and ask about your content — it answers from your docs; raw Llama can't.

Override the index location with SYNTHESUS_RAG_INDEX / SYNTHESUS_RAG_METADATA
(must match what the runtime uses).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))               # ml.swarm_embedder
sys.path.insert(0, str(ROOT / "packages"))  # knowledge.rag_pipeline

from knowledge.rag_pipeline import RAGPipeline  # noqa: E402


def main(argv):
    if not argv:
        print("usage: ingest_docs.py <file_or_folder> [...]")
        return 2
    index = os.environ.get("SYNTHESUS_RAG_INDEX", str(ROOT / "data" / "user_faiss.index"))
    meta = os.environ.get("SYNTHESUS_RAG_METADATA", str(ROOT / "data" / "user_meta.json"))
    rag = RAGPipeline(index_path=index, metadata_path=meta, top_k=5, score_threshold=0.2)
    before = rag.total_vectors
    added = rag.ingest_documents(argv, save=True)
    print(f"Ingested {added} chunk(s). Index: {before} -> {rag.total_vectors} vectors")
    print(f"Saved to: {index}")
    print("Now run the runtime (it reads this index) and ask about your documents.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
