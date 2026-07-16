"""
KAL Client — The public API for Synthesus Core (V4).

Core modules call KalClient.query_knowledge(...) without knowing anything
about FAISS, embeddings, or storage backends.

V4 adds hemisphere-aware helper methods:
  - query_exact()   → Left Hemisphere cached path
  - query_semantic() → Right Hemisphere full search
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schemas import KalMode, KalQuery, KalResult
from .service import KalService


class KalClient:
    """High-level knowledge retrieval client for Synthesus Core (V4)."""

    def __init__(
        self,
        service: KalService,
        default_domains: Optional[List[str]] = None,
    ) -> None:
        self.service = service
        self.default_domains = default_domains or []

    async def query_knowledge(
        self,
        question: str,
        domains: Optional[List[str]] = None,
        namespaces: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 8,
        include_raw: bool = True,
        mode: str = KalMode.SEMANTIC_GRAPH,
        max_latency_ms: float = 5.0,
        context_vector: Optional[List[float]] = None,
    ) -> KalResult:
        """Build a KalQuery and delegate to the KAL service.

        Args:
            question:       Natural language question or search text.
            domains:        V3 compat — aliases to namespaces.
            namespaces:     V4 namespace partitions to search.
            filters:        Metadata filters (e.g. character_id, trust_level).
            top_k:          Number of results to return.
            include_raw:    Whether to include raw text in results.
            mode:           "exact_match" or "semantic_graph".
            max_latency_ms: Strict latency budget.
            context_vector: Pre-computed embedding (skips re-embedding).

        Returns:
            KalResult containing ranked retrieval hits.
        """
        kal_query = KalQuery(
            query=question,
            mode=mode,
            namespaces=namespaces or [],
            domains=domains or self.default_domains,
            filters=filters or {},
            top_k=top_k,
            include_raw=include_raw,
            max_latency_ms=max_latency_ms,
            context_vector=context_vector,
        )
        return await self.service.query(kal_query)

    # ── V4 Hemisphere-Specific Helpers ──

    async def query_exact(
        self,
        question: str,
        namespaces: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> KalResult:
        """Left Hemisphere path — sub-ms cached lookup.

        Uses exact_match mode with a tight 0.5ms latency budget.
        Results are LRU-cached in the service layer.
        """
        return await self.query_knowledge(
            question=question,
            namespaces=namespaces,
            filters=filters,
            top_k=top_k,
            mode=KalMode.EXACT_MATCH,
            max_latency_ms=0.5,
        )

    async def query_semantic(
        self,
        question: str,
        namespaces: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 8,
        context_vector: Optional[List[float]] = None,
    ) -> KalResult:
        """Right Hemisphere path — full semantic search.

        Uses semantic_graph mode with a 5.0ms latency budget.
        Supports pre-computed context vectors to skip re-embedding.
        """
        return await self.query_knowledge(
            question=question,
            namespaces=namespaces,
            filters=filters,
            top_k=top_k,
            mode=KalMode.SEMANTIC_GRAPH,
            max_latency_ms=5.0,
            context_vector=context_vector,
        )
