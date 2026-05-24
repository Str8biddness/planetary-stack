"""
KAL Schemas — V4 Query and Result contracts for the Knowledge Abstraction Layer.

V4 additions:
- Hemisphere-aware mode (exact_match / semantic_graph)
- Namespace-based partitioning (replaces flat domains)
- Latency budgets
- Cache hit tracking
- KalKnowledgeNode (richer result model)

All Synthesus modules that consume knowledge should go through these models,
ensuring a stable interface regardless of the underlying backend (FAISS, IVFFlat,
future Qdrant, etc.).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────

class KalMode(str, Enum):
    """Query mode that controls the retrieval strategy."""
    EXACT_MATCH = "exact_match"       # Left Hemisphere — sub-millisecond cached/pattern lookup
    SEMANTIC_GRAPH = "semantic_graph"  # Right Hemisphere — full FAISS semantic search


class KalNamespace(str, Enum):
    """Well-known namespace partitions for domain-aware retrieval."""
    GAME_LORE = "game_lore"
    CHARACTER_GENOME = "character_genome"
    ARCHITECT_DIRECTIVES = "architect_directives"
    REASONING_RULES = "reasoning_rules"
    GENERAL = "general"


# ──────────────────────────────────────────────────
# Query
# ──────────────────────────────────────────────────

class KalQuery(BaseModel):
    """A knowledge retrieval request (V4)."""

    query: str = Field(..., description="Natural language question or search text.")

    # V4: Hemisphere routing
    mode: str = Field(
        default=KalMode.SEMANTIC_GRAPH,
        description=(
            "Retrieval mode: 'exact_match' (Left Hemisphere, sub-ms cache path) "
            "or 'semantic_graph' (Right Hemisphere, full semantic search)."
        ),
    )

    # V4: Namespace-based partitioning (supercedes flat domains)
    namespaces: List[str] = Field(
        default_factory=list,
        description=(
            "Namespace partitions to search, e.g. 'game_lore', 'character_genome'. "
            "Empty list means search all default namespaces."
        ),
    )

    # V4: Pre-computed embedding (skip re-embedding if caller already has it)
    context_vector: Optional[List[float]] = Field(
        default=None,
        description="Pre-computed 128-dim SwarmEmbedder vector. Skips re-embedding if provided.",
    )

    # V4: Latency budget
    max_latency_ms: float = Field(
        default=5.0,
        description="Strict latency budget in ms. exact_match should use ~0.5, semantic_graph ~5.0.",
    )

    # Carried from V3
    domains: List[str] = Field(
        default_factory=list,
        description="(V3 compat) — aliases to namespaces; prefer namespaces.",
    )
    filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata filters, e.g. {'character_id': 'elena', 'trust_level': 'high'}.",
    )
    top_k: int = Field(default=8, ge=1, le=100, description="Number of results to return.")
    include_raw: bool = Field(
        default=True,
        description="Whether to include raw text in results.",
    )
    must_tags: List[str] = Field(
        default_factory=list,
        description="Results MUST have all of these tags.",
    )
    should_tags: List[str] = Field(
        default_factory=list,
        description="Results SHOULD have at least one of these tags (soft boost).",
    )

    @property
    def effective_namespaces(self) -> List[str]:
        """Resolve namespaces: prefer explicit namespaces, fall back to domains."""
        return self.namespaces or self.domains or []


# ──────────────────────────────────────────────────
# Result items
# ──────────────────────────────────────────────────

class KalKnowledgeNode(BaseModel):
    """A single knowledge retrieval hit (V4 — richer than V3 KalResultItem)."""

    node_id: str = Field(..., description="Unique ID for this knowledge node.")
    content: str = Field(..., description="Retrieved passage / chunk text.")
    confidence: float = Field(..., description="Relevance / similarity score (0-1).")
    source_namespace: str = Field(
        default="general",
        description="Namespace partition this node belongs to.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=lambda: {
            "source": "",
            "timestamp": "",
            "trust_level": "medium",
            "tags": [],
        },
        description=(
            "Metadata dict — at minimum: source, timestamp, trust_level, tags. "
            "May also include partition-specific fields (faction, archetype, etc.)."
        ),
    )


# V3 backward compat alias
class KalResultItem(KalKnowledgeNode):
    """Deprecated alias for KalKnowledgeNode. Use KalKnowledgeNode in new code."""

    @property
    def id(self) -> str:
        return self.node_id

    @property
    def text(self) -> str:
        return self.content

    @property
    def score(self) -> float:
        return self.confidence

    @property
    def domain(self) -> str:
        return self.source_namespace


# ──────────────────────────────────────────────────
# Top-level result
# ──────────────────────────────────────────────────

class KalResult(BaseModel):
    """Top-level response from a KAL query (V4)."""

    results: List[KalKnowledgeNode] = Field(default_factory=list)

    # V4 additions
    retrieval_latency_ms: float = Field(
        default=0.0,
        description="Actual retrieval latency in milliseconds.",
    )
    cache_hit: bool = Field(
        default=False,
        description="True if the result was served from L1 cache (exact_match mode).",
    )

    debug: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Backend debug info (backend_name, index_used, latency_ms, etc.).",
    )
