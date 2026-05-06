"""
Reranker - Cross-Encoder Re-ranking of Retrieved Chunks

Position in pipeline: After the RAG pipeline retrieves an initial set of chunks
from vector search, the reranker applies a cross-encoder model to score and reorder
chunks based on their actual relevance to the specific query.
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any
import numpy as np

logger = logging.getLogger(__name__)

class CrossEncoderReranker:
    """
    Cross-encoder reranking using sentence-transformers.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        config: Optional[Dict[str, Any]] = None
    ) -> None:
        self.model_name = model_name
        self.config = config or {}
        self.device = self.config.get("device", "cpu")
        self.max_length = self.config.get("max_length", 512)
        self.batch_size = self.config.get("batch_size", 32)
        self._model = None
        self._load_attempted = False

    @property
    def model(self) -> Any:
        if self._model is None and not self._load_attempted:
            self._load_attempted = True
            try:
                from sentence_transformers import CrossEncoder
                logger.info(f"Loading reranker model: {self.model_name} on {self.device}")
                self._model = CrossEncoder(
                    self.model_name,
                    device=self.device,
                    max_length=self.max_length
                )
            except ImportError:
                logger.warning("sentence_transformers not installed. Reranker will use fallback (no-op).")
            except Exception as e:
                logger.error(f"Failed to load reranker model: {e}")
        return self._model

    def rerank(
        self,
        query: str,
        chunks: List[str],
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        if not chunks:
            return []

        # If model failed to load, return first top_k as fallback
        if self.model is None:
            return [
                {"chunk": c, "score": 1.0 / (i + 1), "rank": i + 1, "index": i}
                for i, c in enumerate(chunks[:top_k])
            ]

        try:
            pairs = [[query, chunk] for chunk in chunks]
            scores = self.model.predict(pairs, batch_size=self.batch_size)
            
            # Convert scores to list if they are numpy array
            if isinstance(scores, np.ndarray):
                scores = scores.tolist()
            
            indexed = list(zip(chunks, scores, range(len(chunks))))
            indexed.sort(key=lambda x: x[1], reverse=True)

            results = []
            for rank, (chunk, score, orig_idx) in enumerate(indexed[:top_k], start=1):
                results.append({
                    "chunk": chunk,
                    "score": float(score),
                    "rank": rank,
                    "index": orig_idx
                })
            return results
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            # Fallback: return top_k chunks in original order with 0.0 score
            return [
                {"chunk": c, "score": 0.0, "rank": i+1, "index": i}
                for i, c in enumerate(chunks[:top_k])
            ]
