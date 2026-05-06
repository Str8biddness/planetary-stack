"""
IVFFlat Backend — Standalone FAISS IndexIVFFlat for 50K-1M vector scale.

Uses Inverted File Index with inner-product search for sub-linear
retrieval at scale while remaining CPU-only.

Scale thresholds (from ADR 5):
  < 50K vectors  → use FaissKalBackend (IndexFlatIP)
  50K-1M vectors → use this IVFFlatKalBackend
  > 1M vectors   → migrate to Qdrant (future)
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import faiss
import numpy as np

from ..schemas import KalQuery, KalResult, KalKnowledgeNode
from .base import KalBackend

logger = logging.getLogger(__name__)


class IVFFlatKalBackend(KalBackend):
    """KAL backend using FAISS IndexIVFFlat for sub-linear search at scale.

    Recommended for datasets with 50K–1M vectors. Requires a training
    phase before vectors can be added.
    """

    def __init__(
        self,
        embedding_dim: int = 128,
        nlist: int = 100,
        index_path: Optional[str] = None,
        metadata_path: Optional[str] = None,
    ) -> None:
        """
        Args:
            embedding_dim: Dimensionality of embeddings (SwarmEmbedder default: 128).
            nlist: Number of Voronoi cells for IVF. Rule of thumb: 4 * sqrt(N).
            index_path: Path to load/save the FAISS index.
            metadata_path: Path to load/save metadata JSON.
        """
        self.embedding_dim = embedding_dim
        self.nlist = nlist
        self.index_path = Path(index_path) if index_path else None
        self.metadata_path = Path(metadata_path) if metadata_path else None

        # Build the IVF index
        self._quantizer = faiss.IndexFlatIP(embedding_dim)
        self._index = faiss.IndexIVFFlat(
            self._quantizer, embedding_dim, nlist, faiss.METRIC_INNER_PRODUCT
        )
        self._is_trained = False
        self._metadata: List[Dict[str, Any]] = []

        # Lazy-loaded embedder
        self._embedder = None

        # Try to load existing index
        self._load()

    def _get_embedder(self):
        """Lazy-load SwarmEmbedder."""
        if self._embedder is None:
            from ml.swarm_embedder import SwarmEmbedder
            self._embedder = SwarmEmbedder(dim=self.embedding_dim)
        return self._embedder

    def _load(self) -> None:
        """Load index and metadata from disk if available."""
        if self.index_path and self.index_path.exists():
            try:
                self._index = faiss.read_index(str(self.index_path))
                self._is_trained = True
                logger.info(
                    "IVFFlatBackend: loaded index with %d vectors from %s",
                    self._index.ntotal, self.index_path,
                )
            except Exception as e:
                logger.warning("IVFFlatBackend: failed to load index: %s", e)

        if self.metadata_path and self.metadata_path.exists():
            try:
                with open(self.metadata_path) as f:
                    self._metadata = json.load(f)
                logger.info(
                    "IVFFlatBackend: loaded %d metadata entries", len(self._metadata)
                )
            except Exception as e:
                logger.warning("IVFFlatBackend: failed to load metadata: %s", e)

    def train_and_add(
        self,
        embeddings: np.ndarray,
        metadata: List[Dict[str, Any]],
    ) -> None:
        """Train the IVF index and add vectors.

        Must be called before queries can be executed. The training phase
        builds the Voronoi cell structure for sub-linear search.

        Args:
            embeddings: (N, embedding_dim) float32 array.
            metadata: List of metadata dicts, one per embedding.
        """
        embeddings = np.ascontiguousarray(embeddings, dtype=np.float32)
        n_vectors = embeddings.shape[0]

        if not self._is_trained:
            # Need at least nlist vectors to train
            effective_nlist = min(self.nlist, n_vectors)
            if effective_nlist < self.nlist:
                logger.warning(
                    "IVFFlatBackend: reducing nlist from %d to %d (only %d training vectors)",
                    self.nlist, effective_nlist, n_vectors,
                )
                # Rebuild with reduced nlist
                self._quantizer = faiss.IndexFlatIP(self.embedding_dim)
                self._index = faiss.IndexIVFFlat(
                    self._quantizer, self.embedding_dim, effective_nlist,
                    faiss.METRIC_INNER_PRODUCT,
                )

            self._index.train(embeddings)
            self._is_trained = True
            logger.info("IVFFlatBackend: trained on %d vectors", n_vectors)

        self._index.add(embeddings)
        self._metadata.extend(metadata)
        logger.info(
            "IVFFlatBackend: added %d vectors (total: %d)",
            n_vectors, self._index.ntotal,
        )

    def save(self) -> None:
        """Save index and metadata to disk."""
        if self.index_path:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._index, str(self.index_path))
            logger.info("IVFFlatBackend: saved index (%d vectors)", self._index.ntotal)
        if self.metadata_path:
            with open(self.metadata_path, "w") as f:
                json.dump(self._metadata, f)
            logger.info("IVFFlatBackend: saved %d metadata entries", len(self._metadata))

    async def query(self, kal_query: KalQuery) -> KalResult:
        """Execute a knowledge retrieval query using IVFFlat search."""
        start = time.time()

        if not self._is_trained or self._index.ntotal == 0:
            return KalResult(
                results=[],
                retrieval_latency_ms=0.0,
                cache_hit=False,
                debug={"backend_name": "faiss_ivf", "error": "index not trained or empty"},
            )

        # Embed the query
        embedder = self._get_embedder()
        if kal_query.context_vector is not None:
            q_emb = np.array([kal_query.context_vector], dtype=np.float32)
        else:
            q_emb = embedder.embed_texts([kal_query.query])
            q_emb = np.ascontiguousarray(q_emb, dtype=np.float32)

        # Set nprobe for search quality/speed tradeoff
        self._index.nprobe = min(10, self.nlist)

        # Search
        k = min(kal_query.top_k * 2, self._index.ntotal)  # over-fetch for filtering
        scores, indices = self._index.search(q_emb, k)

        # Build results with namespace filtering
        effective_ns = kal_query.effective_namespaces
        items: List[KalKnowledgeNode] = []

        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._metadata):
                continue
            if score < 0.1:  # Floor
                continue

            meta = self._metadata[idx]
            namespace = meta.get("domain", meta.get("namespace", "general"))

            # Namespace filtering
            if effective_ns and namespace not in effective_ns:
                continue

            items.append(
                KalKnowledgeNode(
                    node_id=str(uuid.uuid4()),
                    content=meta.get("response", meta.get("pattern", "")) if kal_query.include_raw else "",
                    confidence=float(score),
                    source_namespace=namespace,
                    metadata={
                        "source": meta.get("pattern", meta.get("source", "")),
                        "timestamp": meta.get("timestamp", ""),
                        "trust_level": meta.get("trust_level", "medium"),
                        "tags": meta.get("tags", []),
                        "character": meta.get("character_id", "global"),
                    },
                )
            )

            if len(items) >= kal_query.top_k:
                break

        latency_ms = (time.time() - start) * 1000

        return KalResult(
            results=items,
            retrieval_latency_ms=round(latency_ms, 2),
            cache_hit=False,
            debug={
                "backend_name": "faiss_ivf",
                "index_vectors": self._index.ntotal,
                "nlist": self.nlist,
                "nprobe": self._index.nprobe,
                "latency_ms": round(latency_ms, 2),
                "mode": kal_query.mode,
            },
        )

    @property
    def total_vectors(self) -> int:
        return self._index.ntotal
