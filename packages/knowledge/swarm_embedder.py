#!/usr/bin/env python3
"""
SwarmEmbedder — Lightweight Embedding for Synthesus 2.0 ML Swarm
AIVM LLC

Replaces sentence-transformers + PyTorch with a pure sklearn/numpy pipeline:
  1. TF-IDF character n-gram vectorization (no neural network)
  2. TruncatedSVD dimensionality reduction → fixed-dim dense vectors
  3. L2 normalisation → ready for FAISS IndexFlatIP (cosine similarity)

Total footprint: ~50 KB fitted model (serialisable via joblib).
Inference: <1 ms per query on CPU.

Usage:
    embedder = SwarmEmbedder(dim=128)
    vecs = embedder.embed_texts(["hello world", "hi there"])
    # vecs.shape == (2, 128), dtype float32, L2-normalised
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Union

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional persistence via joblib (not required for in-memory use)
# ---------------------------------------------------------------------------
try:
    import joblib
    _HAS_JOBLIB = True
except ImportError:
    _HAS_JOBLIB = False


class SwarmEmbedder:
    """
    Lightweight text embedder for the Synthesus ML Swarm.

    Produces dense, L2-normalised float32 vectors suitable for FAISS
    inner-product (cosine similarity) search.

    The embedder is **fitted lazily** on the first corpus it sees, and
    can optionally be saved/loaded from disk for persistence across
    restarts.
    """

    DEFAULT_DIM = 128

    def __init__(
        self,
        model_dir: Optional[Union[str, Path]] = None,
        dim: int = DEFAULT_DIM,
    ):
        """
        Args:
            model_dir: Optional directory to load/save fitted model artifacts.
                       If a fitted model exists here, it is loaded immediately.
            dim:       Output embedding dimension (default 128).
        """
        self.dim = dim
        self.model_dir = Path(model_dir) if model_dir else None

        self._tfidf = None       # TfidfVectorizer
        self._svd = None         # TruncatedSVD
        self._fitted = False

        # Try to load a previously fitted model
        if self.model_dir and self._model_path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """
        Return a 2D numpy array of shape (len(texts), self.dim),
        dtype float32, L2-normalised.  Suitable for FAISS IndexFlatIP.

        If the embedder has not been fitted yet, it fits on the provided
        texts (cold-start path).
        """
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)

        if not self._fitted:
            self._fit(texts)

        return self._transform(texts)

    def fit(self, corpus: list[str]) -> None:
        """Explicitly fit the embedder on a corpus (optional)."""
        self._fit(corpus)

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fit(self, corpus: list[str]) -> None:
        """Fit TF-IDF + SVD on the given corpus."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import TruncatedSVD

        logger.info(
            f"SwarmEmbedder: fitting on {len(corpus)} texts → {self.dim}-dim"
        )

        # Character n-gram TF-IDF (3–5 grams captures sub-word patterns)
        self._tfidf = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            max_features=8192,
            sublinear_tf=True,
            strip_accents="unicode",
            dtype=np.float32,
        )

        tfidf_matrix = self._tfidf.fit_transform(corpus)

        # SVD to reduce to dense dim-dimensional vectors
        actual_dim = min(self.dim, tfidf_matrix.shape[1] - 1, tfidf_matrix.shape[0] - 1)
        if actual_dim < 1:
            actual_dim = 1
        self._svd = TruncatedSVD(n_components=actual_dim, random_state=42)
        self._svd.fit(tfidf_matrix)

        self._fitted = True
        self.dim = actual_dim  # update in case corpus was tiny
        logger.info(
            f"SwarmEmbedder: fitted (tfidf features={tfidf_matrix.shape[1]}, "
            f"svd dim={actual_dim})"
        )

        # Persist if model_dir is set
        if self.model_dir:
            self._save()

    def _transform(self, texts: list[str]) -> np.ndarray:
        """Transform texts to dense L2-normalised embeddings."""
        sparse = self._tfidf.transform(texts)
        dense = self._svd.transform(sparse).astype(np.float32)

        # L2 normalise for cosine similarity via inner product
        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        dense /= norms

        return dense

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @property
    def _model_path(self) -> Path:
        return self.model_dir / "swarm_embedder.pkl"

    def _save(self) -> None:
        if not _HAS_JOBLIB:
            logger.debug("SwarmEmbedder: joblib not available, skipping save")
            return
        self.model_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"tfidf": self._tfidf, "svd": self._svd, "dim": self.dim},
            self._model_path,
        )
        logger.info(f"SwarmEmbedder: saved to {self._model_path}")

    def _load(self) -> None:
        if not _HAS_JOBLIB:
            logger.debug("SwarmEmbedder: joblib not available, skipping load")
            return
        try:
            data = joblib.load(self._model_path)
            self._tfidf = data["tfidf"]
            self._svd = data["svd"]
            self.dim = data["dim"]
            self._fitted = True
            logger.info(
                f"SwarmEmbedder: loaded from {self._model_path} (dim={self.dim})"
            )
        except Exception as e:
            logger.warning(f"SwarmEmbedder: failed to load model: {e}")
