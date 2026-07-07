#!/usr/bin/env python3
"""Ingest a GitHub repo into your Synthesus grounding index (expansion drive: GitHub).

Usage:
    python tools/ingest_github.py <owner/repo | git-url | local-path> [--token T] [--ref BRANCH]

Pulls the repo's source + doc files and grounds Synthesus on YOUR code. The repo
is fetched from your GitHub; embedding + indexing stay local (private). For a
private repo pass --token or set GITHUB_TOKEN.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))               # ml.swarm_embedder
sys.path.insert(0, str(ROOT / "packages"))  # knowledge.*

from knowledge.rag_pipeline import RAGPipeline  # noqa: E402
from knowledge.connectors.github_connector import ingest_github_repo  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Ingest a GitHub repo into the Synthesus grounding index.")
    ap.add_argument("repo", help="owner/repo, git URL, or local path")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"), help="token for private repos")
    ap.add_argument("--ref", default=None, help="branch/tag to clone")
    args = ap.parse_args()

    index = os.environ.get("SYNTHESUS_RAG_INDEX", str(ROOT / "data" / "user_faiss.index"))
    meta = os.environ.get("SYNTHESUS_RAG_METADATA", str(ROOT / "data" / "user_meta.json"))
    rag = RAGPipeline(index_path=index, metadata_path=meta, top_k=5, score_threshold=0.2)

    before = rag.total_vectors
    added, files, label = ingest_github_repo(rag, args.repo, token=args.token, ref=args.ref)
    print(f"Ingested {added} chunk(s) from {files} file(s) in '{label}'.")
    print(f"Index: {before} -> {rag.total_vectors} vectors  ({index})")
    print("Now boot the runtime and ask Synthesus about your repo.")


if __name__ == "__main__":
    main()
