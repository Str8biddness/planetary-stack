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
import threading

from ml.swarm_embedder import SwarmEmbedder

try:
    from knowledge_integration.cloud_sync import bootstrap_knowledge_cache
except Exception:
    bootstrap_knowledge_cache = None

try:
    from memory_provenance import (
        Provenance,
        Verification,
        annotate_metadata,
        resolve_legacy_metadata,
        weight_for,
    )
except ImportError:
    from knowledge.memory_provenance import (  # type: ignore
        Provenance,
        Verification,
        annotate_metadata,
        resolve_legacy_metadata,
        weight_for,
    )


def _should_bootstrap_knowledge_cache(local_root: Path) -> bool:
    return local_root.name == "data"

logger = logging.getLogger(__name__)


def _enrich_pattern_metadata(meta: Dict[str, Any], *, default_provenance: Optional[str] = None) -> Dict[str, Any]:
    """Ensure provenance + verification fields exist on a pattern metadata dict.

    Explicit fields are preserved (subject to anti-collapse rules in annotate).
    Legacy items without fields receive backward-compatible defaults.
    """
    out = dict(meta)
    if out.get("provenance") is not None:
        prov = out.get("provenance")
        refs = out.get("provenance_refs") or []
        if out.get("source") and out["source"] not in refs:
            refs = list(refs) + [str(out["source"])]
        annotate_metadata(
            out,
            provenance=prov,
            provenance_refs=refs,
            origin_voice=out.get("origin_voice"),
            created_ts=out.get("created_ts"),
            confirmed_ts=out.get("confirmed_ts"),
            confirmed_by=out.get("confirmed_by"),
            verification=out.get("verification"),
        )
        return out

    if default_provenance is not None:
        refs = list(out.get("provenance_refs") or [])
        if out.get("source") and str(out["source"]) not in refs:
            refs.append(str(out["source"]))
        annotate_metadata(
            out,
            provenance=default_provenance,
            provenance_refs=refs,
            origin_voice=out.get("origin_voice"),
        )
        return out

    prov, tier = resolve_legacy_metadata(out)
    refs = list(out.get("provenance_refs") or [])
    if out.get("source") and str(out["source"]) not in refs:
        refs.append(str(out["source"]))
    annotate_metadata(
        out,
        provenance=prov,
        provenance_refs=refs,
        origin_voice=out.get("origin_voice"),
        verification=tier,
    )
    return out


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
        # Empirically calibrated on the REAL user index (tools/retrieval_eval.py
        # --real-index): off-topic/junk queries score <=~0.28 while true code/doc
        # hits score >=~0.37. 0.32 sits inside that gap — it rejects junk grounding
        # without filtering legitimate (lower-scoring) real hits. The old 0.4 was
        # ABOVE the real-hit floor and silently dropped valid grounding.
        score_threshold: float = 0.32,
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
        # FAISS is not thread-safe for concurrent add()/search(); retrieve() runs
        # _search in a threadpool executor while ingest may add() on another thread.
        # Serialize index mutation + search so a query during an ingest can't hit a
        # half-updated index (a source of the transient "freshly-ingested doc missed
        # on the first query" behaviour). Cheap: adds/searches are already fast.
        self._index_lock = threading.RLock()
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

        # Embedder selection: semantic (meaning-based, expansion drive) vs the
        # lexical SwarmEmbedder. SYNTHESUS_EMBEDDER=semantic picks MiniLM-384.
        model_dir = Path(self.index_path.parent) / "models"
        want_semantic = os.environ.get("SYNTHESUS_EMBEDDER", "").lower() == "semantic"
        try:
            if want_semantic:
                logger.info("Loading SemanticEmbedder (MiniLM-384)...")
                from ml.semantic_embedder import SemanticEmbedder
                self._embedder = SemanticEmbedder(model_dir=model_dir, dim=self.embedding_dim)
                # Meaning-based model dictates the index dimension.
                self.embedding_dim = self._embedder.dim
                logger.info(f"SemanticEmbedder ready (dim={self._embedder.dim}).")
            else:
                logger.info("Loading SwarmEmbedder...")
                self._embedder = SwarmEmbedder(model_dir=model_dir, dim=self.embedding_dim)
                if self._embedder.is_fitted:
                    logger.info(f"SwarmEmbedder loaded pre-fitted (dim={self._embedder.dim}).")
                else:
                    logger.info("SwarmEmbedder ready (lazy-fit on first corpus).")
        except Exception as e:
            logger.error(f"Failed to init embedder: {e}")
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
        """Generate normalized embeddings for a list of texts.

        FAISS requires a C-contiguous float32 array for both add() and search();
        a float64 or non-contiguous array makes those raise a cryptic/empty error
        (the intermittent "FAISS search error" that made a freshly-ingested doc miss
        on the first query). Normalize here so every add/search is well-formed.
        """
        emb = self._embedder.embed_texts(texts)
        return np.ascontiguousarray(emb, dtype=np.float32)

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
            # Provenance ref (e.g. "myrepo/auth.py") written by the expansion-drive
            # connectors; fall back to namespace so every hit carries a source.
            source = meta.get("source") or ns
            prov, tier = resolve_legacy_metadata(meta)

            context_parts.append(f"Q: {pattern}\nA: {response}")
            sources.append({
                "pattern": pattern,
                "score": round(score, 4),
                "character": char,
                "namespace": ns,
                "domain": domain,
                "source": source,
                "provenance": prov.value if hasattr(prov, "value") else str(prov),
                "verification": int(tier),
                "verification_name": tier.name if hasattr(tier, "name") else str(tier),
                "provenance_refs": list(meta.get("provenance_refs") or ([source] if source else [])),
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
            n = self._index.ntotal if self._index is not None else 0
            if n == 0:
                return []
            query_emb = self._embed([query])
            # V4: Deeper over-fetch (100x) to ensure character knowledge isn't buried under globally similar patterns
            search_depth = max(1, min(k * 100, n))
            with self._index_lock:
                scores, indices = self._index.search(query_emb, search_depth)

            # Collect candidates above the raw-similarity threshold (calibration
            # stays on unweighted FAISS scores), then re-rank by
            # similarity × VERIFICATION_WEIGHT so verified out-ranks guesses.
            candidates = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._metadata):
                    continue
                raw = float(score)
                if raw < threshold:
                    continue

                meta = self._metadata[idx]

                # Filter by character if specified
                if character_id and meta.get("character_id") not in (character_id, "global", None):
                    continue

                # Filter by namespace if specified
                if namespaces and meta.get("namespace") not in namespaces:
                    continue

                weighted = raw * weight_for(meta)
                candidates.append((weighted, meta, raw))

            candidates.sort(key=lambda item: item[0], reverse=True)
            return [(weighted, meta) for weighted, meta, _raw in candidates[:k]]
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

            with self._index_lock:
                self._index.add(embeddings)
            for p in batch:
                meta = _enrich_pattern_metadata(dict(p))
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

    def append_patterns(self, patterns: List[Dict], character_id: Optional[str] = None) -> int:
        """Append patterns to the EXISTING index without rebuilding it (preserves
        prior knowledge). Uses the real embedding dimension and raises on a
        dimension mismatch instead of silently wiping the index (the add_patterns
        rebuild bug). Requires a fitted embedder."""
        if not patterns:
            return 0
        if self._embedder is None or not self._embedder.is_fitted:
            raise RuntimeError(
                "Embedder must be fitted before appending to an existing index."
            )
        added = 0
        for batch_start in range(0, len(patterns), self.batch_size):
            batch = patterns[batch_start:batch_start + self.batch_size]
            embeddings = self._embed([p.get("pattern", "") for p in batch])
            dim = embeddings.shape[1]
            if self._index is None:
                self._index = faiss.IndexFlatIP(dim)
            elif self._index.d != dim:
                raise ValueError(
                    f"Embedding dim {dim} != existing index dim {self._index.d}; "
                    "refusing to append (would corrupt the index)."
                )
            with self._index_lock:
                self._index.add(embeddings)
            for p in batch:
                meta = _enrich_pattern_metadata(dict(p))
                if character_id:
                    meta["character_id"] = character_id
                self._metadata.append(meta)
            added += len(batch)
            time.sleep(self.batch_sleep_s)
        return added

    def ingest_documents(self, paths, namespace: str = "user_docs",
                         chunk_size: int = 400, save: bool = True) -> int:
        """Read local text/markdown files, chunk them, and APPEND to the index so
        Synthesus can ground answers on YOUR documents (local, private). Returns
        the number of chunks added.

        Ingested user files are tagged USER_DOCUMENT / VERIFIED (external signal).
        """
        exts = {".txt", ".md", ".markdown", ".rst"}
        files: List[Path] = []
        for p in ([paths] if isinstance(paths, (str, Path)) else paths):
            path = Path(p)
            if path.is_dir():
                files += [f for f in path.rglob("*") if f.is_file() and f.suffix.lower() in exts]
            elif path.is_file():
                files.append(path)

        def _chunk(text: str) -> List[str]:
            words, chunks, cur, cur_len = text.split(), [], [], 0
            for w in words:
                if cur_len + len(w) > chunk_size and cur:
                    chunks.append(" ".join(cur)); cur, cur_len = [w], len(w)
                else:
                    cur.append(w); cur_len += len(w) + 1
            if cur:
                chunks.append(" ".join(cur))
            return chunks

        patterns: List[Dict] = []
        now = time.time()
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for chunk in _chunk(text):
                if chunk.strip():
                    patterns.append({
                        "pattern": chunk, "response": chunk,
                        "namespace": namespace, "domain": "user_docs", "source": f.name,
                        "provenance": Provenance.USER_DOCUMENT.value,
                        "verification": int(Verification.VERIFIED),
                        "provenance_refs": [f.name],
                        "origin_voice": None,
                        "created_ts": now,
                        "confirmed_ts": now,
                        "confirmed_by": "user_document_ingest",
                    })
        added = self.append_patterns(patterns)
        if save and added:
            self.save_index()
        logger.info(f"Ingested {added} chunks from {len(files)} file(s) into namespace '{namespace}'.")
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
