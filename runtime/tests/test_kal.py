"""
KAL Unit Tests — V4 schemas, backends, service (with cache), client, and partitions.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kal.schemas import KalQuery, KalKnowledgeNode, KalResultItem, KalResult, KalMode, KalNamespace
from kal.service import KalService
from kal.client import KalClient
from kal.config import KalConfig, load_kal_config
from kal.partitions import (
    GameLorePartition,
    ArchitectDirectivesPartition,
    CharacterGenomePartition,
    ReasoningRulesPartition,
    AutonomyLevel,
    validate_partition_metadata,
)
from kal.backends.faiss_backend import FaissKalBackend


# ══════════════════════════════════════════════════
# Schema Tests (V4)
# ══════════════════════════════════════════════════


class TestKalQueryV4:
    def test_defaults(self):
        q = KalQuery(query="hello world")
        assert q.query == "hello world"
        assert q.mode == KalMode.SEMANTIC_GRAPH
        assert q.namespaces == []
        assert q.domains == []
        assert q.context_vector is None
        assert q.max_latency_ms == 5.0
        assert q.top_k == 8

    def test_exact_match_mode(self):
        q = KalQuery(query="test", mode=KalMode.EXACT_MATCH, max_latency_ms=0.5)
        assert q.mode == "exact_match"
        assert q.max_latency_ms == 0.5

    def test_namespaces(self):
        q = KalQuery(
            query="test",
            namespaces=["game_lore", "character_genome"],
        )
        assert q.effective_namespaces == ["game_lore", "character_genome"]

    def test_domains_fallback(self):
        """V3 domains field should be accessible via effective_namespaces."""
        q = KalQuery(query="test", domains=["general"])
        assert q.effective_namespaces == ["general"]

    def test_namespaces_take_priority(self):
        q = KalQuery(
            query="test",
            namespaces=["character_genome"],
            domains=["general"],
        )
        assert q.effective_namespaces == ["character_genome"]

    def test_context_vector(self):
        vec = [0.1] * 128
        q = KalQuery(query="test", context_vector=vec)
        assert len(q.context_vector) == 128

    def test_serialization_roundtrip(self):
        q = KalQuery(query="test", namespaces=["game_lore"], mode=KalMode.EXACT_MATCH)
        data = q.model_dump()
        q2 = KalQuery(**data)
        assert q == q2


class TestKalKnowledgeNode:
    def test_defaults(self):
        node = KalKnowledgeNode(node_id="1", content="passage", confidence=0.9)
        assert node.source_namespace == "general"
        assert node.metadata["trust_level"] == "medium"

    def test_full_node(self):
        node = KalKnowledgeNode(
            node_id="abc",
            content="lore text",
            confidence=0.85,
            source_namespace="game_lore",
            metadata={
                "source": "wiki",
                "timestamp": "2025-01-01",
                "trust_level": "high",
                "tags": ["canon"],
                "faction": "alliance",
            },
        )
        assert node.source_namespace == "game_lore"
        assert node.metadata["faction"] == "alliance"


class TestKalResultItemCompat:
    """V3 KalResultItem should still work as an alias."""

    def test_v3_properties(self):
        item = KalResultItem(node_id="1", content="text", confidence=0.8)
        assert item.id == "1"
        assert item.text == "text"
        assert item.score == 0.8
        assert item.domain == "general"


class TestKalResultV4:
    def test_new_fields(self):
        r = KalResult(
            results=[KalKnowledgeNode(node_id="1", content="a", confidence=0.8)],
            retrieval_latency_ms=1.5,
            cache_hit=True,
        )
        assert r.retrieval_latency_ms == 1.5
        assert r.cache_hit is True
        assert len(r.results) == 1


# ══════════════════════════════════════════════════
# Partition Tests
# ══════════════════════════════════════════════════


class TestPartitions:
    def test_game_lore_partition(self):
        p = GameLorePartition(faction="alliance", temporal_epoch=3)
        assert p.faction == "alliance"
        assert p.temporal_epoch == 3

    def test_architect_directives(self):
        p = ArchitectDirectivesPartition(
            autonomy_level=AutonomyLevel.COPILOT,
            tool_whitelist=["web_search"],
            safety_override=True,
        )
        assert p.autonomy_level == "COPILOT"
        assert p.safety_override is True

    def test_character_genome(self):
        p = CharacterGenomePartition(
            archetype="merchant",
            relationship_trust_gate=0.7,
            emotion_trigger="anger",
        )
        assert p.archetype == "merchant"

    def test_reasoning_rules(self):
        p = ReasoningRulesPartition(synthetic_core_priority=5, requires_escalation=True)
        assert p.requires_escalation is True

    def test_validate_known_namespace(self):
        result = validate_partition_metadata(
            "game_lore", {"faction": "horde", "temporal_epoch": 2, "extra_key": "ignored"}
        )
        assert isinstance(result, GameLorePartition)
        assert result.faction == "horde"

    def test_validate_unknown_namespace(self):
        result = validate_partition_metadata("unknown_ns", {"foo": "bar"})
        assert result is None


# ══════════════════════════════════════════════════
# Config Tests (V4)
# ══════════════════════════════════════════════════


class TestKalConfigV4:
    def test_v4_defaults(self):
        cfg = KalConfig()
        assert cfg.cache_size == 1024
        assert cfg.ivf_nlist == 100
        assert cfg.left_hemisphere_latency_ms == 0.5
        assert cfg.right_hemisphere_latency_ms == 5.0

    def test_load_v4_config(self):
        cfg = load_kal_config(str(ROOT / "config.yaml"))
        assert cfg.cache_size == 1024
        assert cfg.ivf_nlist == 100


# ══════════════════════════════════════════════════
# Backend Tests (mocked RAG)
# ══════════════════════════════════════════════════


class TestFaissKalBackendV4:
    @pytest.fixture
    def mock_rag(self):
        rag = MagicMock()
        rag.total_vectors = 100

        async def fake_retrieve(query, character_id=None, top_k=5):
            return {
                "context": "Q: What is lore?\nA: Ancient knowledge",
                "sources": [
                    {"pattern": "What is lore?", "score": 0.85, "character": "global", "domain": "game_lore"},
                ],
            }

        rag.retrieve = fake_retrieve
        return rag

    @pytest.mark.asyncio
    async def test_returns_knowledge_nodes(self, mock_rag):
        backend = FaissKalBackend(mock_rag)
        q = KalQuery(query="Tell me about lore", top_k=5)
        result = await backend.query(q)

        assert isinstance(result, KalResult)
        assert len(result.results) == 1
        assert isinstance(result.results[0], KalKnowledgeNode)
        assert result.results[0].confidence == 0.85
        assert result.retrieval_latency_ms > 0
        assert result.cache_hit is False

    @pytest.mark.asyncio
    async def test_namespace_filtering(self, mock_rag):
        """With namespaces=["character_genome"], game_lore results should be filtered out."""
        backend = FaissKalBackend(mock_rag)
        q = KalQuery(query="test", namespaces=["character_genome"])
        result = await backend.query(q)
        assert len(result.results) == 0  # game_lore doesn't match

    @pytest.mark.asyncio
    async def test_matching_namespace(self, mock_rag):
        backend = FaissKalBackend(mock_rag)
        q = KalQuery(query="test", namespaces=["game_lore"])
        result = await backend.query(q)
        assert len(result.results) == 1
        assert result.results[0].source_namespace == "game_lore"


# ══════════════════════════════════════════════════
# Service Cache Tests
# ══════════════════════════════════════════════════


class TestKalServiceCache:
    @pytest.fixture
    def mock_backend(self):
        expected = KalResult(
            results=[KalKnowledgeNode(node_id="1", content="cached text", confidence=0.9)],
            retrieval_latency_ms=2.0,
        )
        backend = MagicMock()
        backend.query = AsyncMock(return_value=expected)
        return backend

    @pytest.mark.asyncio
    async def test_semantic_graph_bypasses_cache(self, mock_backend):
        service = KalService(backend=mock_backend, cache_size=10)
        q = KalQuery(query="test", mode=KalMode.SEMANTIC_GRAPH)

        # Two identical queries → backend called both times (no caching)
        await service.query(q)
        await service.query(q)
        assert mock_backend.query.await_count == 2

    @pytest.mark.asyncio
    async def test_exact_match_uses_cache(self, mock_backend):
        service = KalService(backend=mock_backend, cache_size=10)
        q = KalQuery(query="test", mode=KalMode.EXACT_MATCH)

        r1 = await service.query(q)
        r2 = await service.query(q)

        # Backend should only be called ONCE — second call hits cache
        assert mock_backend.query.await_count == 1
        assert r2.cache_hit is True
        assert r2.retrieval_latency_ms < 1.0  # Cache should be fast

    @pytest.mark.asyncio
    async def test_cache_stats(self, mock_backend):
        service = KalService(backend=mock_backend, cache_size=10)
        q = KalQuery(query="test", mode=KalMode.EXACT_MATCH)

        await service.query(q)
        await service.query(q)

        stats = service.get_cache_stats()
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 1
        assert stats["hit_rate"] == 0.5


# ══════════════════════════════════════════════════
# Client Tests (V4)
# ══════════════════════════════════════════════════


class TestKalClientV4:
    @pytest.mark.asyncio
    async def test_query_exact_helper(self):
        mock_service = MagicMock()
        mock_service.query = AsyncMock(return_value=KalResult())
        client = KalClient(service=mock_service)

        await client.query_exact("Hello?", namespaces=["character_genome"])

        call_args = mock_service.query.call_args[0][0]
        assert call_args.mode == KalMode.EXACT_MATCH
        assert call_args.max_latency_ms == 0.5
        assert call_args.namespaces == ["character_genome"]

    @pytest.mark.asyncio
    async def test_query_semantic_helper(self):
        mock_service = MagicMock()
        mock_service.query = AsyncMock(return_value=KalResult())
        client = KalClient(service=mock_service)

        await client.query_semantic("What about the lore?", top_k=3)

        call_args = mock_service.query.call_args[0][0]
        assert call_args.mode == KalMode.SEMANTIC_GRAPH
        assert call_args.max_latency_ms == 5.0
        assert call_args.top_k == 3

    @pytest.mark.asyncio
    async def test_v3_compat_query_knowledge(self):
        mock_service = MagicMock()
        mock_service.query = AsyncMock(return_value=KalResult())
        client = KalClient(service=mock_service, default_domains=["general"])

        await client.query_knowledge("test")

        call_args = mock_service.query.call_args[0][0]
        assert call_args.domains == ["general"]
        assert call_args.mode == KalMode.SEMANTIC_GRAPH

    @pytest.mark.asyncio
    async def test_context_vector_passthrough(self):
        mock_service = MagicMock()
        mock_service.query = AsyncMock(return_value=KalResult())
        client = KalClient(service=mock_service)

        vec = [0.1] * 128
        await client.query_semantic("test", context_vector=vec)

        call_args = mock_service.query.call_args[0][0]
        assert call_args.context_vector == vec
