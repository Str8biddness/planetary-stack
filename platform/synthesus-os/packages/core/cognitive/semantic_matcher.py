"""
Semantic Matcher — Left Hemisphere Upgrade

Replaces keyword/token overlap with semantic embedding-based matching.
Uses SwarmEmbedder (TF-IDF + SVD, ~128-dim) + FAISS IndexFlatIP for
sub-millisecond cosine similarity lookup against all pattern triggers.

This lets NPCs understand:
- Paraphrasing: "what do you sell?" ≈ "got any wares?"
- Slang: "yo lemme cop some gear" ≈ "I'd like to buy equipment"
- Indirect references: "heard anything interesting?" ≈ "any rumors?"
- Typos/variations: "whats ur name" ≈ "what is your name?"

Architecture:
1. At init: embed all triggers → FAISS index (one-time, <10ms per 100 triggers)
2. At query: embed query → FAISS search → top-K candidates with scores
3. Caller blends semantic score with existing token score for hybrid matching

Memory: ~50 KB fitted model + ~1KB per 100 triggers (negligible index)
Latency: <1ms per query on CPU (TF-IDF + SVD is near-instant)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None

logger = logging.getLogger(__name__)

# Lazy-loaded global (shared across all NPC instances)
_embedder = None
_embedder_load_time = 0.0


def _get_embedder():
    """Lazy-load the SwarmEmbedder (shared singleton)."""
    global _embedder, _embedder_load_time
    if _embedder is None:
        start = time.time()
        from ml.swarm_embedder import SwarmEmbedder
        _embedder = SwarmEmbedder(dim=128)
        _embedder_load_time = (time.time() - start) * 1000
        logger.info(f"SemanticMatcher: SwarmEmbedder ready in {_embedder_load_time:.0f}ms")
    return _embedder


class SemanticMatcher:
    """
    FAISS-backed semantic similarity matcher for pattern triggers.
    
    Usage:
        matcher = SemanticMatcher()
        matcher.build_index(patterns)  # One-time at engine init
        results = matcher.search("got any wares?", top_k=3)
        # → [(pattern_dict, trigger_text, cosine_score), ...]
    """

    def __init__(self, similarity_floor: float = 0.12):
        """
        Args:
            similarity_floor: Minimum cosine similarity to return a match.
                              Below this, we treat it as "no semantic match".
                              0.15 is intentionally low — the hybrid scorer
                              handles final thresholding.  TF-IDF char n-gram
                              scores tend to be lower than neural embeddings.
        """
        self.similarity_floor = similarity_floor
        self._index = None            # FAISS IndexFlatIP
        self._trigger_texts: List[str] = []       # Parallel array: trigger string
        self._trigger_patterns: List[Dict] = []   # Parallel array: parent pattern dict
        self._trigger_is_generic: List[bool] = [] # Parallel array: generic flag
        self._n_triggers = 0
        self._build_time_ms = 0.0
        self._enabled = True

    def build_index(
        self,
        synthetic_patterns: List[Dict],
        generic_patterns: List[Dict],
    ) -> None:
        """
        Pre-embed all triggers and build the FAISS index.
        
        Called once at CognitiveEngine.__init__. Typically 20-200 triggers,
        so this takes <10ms on CPU with SwarmEmbedder.
        """
        try:
            import faiss
        except ImportError:
            self._enabled = False
            logger.warning("SemanticMatcher: FAISS not found, disabled")
            return
            
        if np is None:
            self._enabled = False
            logger.warning("SemanticMatcher: numpy not found, disabled")
            return

        start = time.time()
        embedder = _get_embedder()

        # Collect all (trigger_text, pattern_dict, is_generic) triples
        trigger_data = []
        for pat in synthetic_patterns:
            triggers = pat.get("trigger", [])
            if isinstance(triggers, str):
                triggers = [triggers]
            for t in triggers:
                trigger_data.append((t.strip(), pat, False))

        for pat in generic_patterns:
            triggers = pat.get("trigger", [])
            if isinstance(triggers, str):
                triggers = [triggers]
            for t in triggers:
                trigger_data.append((t.strip(), pat, True))

        if not trigger_data:
            self._enabled = False
            logger.warning("SemanticMatcher: no triggers to index, disabled")
            return

        # Store parallel arrays
        self._trigger_texts = [td[0] for td in trigger_data]
        self._trigger_patterns = [td[1] for td in trigger_data]
        self._trigger_is_generic = [td[2] for td in trigger_data]
        self._n_triggers = len(trigger_data)

        # Fit the embedder on the trigger corpus, then encode
        if not embedder.is_fitted:
            embedder.fit(self._trigger_texts)

        embeddings = embedder.embed_texts(self._trigger_texts)
        embeddings = np.array(embeddings, dtype=np.float32)

        # Build FAISS inner-product index (cosine sim on normalized vectors)
        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(embeddings)

        self._build_time_ms = (time.time() - start) * 1000
        logger.info(
            f"SemanticMatcher: indexed {self._n_triggers} triggers "
            f"in {self._build_time_ms:.0f}ms (dim={dim})"
        )

    def search(
        self,
        query: str,
        top_k: int = 3,
    ) -> List[Tuple[Dict, str, float, bool]]:
        """
        Find the top-K semantically similar triggers for a query.
        
        Returns:
            List of (pattern_dict, trigger_text, cosine_score, is_generic)
            sorted by score descending. Only scores >= similarity_floor.
        """
        if not self._enabled or self._index is None:
            return []

        embedder = _get_embedder()

        # Encode query
        q_emb = embedder.embed_texts([query])
        q_emb = np.array(q_emb, dtype=np.float32)

        # Search FAISS
        k = min(top_k, self._n_triggers)
        scores, indices = self._index.search(q_emb, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:  # FAISS returns -1 for unfilled slots
                continue
            if score < self.similarity_floor:
                continue
            results.append((
                self._trigger_patterns[idx],
                self._trigger_texts[idx],
                float(score),
                self._trigger_is_generic[idx],
            ))

        return results

    def get_best_match(
        self,
        query: str,
    ) -> Tuple[Optional[Dict], str, float, bool]:
        """
        Convenience: return the single best semantic match.
        
        Returns:
            (pattern_dict, trigger_text, cosine_score, is_generic)
            or (None, "", 0.0, False) if no match above floor.
        """
        results = self.search(query, top_k=1)
        if results:
            return results[0]
        return None, "", 0.0, False

    def get_stats(self) -> Dict[str, Any]:
        """Return matcher statistics."""
        dim = self._index.d if self._index else 128
        return {
            "enabled": self._enabled,
            "n_triggers": self._n_triggers,
            "build_time_ms": round(self._build_time_ms, 1),
            "model_load_time_ms": round(_embedder_load_time, 1),
            "similarity_floor": self.similarity_floor,
            "index_memory_kb": (
                self._n_triggers * dim * 4 / 1024  # float32 vectors
                if self._enabled else 0
            ),
        }
