"""
KAL Service — V4 Orchestrator with L1 Cache.

Provides two retrieval paths:
  - exact_match (Left Hemisphere): LRU cache lookup → sub-millisecond
  - semantic_graph (Right Hemisphere): full backend query → bounded by latency budget

Future home for:
  - Domain fallback chains
  - Result re-ranking / deduplication
  - Multi-backend fan-out and merge
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from typing import Optional

from .backends.base import KalBackend
from .schemas import KalMode, KalQuery, KalResult

logger = logging.getLogger(__name__)


class _LRUCache:
    """Simple thread-safe-ish LRU cache for KalResult objects."""

    def __init__(self, max_size: int = 1024):
        self._max_size = max_size
        self._store: OrderedDict[str, KalResult] = OrderedDict()

    @staticmethod
    def _key(query: KalQuery) -> str:
        """Build a cache key from the query text + namespaces + filters."""
        raw = f"{query.query}|{sorted(query.effective_namespaces)}|{sorted(query.filters.items())}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, query: KalQuery) -> Optional[KalResult]:
        key = self._key(query)
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]
        return None

    def put(self, query: KalQuery, result: KalResult) -> None:
        key = self._key(query)
        self._store[key] = result
        self._store.move_to_end(key)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    @property
    def size(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()


class KalService:
    """Orchestrates knowledge retrieval through a pluggable backend (V4).

    Adds an L1 LRU cache for exact_match mode, providing sub-millisecond
    responses for repeated Left Hemisphere queries.
    """

    def __init__(
        self,
        backend: KalBackend,
        cache_size: int = 1024,
    ) -> None:
        self.backend = backend
        self._cache = _LRUCache(max_size=cache_size)
        self._cache_hits = 0
        self._cache_misses = 0

    async def query(self, kal_query: KalQuery) -> KalResult:
        """Route query through cache or backend based on mode."""
        start = time.time()

        # ── exact_match path: check L1 cache first ──
        if kal_query.mode == KalMode.EXACT_MATCH:
            cached = self._cache.get(kal_query)
            if cached is not None:
                latency_ms = (time.time() - start) * 1000
                self._cache_hits += 1
                logger.debug("KalService: cache HIT (%.2fms)", latency_ms)
                # Return cached result with updated latency + cache_hit flag
                return KalResult(
                    results=cached.results,
                    retrieval_latency_ms=round(latency_ms, 2),
                    cache_hit=True,
                    debug={**(cached.debug or {}), "cache_hit": True, "latency_ms": round(latency_ms, 2)},
                )
            self._cache_misses += 1

        # ── Backend query ──
        logger.debug(
            "KalService.query: mode=%s namespaces=%s top_k=%d",
            kal_query.mode, kal_query.effective_namespaces, kal_query.top_k,
        )
        result = await self.backend.query(kal_query)

        # Cache the result for exact_match mode (even empty results, to avoid re-query)
        if kal_query.mode == KalMode.EXACT_MATCH:
            self._cache.put(kal_query, result)

        return result

    def get_cache_stats(self) -> dict:
        """Return cache statistics."""
        return {
            "cache_size": self._cache.size,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": (
                round(self._cache_hits / max(self._cache_hits + self._cache_misses, 1), 4)
            ),
        }

    def clear_cache(self) -> None:
        """Clear the L1 cache."""
        self._cache.clear()
        logger.info("KalService: L1 cache cleared")
