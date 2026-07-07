"""Semantic embedder for the agnostic expansion drive.

Drop-in replacement for SwarmEmbedder that produces MEANING-based embeddings
(sentence-transformers/all-MiniLM-L6-v2, 384-dim) instead of lexical TF-IDF.
This is what lets Synthesus answer natural-language questions about a user's
code/docs ("what does the login function do") rather than only keyword hits.

Backend: fastembed (ONNX runtime) — same MiniLM vectors as sentence-transformers
but a fraction of torch's install weight, which matters for the AppImage.

Interface mirrors SwarmEmbedder so RAGPipeline uses it unchanged:
    .dim, .is_fitted, .fit(texts) -> no-op, .embed_texts(texts) -> np.ndarray
Vectors are L2-normalized, so FAISS inner-product == cosine similarity.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_DIM = 384


class SemanticEmbedder:
    def __init__(self, model_dir=None, dim: int = MODEL_DIM, model_name: str = DEFAULT_MODEL):
        # `model_dir`/`dim` accepted for interface parity with SwarmEmbedder.
        # A pretrained model has no corpus-fit step, so it is always "fitted".
        from fastembed import TextEmbedding  # local import: heavy dep, only if selected

        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)
        self.dim = MODEL_DIM
        if dim not in (None, MODEL_DIM):
            logger.warning("SemanticEmbedder dim=%s ignored; %s is %d-dim.", dim, model_name, MODEL_DIM)

    @property
    def is_fitted(self) -> bool:
        return True  # pretrained — no lexical vocabulary to fit

    def fit(self, texts: List[str]) -> None:
        return None  # no-op: pretrained model needs no corpus fit

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        vecs = np.asarray(list(self._model.embed(list(texts))), dtype="float32")
        # fastembed returns normalized vectors; re-normalize defensively so
        # inner-product search == cosine even if that ever changes upstream.
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms
