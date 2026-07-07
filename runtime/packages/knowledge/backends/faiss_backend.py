"""
FAISS Backend — Wraps the existing RAGPipeline behind KAL's interface (V4).

This adapter delegates to core.rag_pipeline.RAGPipeline and converts
its Dict results into KalResult objects. Supports V4 namespace filtering.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from ..schemas import KalQuery, KalResult, KalKnowledgeNode
from .base import KalBackend

logger = logging.getLogger(__name__)


class FaissKalBackend(KalBackend):
    """KAL backend that wraps the existing RAGPipeline (FAISS + SwarmEmbedder)."""

    def __init__(self, rag_pipeline: Any) -> None:
        """
        Args:
            rag_pipeline: An instance of core.rag_pipeline.RAGPipeline.
                          Typed as Any to avoid a hard import dependency here;
                          duck-typing is sufficient (needs .retrieve()).
        """
        self._rag = rag_pipeline

    async def query(self, kal_query: KalQuery) -> KalResult:
        """
        Translate a KalQuery into a RAGPipeline.retrieve() call and map
        the results back into KalResult.
        """
        start = time.time()

        # Extract character_id from filters if present
        character_id: Optional[str] = kal_query.filters.get("character_id")

        # V4: Request more results (10x top_k) from RAG to allow for deep namespace/domain filtering
        search_k = max(kal_query.top_k * 10, 50)
        
        # V4: Adaptive thresholding. Lower threshold for targeted namespaces.
        threshold = 0.1 if kal_query.effective_namespaces else 0.4

        # Delegate to the existing async retrieve method. Older RAGPipeline
        # implementations do not accept the V4 namespace/threshold keywords,
        # so preserve compatibility and perform namespace filtering locally.
        try:
            rag_result = await self._rag.retrieve(
                query=kal_query.query,
                character_id=character_id,
                namespaces=kal_query.effective_namespaces,
                top_k=search_k,
                score_threshold=threshold,
            )
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            rag_result = await self._rag.retrieve(
                query=kal_query.query,
                character_id=character_id,
                top_k=search_k,
            )

        # Map RAG sources → KalKnowledgeNodes
        items: List[KalKnowledgeNode] = []
        sources = rag_result.get("sources", [])
        context_str = rag_result.get("context", "")

        # Each source dict has: pattern, score, character
        # The full context string has the Q/A pairs joined.
        context_parts = context_str.split("\n\n") if context_str else []
        effective_ns = kal_query.effective_namespaces

        for i, src in enumerate(sources):
            # ...
            # Build the text from the context part if available, else from pattern
            text = context_parts[i] if i < len(context_parts) else src.get("pattern", "")
            if not text:
                text = src.get("response", "") or src.get("pattern", "No content available")

            # V4: Use explicitly stored namespace from rag_pipeline if available, else derive it
            namespace = src.get("namespace")
            source_domain = src.get("domain", "")
            char = src.get("character", src.get("character_id", "global"))
            
            if not namespace or namespace == "general":
                if source_domain:
                    # Map domain to namespace if namespace was general but domain exists (V3 compat)
                    namespace = source_domain
                elif char and char != "global":
                    namespace = "character_genome"
                else:
                    namespace = "general"


            # V4: Namespace filtering — skip results outside requested namespaces
            if effective_ns and namespace not in effective_ns:
                continue

            items.append(
                KalKnowledgeNode(
                    node_id=str(uuid.uuid4()),
                    content=text if kal_query.include_raw else "",
                    confidence=src.get("score", 0.0),
                    source_namespace=namespace,
                    metadata={
                        "source": src.get("pattern", ""),
                        "timestamp": "",
                        "trust_level": "medium",
                        "tags": [],
                        "character": char,
                        "domain": source_domain,
                    },
                )
            )

        # Respect the original top_k request after filtering
        items = items[:kal_query.top_k]

        latency_ms = (time.time() - start) * 1000

        return KalResult(
            results=items,
            retrieval_latency_ms=round(latency_ms, 2),
            cache_hit=False,
            debug={
                "backend_name": "faiss",
                "index_vectors": getattr(self._rag, "total_vectors", 0),
                "latency_ms": round(latency_ms, 2),
                "mode": kal_query.mode,
                "namespaces_requested": effective_ns,
            },
        )
