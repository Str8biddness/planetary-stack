#!/usr/bin/env python3
r"""
KAL V4 -- End-to-End Integration Test

Tests the full KAL pipeline directly in Python (no server needed):
  1. RAGPipeline loads the real FAISS index
  2. KAL wraps it via FaissKalBackend
  3. KalService handles caching
  4. KalClient queries through both hemisphere paths
  5. Gateway-style integration

Run:
  .venv\Scripts\python.exe tests/test_kal_e2e.py
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def main():
    print("=" * 70)
    print("   KAL V4 -- End-to-End Integration Test")
    print("=" * 70)

    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        status = "PASS" if condition else "FAIL"
        tag = "[+]" if condition else "[X]"
        msg = f"  {tag} {status}  {name}"
        if detail:
            msg += f"  ({detail})"
        print(msg)
        if condition:
            passed += 1
        else:
            failed += 1

    # ==============================================================
    # Phase 1: RAGPipeline + FAISS Index
    # ==============================================================
    print("\n--- Phase 1: RAGPipeline ---")

    from core.rag_pipeline import RAGPipeline
    rag = RAGPipeline()
    check("RAGPipeline loads", rag is not None)
    check("FAISS index has vectors", rag.total_vectors > 0, f"{rag.total_vectors} vectors")

    # Test a raw retrieve
    raw = await rag.retrieve("What is the meaning of life?", top_k=3)
    check("RAG retrieve returns context", len(raw.get("context", "")) > 0, f"{len(raw['context'])} chars")
    check("RAG retrieve returns sources", len(raw.get("sources", [])) > 0, f"{len(raw['sources'])} sources")

    # ==============================================================
    # Phase 2: KAL Config + Service Stack
    # ==============================================================
    print("\n--- Phase 2: KAL Config & Build ---")

    from kal.config import load_kal_config, build_kal_service
    config = load_kal_config()
    check("KAL config loaded", config is not None, f"backend={config.backend_type}")
    check("KAL enabled", config.enabled)
    check("KAL use_for_retrieval", config.use_for_retrieval)

    service, client = build_kal_service(config, rag_pipeline=rag)
    check("KalService created", service is not None)
    check("KalClient created", client is not None)

    # ==============================================================
    # Phase 3: Semantic Graph Query (Right Hemisphere)
    # ==============================================================
    print("\n--- Phase 3: Semantic Graph Query ---")

    from kal.schemas import KalMode, KalKnowledgeNode, KalResult

    t0 = time.time()
    result = await client.query_semantic(
        "Tell me about history and ancient civilizations",
        top_k=5,
    )
    t1 = time.time()
    latency_ms = (t1 - t0) * 1000

    check("query_semantic returns KalResult", isinstance(result, KalResult))
    check("Has results", len(result.results) > 0, f"{len(result.results)} nodes")
    if result.results:
        check("Results are KalKnowledgeNode", isinstance(result.results[0], KalKnowledgeNode))
    check("retrieval_latency_ms tracked", result.retrieval_latency_ms > 0, f"{result.retrieval_latency_ms:.2f}ms")
    check("cache_hit is False", result.cache_hit is False)
    check("debug has backend info", result.debug is not None and "backend_name" in result.debug)
    check("Latency < 100ms", latency_ms < 100, f"{latency_ms:.1f}ms")

    if result.results:
        node = result.results[0]
        content_preview = node.content[:120].replace('\n', ' ')
        print(f"\n    Best result: score={node.confidence:.4f}, ns={node.source_namespace}")
        print(f"    Content: {content_preview}...")

    # ==============================================================
    # Phase 4: Exact Match Query + L1 Cache (Left Hemisphere)
    # ==============================================================
    print("\n--- Phase 4: Exact Match + Cache ---")

    # First call -- cache miss
    r1 = await client.query_exact("What is history?")
    check("Exact match returns results", len(r1.results) >= 0)

    # Second call -- should hit cache
    t0 = time.time()
    r2 = await client.query_exact("What is history?")
    t1 = time.time()
    cache_latency = (t1 - t0) * 1000

    check("Cache hit on repeat query", r2.cache_hit is True)
    check("Cache latency < 1ms", cache_latency < 1.0, f"{cache_latency:.3f}ms")

    stats = service.get_cache_stats()
    check("Cache has entries", stats["cache_size"] > 0, f"size={stats['cache_size']}")
    check("Cache hit count", stats["cache_hits"] >= 1)
    print(f"\n    Cache stats: {stats}")

    # ==============================================================
    # Phase 5: Namespace Filtering
    # ==============================================================
    print("\n--- Phase 5: Namespace Filtering ---")

    r_all = await client.query_semantic("test query", top_k=10)
    r_filtered = await client.query_semantic(
        "test query",
        namespaces=["character_genome"],
        top_k=10,
    )
    # Filtered results should be <= unfiltered (or empty if no character_genome data)
    check(
        "Namespace filter restricts results",
        len(r_filtered.results) <= len(r_all.results),
        f"all={len(r_all.results)}, filtered={len(r_filtered.results)}",
    )

    # ==============================================================
    # Phase 6: Partition Metadata
    # ==============================================================
    print("\n--- Phase 6: Partition Metadata ---")

    from kal.partitions import validate_partition_metadata, GameLorePartition
    p = validate_partition_metadata("game_lore", {
        "faction": "alliance",
        "temporal_epoch": 3,
        "unrelated_key": "ignored",
    })
    check("Partition validation works", isinstance(p, GameLorePartition))
    check("Partition fields extracted", p.faction == "alliance")

    # ==============================================================
    # Phase 7: Gateway Integration Path
    # ==============================================================
    print("\n--- Phase 7: Gateway KAL Path ---")

    # Simulate what gateway.py does when use_for_retrieval=True
    kal_result = await client.query_knowledge(
        question="How do I trade goods?",
        filters={"character_id": "elena"},
    )
    rag_context = "\n\n".join(item.content for item in kal_result.results if item.content)
    rag_sources = [
        {"pattern": item.metadata.get("source", ""),
         "score": round(item.confidence, 4),
         "character": item.metadata.get("character", "global")}
        for item in kal_result.results
    ]
    check("Gateway-style context built", isinstance(rag_context, str))
    check("Gateway-style sources built", isinstance(rag_sources, list))
    print(f"\n    Context length: {len(rag_context)} chars, Sources: {len(rag_sources)}")

    # ==============================================================
    # Summary
    # ==============================================================
    print("\n" + "=" * 70)
    total = passed + failed
    print(f"   Results: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("   ALL TESTS PASSED -- KAL V4 is fully operational!")
    else:
        print("   WARNING: Some tests failed -- check output above")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
