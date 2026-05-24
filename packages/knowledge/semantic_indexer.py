"""
SemanticIndexer — Vector-based semantic search for the Knowledge Network.
Uses TF-IDF + SVD for lightweight embedding (SwarmEmbedder) with FAISS indexing.
"""

from __future__ import annotations

import json
import logging
import os
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import faiss
    _HAS_FAISS = True
except ImportError:
    _HAS_FAISS = False
    logger.warning("FAISS not available; semantic search will use fallback.")


class SemanticIndexer:
    """
    Semantic search index for Knowledge Network nodes.

    Uses SwarmEmbedder (TF-IDF + SVD) for embeddings + FAISS IndexFlatIP for
    cosine-similarity search. Falls back to simple keyword search if FAISS
    is unavailable.

    Usage:
        indexer = SemanticIndexer(kn=knowledge_network)
        indexer.index_node(node)
        results = indexer.search("dragon fire", top_k=5)
    """

    def __init__(
        self,
        kn=None,
        embedder=None,
        index_path: Optional[str] = None,
        meta_path: Optional[str] = None,
        dim: int = 128,
        auto_save: bool = True,
    ):
        """Initializes the SemanticIndexer.

        Args:
            kn: Knowledge Network instance. Defaults to None.
            embedder: Embedder instance (e.g., SwarmEmbedder). Defaults to None.
            index_path: Path to save/load the FAISS index. Defaults to None.
            meta_path: Path to save/load the metadata JSON. Defaults to None.
            dim: Dimensionality of the embeddings. Defaults to 128.
            auto_save: Whether to automatically save changes. Defaults to True.
        """
        self.kn = kn
        self.dim = dim
        self.index_path = Path(index_path) if index_path else None
        self.meta_path = Path(meta_path) if meta_path else None
        self.auto_save = auto_save
        self._dirty = False

        self._embedder = embedder
        self._index: Any = None
        self._node_ids: List[str] = []
        self._id_to_meta: Dict[str, Dict[str, Any]] = {}

        if _HAS_FAISS:
            self._init_faiss()
        if self.index_path and self.index_path.exists():
            self._load()
        elif meta_path and Path(meta_path).exists():
            self._load_meta()

    def _init_faiss(self) -> None:
        """Initializes the FAISS index."""
        if not _HAS_FAISS:
            return
        self._index = faiss.IndexFlatIP(self.dim)
        logger.info("FAISS IndexFlatIP initialized (dim=%d)", self.dim)

    @property
    def embedder(self):
        """Returns the embedder instance, initializing it if necessary."""
        if self._embedder is None:
            from ml.swarm_embedder import SwarmEmbedder
            self._embedder = SwarmEmbedder(dim=self.dim)
        return self._embedder

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_node(self, node) -> None:
        """Add a single node to the semantic index."""
        text = node.get_embedding_text() if hasattr(node, "get_embedding_text") else str(node.content or node.id)
        vec = self.embedder.embed_texts([text])
        self._add_vector(node.id, vec[0], {
            "id": node.id,
            "type": node.node_type.value if hasattr(node, "node_type") else "unknown",
            "display_name": node.display_name if hasattr(node, "display_name") else node.id,
            "description": node.description if hasattr(node, "description") else "",
            "tags": node.tags if hasattr(node, "tags") else [],
        })

    def index_nodes(self, nodes: List[Any]) -> int:
        """Bulk index a list of nodes."""
        if not nodes:
            return 0

        texts = []
        metas = []
        for node in nodes:
            text = node.get_embedding_text() if hasattr(node, "get_embedding_text") else str(node.content or node.id)
            texts.append(text)
            metas.append({
                "id": node.id,
                "type": node.node_type.value if hasattr(node, "node_type") else "unknown",
                "display_name": node.display_name if hasattr(node, "display_name") else node.id,
                "description": node.description if hasattr(node, "description") else "",
                "tags": node.tags if hasattr(node, "tags") else [],
            })

        vecs = self.embedder.embed_texts(texts)
        for vec, meta in zip(vecs, metas):
            self._add_vector(meta["id"], vec, meta)

        if self.auto_save:
            self._save()
        return len(nodes)

    def _add_vector(self, node_id: str, vec: np.ndarray, meta: Dict[str, Any]) -> None:
        """Adds a vector to the internal index and metadata store.

        Args:
            node_id: Unique identifier for the node.
            vec: The embedding vector as a numpy array.
            meta: Metadata associated with the node.
        """
        vec = vec.astype(np.float32)
        if vec.ndim == 1:
            vec = vec.reshape(1, -1)
        actual_dim = vec.shape[1]

        if node_id in self._id_to_meta:
            existing_idx = self._node_ids.index(node_id)
            if _HAS_FAISS and self._index is not None:
                self._index.remove_ids(np.array([existing_idx], dtype=np.int64))
            self._node_ids.pop(existing_idx)
            del self._id_to_meta[node_id]

        self._node_ids.append(node_id)
        self._id_to_meta[node_id] = meta

        if _HAS_FAISS and self._index is not None:
            if actual_dim != self.dim and self._index.ntotal == 0:
                logger.info("Reinitializing FAISS index dim from %d to %d to match embedder", self.dim, actual_dim)
                self.dim = actual_dim
                self._index = faiss.IndexFlatIP(self.dim)
            if actual_dim != self.dim:
                logger.warning("Vector dim %d != index dim %d; rebuilding index", actual_dim, self.dim)
                self._rebuild_index(actual_dim)
            faiss.normalize_L2(vec)
            self._index.add(vec)

        self._dirty = True

    def _rebuild_index(self, new_dim: int) -> None:
        """Rebuild FAISS index with a new dimensionality."""
        if not _HAS_FAISS:
            return
        old_index = self._index
        old_ids = list(self._node_ids)
        old_meta = dict(self._id_to_meta)

        self.dim = new_dim
        self._index = faiss.IndexFlatIP(self.dim)
        self._node_ids = []
        self._id_to_meta = {}

        if self.embedder and old_ids:
            texts = []
            metas = []
            for nid in old_ids:
                node = self.kn.get_node(nid) if self.kn else None
                if node:
                    text = node.get_embedding_text() if hasattr(node, "get_embedding_text") else str(node.content or node.id)
                    texts.append(text)
                    metas.append({
                        "id": node.id,
                        "type": node.node_type.value if hasattr(node, "node_type") else "unknown",
                        "display_name": node.display_name if hasattr(node, "display_name") else node.id,
                        "description": node.description if hasattr(node, "description") else "",
                        "tags": node.tags if hasattr(node, "tags") else [],
                    })
            if texts:
                vecs = self.embedder.embed_texts(texts)
                for vid, (v, m) in enumerate(zip(vecs, metas)):
                    self._node_ids.append(old_ids[vid])
                    self._id_to_meta[old_ids[vid]] = m
                    v_f = v.astype(np.float32)
                    if v_f.ndim == 1:
                        v_f = v_f.reshape(1, -1)
                    faiss.normalize_L2(v_f)
                    self._index.add(v_f)
        logger.info("FAISS index rebuilt with dim=%d (%d nodes)", new_dim, len(self._node_ids))

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 10,
        node_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_score: float = 0.0,
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Semantic similarity search. Returns list of (node_metadata, score).
        """
        if not self._node_ids:
            return []

        q_vec = self.embedder.embed_texts([query])
        q_vec = q_vec[0].astype(np.float32)
        if q_vec.ndim == 1:
            q_vec = q_vec.reshape(1, -1)
        faiss.normalize_L2(q_vec)

        if _HAS_FAISS and self._index is not None and self._index.ntotal > 0:
            q_dim = q_vec.shape[1]
            if q_dim != self._index.d:
                logger.warning(
                    "Query dim %d != FAISS index dim %d; rebuilding index to match embedder",
                    q_dim, self._index.d,
                )
                self._rebuild_index(q_dim)
            scores, indices = self._index.search(q_vec.reshape(1, -1).astype(np.float32), top_k)
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._node_ids):
                    continue
                node_id = self._node_ids[int(idx)]
                meta = self._id_to_meta.get(node_id, {})
                if min_score > 0 and float(score) < min_score:
                    continue
                if node_type and meta.get("type") != node_type:
                    continue
                if tags:
                    node_tags = set(meta.get("tags", []))
                    if not node_tags & set(tags):
                        continue
                results.append((meta, float(score)))
            return results

        return self._fallback_search(query, top_k, node_type, tags)

    def _fallback_search(
        self,
        query: str,
        top_k: int,
        node_type: Optional[str],
        tags: Optional[List[str]],
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Performs a simple keyword-based fallback search.

        Args:
            query: The search query string.
            top_k: Number of results to return.
            node_type: Filter by node type. Defaults to None.
            tags: Filter by tags. Defaults to None.

        Returns:
            A list of tuples containing (node_metadata, score).
        """
        query_terms = set(query.lower().split())
        scored: List[Tuple[Dict[str, Any], float]] = []

        for node_id, meta in self._id_to_meta.items():
            if node_type and meta.get("type") != node_type:
                continue

            text = f"{meta.get('display_name', '')} {meta.get('description', '')} {' '.join(meta.get('tags', []))}".lower()
            score = sum(1 for t in query_terms if t in text) / max(len(query_terms), 1)
            if score > 0:
                scored.append((meta, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Saves the index and metadata to disk."""
        if not self.auto_save:
            return

        if _HAS_FAISS and self._index is not None and self.index_path:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._index, str(self.index_path))

        if self.meta_path:
            self.meta_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.meta_path, "w", encoding="utf-8") as f:
                json.dump({
                    "dim": self.dim,
                    "node_ids": self._node_ids,
                    "meta": self._id_to_meta,
                }, f, indent=2, ensure_ascii=False)

        self._dirty = False
        logger.info("Semantic index saved (%d nodes)", len(self._node_ids))

    def _load(self) -> None:
        """Loads the index and metadata from disk."""
        if _HAS_FAISS and self.index_path and self.index_path.exists():
            try:
                self._index = faiss.read_index(str(self.index_path))
                self.dim = int(self._index.d)
                logger.info("FAISS index loaded: %d vectors, dim=%d", self._index.ntotal, self.dim)
            except Exception as e:
                logger.warning("Could not load FAISS index: %s", e)
                self._init_faiss()

        if self.meta_path and self.meta_path.exists():
            self._load_meta()

    def _load_meta(self) -> None:
        """Loads the metadata JSON from disk."""
        try:
            with open(self.meta_path, encoding="utf-8") as f:
                data = json.load(f)
            self._node_ids = data.get("node_ids", [])
            self._id_to_meta = data.get("meta", {})
            self.dim = data.get("dim", self.dim)
            logger.info("Semantic index metadata loaded: %d nodes", len(self._node_ids))
        except Exception as e:
            logger.error("Failed to load semantic index metadata: %s", e)

    def stats(self) -> Dict[str, Any]:
        """Returns statistics about the index.

        Returns:
            A dictionary containing index metrics.
        """
        return {
            "indexed_nodes": len(self._node_ids),
            "faiss_vectors": int(self._index.ntotal) if _HAS_FAISS and self._index else 0,
            "dim": self.dim,
            "dirty": self._dirty,
        }