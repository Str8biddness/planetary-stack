#!/usr/bin/env python3
"""
Synthetic RAG Pipeline - Synthesus 2.0
AIVM LLC

Implements the Synthetic RAG Reasoning System from DeepSeek design:
- FAISS vector index for semantic retrieval
- Character-aware context injection
- Batched embedding with sleep intervals (CPU-safe)
- Checkpoint-based migration (34% @ 290K patterns resume point)

Embedding provided by SwarmEmbedder (lightweight TF-IDF + SVD),
no sentence-transformers or PyTorch required.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import faiss
import numpy as np

from ml.swarm_embedder import SwarmEmbedder

try:
    from knowledge_integration.cloud_sync import bootstrap_knowledge_cache
except Exception:
    bootstrap_knowledge_cache = None


def _should_bootstrap_knowledge_cache(local_root: Path) -> bool:
    return local_root.name == "data"

logger = logging.getLogger(__name__)


class RAGPipeline:
    """
    Synthetic RAG Pipeline for Synthesus.
    Retrieves relevant patterns and knowledge nodes from FAISS index.
    Injects context into right hemisphere queries.
    """

    def __init__(
        self,
        index_path: str = "./data/faiss.index",
        metadata_path: str = "./data/faiss_metadata.json",
        model_dir: str | None = None,
        top_k: int = 5,
        score_threshold: float = 0.4,
        batch_size: int = 256,
        batch_sleep_s: float = 0.5,
        embedding_dim: int = 128,
    ):
        self.index_path = Path(index_path)
        self.metadata_path = Path(metadata_path)
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.batch_size = batch_size
        self.batch_sleep_s = batch_sleep_s
        self.embedding_dim = embedding_dim

        self._index: Optional[faiss.Index] = None
        self._metadata: List[Dict] = []
        self._embedder: Optional[SwarmEmbedder] = None

        self._load()

    def _load(self):
        """Load SwarmEmbedder, FAISS index, and metadata from disk."""
        if bootstrap_knowledge_cache is not None and _should_bootstrap_knowledge_cache(self.index_path.parent):
            try:
                report = bootstrap_knowledge_cache(self.index_path.parent)
                downloaded = report.get("downloaded", [])
                if downloaded:
                    logger.info("Knowledge cache bootstrapped from cloud: %s", ", ".join(downloaded))
            except Exception as e:
                logger.warning(f"Knowledge cloud bootstrap skipped: {e}")

        logger.info("Loading SwarmEmbedder...")
        try:
            # Try to load pre-fitted model from data/models/ first
            model_dir = Path(self.index_path.parent) / "models"
            self._embedder = SwarmEmbedder(model_dir=model_dir, dim=self.embedding_dim)
            if self._embedder.is_fitted:
                logger.info(f"SwarmEmbedder loaded pre-fitted (dim={self._embedder.dim}).")
            else:
                logger.info("SwarmEmbedder ready (lazy-fit on first corpus).")
        except Exception as e:
            logger.error(f"Failed to init SwarmEmbedder: {e}")
            return

        if self.index_path.exists():
            logger.info(f"Loading FAISS index from {self.index_path}...")
            self._index = faiss.read_index(str(self.index_path))
            logger.info(f"FAISS index loaded: {self._index.ntotal} vectors")
        else:
            logger.warning(f"FAISS index not found at {self.index_path}. Starting empty.")
            self._index = faiss.IndexFlatIP(self.embedding_dim)

        if self.metadata_path.exists():
            with open(self.metadata_path, "r") as f:
                self._metadata = json.load(f)
            logger.info(f"Metadata loaded: {len(self._metadata)} entries")
        else:
            logger.warning("Metadata file not found. Starting empty.")
            self._metadata = []

    def _embed(self, texts: List[str]) -> np.ndarray:
        """Generate normalized embeddings for a list of texts."""
        return self._embedder.embed_texts(texts)

    async def retrieve(
        self,
        query: str,
        character_id: Optional[str] = None,
        namespaces: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Retrieve relevant context for a query.
        Returns dict with 'context' string and 'sources' list.
        """
        if self._index is None or self._index.ntotal == 0:
            return {"context": "", "sources": []}

        k = top_k or self.top_k
        threshold = score_threshold if score_threshold is not None else self.score_threshold

        # Run blocking embedding + search in executor
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: self._search(query, character_id, namespaces, k, threshold)
        )

        if not results:
            return {"context": "", "sources": []}

        context_parts = []
        sources = []
        for score, meta in results:
            pattern = meta.get("pattern", "")
            response = meta.get("response", "")
            char = meta.get("character_id", "global")
            ns = meta.get("namespace", "general")
            domain = meta.get("domain", "")
            
            context_parts.append(f"Q: {pattern}\nA: {response}")
            sources.append({
                "pattern": pattern, 
                "score": round(score, 4), 
                "character": char,
                "namespace": ns,
                "domain": domain
            })

        context = "\n\n".join(context_parts)
        return {"context": context, "sources": sources}

    def _search(
        self, 
        query: str, 
        character_id: Optional[str], 
        namespaces: Optional[List[str]], 
        k: int,
        threshold: float
    ) -> List[Tuple[float, Dict]]:
        """Synchronous FAISS search."""
        try:
            query_emb = self._embed([query])
            # V4: Deeper over-fetch (100x) to ensure character knowledge isn't buried under globally similar patterns
            search_depth = min(k * 100, self.total_vectors)
            scores, indices = self._index.search(query_emb, search_depth)  

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._metadata):
                    continue
                if score < threshold:
                    continue
                
                meta = self._metadata[idx]
                
                # Filter by character if specified
                if character_id and meta.get("character_id") not in (character_id, "global", None):
                    continue
                
                # Filter by namespace if specified
                if namespaces and meta.get("namespace") not in namespaces:
                    continue
                    
                results.append((float(score), meta))
                if len(results) >= k:
                    break

            return results
        except Exception as e:
            logger.error(f"FAISS search error: {e}")
            return []

    def add_patterns(
        self,
        patterns: List[Dict],
        character_id: Optional[str] = None,
        checkpoint_path: Optional[str] = None
    ) -> int:
        """
        Add patterns to the FAISS index in CPU-safe batches.
        Supports checkpoint resume for large migrations.
        Returns number of patterns added.
        """
        total = len(patterns)
        added = 0
        checkpoint_file = Path(checkpoint_path) if checkpoint_path else None

        # Load checkpoint if exists
        start_idx = 0
        if checkpoint_file and checkpoint_file.exists():
            with open(checkpoint_file) as f:
                cp = json.load(f)
                start_idx = cp.get("last_batch_end", 0)
                logger.info(f"Resuming from checkpoint: {start_idx}/{total}")

        # Pre-fit embedder on the full corpus so TF-IDF vocabulary is complete
        all_texts = [p.get("pattern", "") for p in patterns]
        if not self._embedder.is_fitted:
            self._embedder.fit(all_texts)

        # Rebuild FAISS index with correct dimension after fitting
        if self._index is None or self._index.d != self._embedder.dim:
            self._index = faiss.IndexFlatIP(self._embedder.dim)

        for batch_start in range(start_idx, total, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total)
            batch = patterns[batch_start:batch_end]

            texts = [p.get("pattern", "") for p in batch]
            embeddings = self._embed(texts)

            self._index.add(embeddings)
            for p in batch:
                meta = dict(p)
                if character_id:
                    meta["character_id"] = character_id
                self._metadata.append(meta)

            added += len(batch)

            # Save checkpoint
            if checkpoint_file:
                with open(checkpoint_file, "w") as f:
                    json.dump({"last_batch_end": batch_end, "total": total}, f)

            logger.info(f"RAG migration: {batch_end}/{total} ({batch_end/total*100:.1f}%)")

            # CPU-safe sleep between batches
            time.sleep(self.batch_sleep_s)

        return added

    def save_index(self):
        """Save FAISS index and metadata to disk."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self.index_path))
        with open(self.metadata_path, "w") as f:
            json.dump(self._metadata, f)
        logger.info(f"FAISS index saved: {self._index.ntotal} vectors")

    @property
    def total_vectors(self) -> int:
        return self._index.ntotal if self._index else 0

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_vectors": self.total_vectors,
            "metadata_entries": len(self._metadata),
            "index_path": str(self.index_path),
            "top_k": self.top_k,
            "score_threshold": self.score_threshold,
            "embedding_dim": self.embedding_dim,
            "embedder_fitted": self._embedder.is_fitted if self._embedder else False,
        }
