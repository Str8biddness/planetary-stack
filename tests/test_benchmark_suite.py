"""
Tests for Phase 18: Benchmark Suite + Demo Reel

Tests cover:
- Benchmark function return structure validation
- Pattern matching benchmark
- Full pipeline benchmark
- Memory per NPC benchmark
- NPC scaling benchmark
- Social fabric tick benchmark
- Save/Load benchmark
- Kernel bridge benchmark
- Comparison data generation
- Full suite runner
- Demo reel imports and NPC creation
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from benchmark_suite import (
    benchmark_pattern_matching,
    benchmark_full_pipeline,
    benchmark_memory_per_npc,
    benchmark_npc_scaling,
    benchmark_social_fabric,
    benchmark_save_load,
    benchmark_kernel_bridge,
    generate_comparison,
    run_all_benchmarks,
    SAMPLE_BIO,
    SAMPLE_PATTERNS,
    TEST_QUERIES,
)


# ── Test Data Validation ──

class TestBenchmarkData:
    """Validate test data constants."""

    def test_sample_bio_has_required_fields(self):
        assert "name" in SAMPLE_BIO
        assert "role" in SAMPLE_BIO
        assert "personality" in SAMPLE_BIO
        assert "backstory" in SAMPLE_BIO

    def test_sample_patterns_has_required_keys(self):
        assert "synthetic_patterns" in SAMPLE_PATTERNS
        assert "generic_patterns" in SAMPLE_PATTERNS
        assert "fallback" in SAMPLE_PATTERNS

    def test_sample_patterns_count(self):
        assert len(SAMPLE_PATTERNS["synthetic_patterns"]) == 15
        assert len(SAMPLE_PATTERNS["generic_patterns"]) == 4

    def test_each_pattern_has_required_fields(self):
        for p in SAMPLE_PATTERNS["synthetic_patterns"]:
            assert "id" in p
            assert "triggers" in p
            assert "response_template" in p
            assert "topic" in p

    def test_test_queries_count(self):
        assert len(TEST_QUERIES) == 20

    def test_test_queries_are_strings(self):
        for q in TEST_QUERIES:
            assert isinstance(q, str)
            assert len(q) > 0


# ── Pattern Matching Benchmark ──

class TestPatternMatchingBenchmark:
    """Test the pattern matching benchmark."""

    def test_returns_valid_structure(self):
        result = benchmark_pattern_matching(n_iterations=5)
        assert result["name"] == "Pattern Matching"
        assert "iterations" in result
        assert "avg_ms" in result
        assert "p50_ms" in result
        assert "p95_ms" in result
        assert "p99_ms" in result
        assert "min_ms" in result
        assert "max_ms" in result

    def test_iterations_count(self):
        result = benchmark_pattern_matching(n_iterations=10)
        # 10 iterations * 5 queries = 50
        assert result["iterations"] == 50

    def test_latency_values_are_positive(self):
        result = benchmark_pattern_matching(n_iterations=5)
        assert result["avg_ms"] > 0
        assert result["min_ms"] > 0
        assert result["max_ms"] >= result["min_ms"]

    def test_percentiles_are_ordered(self):
        result = benchmark_pattern_matching(n_iterations=20)
        assert result["min_ms"] <= result["p50_ms"]
        assert result["p50_ms"] <= result["p95_ms"]
        assert result["p95_ms"] <= result["max_ms"]

    def test_pattern_matching_is_fast(self):
        """Pattern matching should be sub-millisecond."""
        result = benchmark_pattern_matching(n_iterations=50)
        assert result["avg_ms"] < 1.0, f"Pattern matching too slow: {result['avg_ms']}ms"


# ── Full Pipeline Benchmark ──

class TestFullPipelineBenchmark:
    """Test the full cognitive pipeline benchmark."""

    def test_returns_valid_structure(self):
        result = benchmark_full_pipeline(n_iterations=10)
        assert result["name"] == "Full Cognitive Pipeline"
        assert result["iterations"] == 10
        assert "avg_ms" in result

    def test_pipeline_completes(self):
        result = benchmark_full_pipeline(n_iterations=5)
        assert result["avg_ms"] > 0

    def test_pipeline_is_fast(self):
        """Full pipeline should be under 5ms."""
        result = benchmark_full_pipeline(n_iterations=20)
        assert result["avg_ms"] < 5.0, f"Pipeline too slow: {result['avg_ms']}ms"


# ── Memory Per NPC Benchmark ──

class TestMemoryBenchmark:
    """Test memory footprint measurement."""

    def test_returns_valid_structure(self):
        result = benchmark_memory_per_npc(n_npcs=5)
        assert result["name"] == "Memory Per NPC"
        assert "npc_count" in result
        assert "total_mb" in result
        assert "peak_mb" in result
        assert "per_npc_kb" in result
        assert "note" in result

    def test_npc_count_matches(self):
        result = benchmark_memory_per_npc(n_npcs=10)
        assert result["npc_count"] == 10

    def test_memory_values_are_positive(self):
        result = benchmark_memory_per_npc(n_npcs=5)
        assert result["total_mb"] > 0
        assert result["per_npc_kb"] > 0

    def test_peak_exceeds_current(self):
        result = benchmark_memory_per_npc(n_npcs=10)
        assert result["peak_mb"] >= result["total_mb"]

    def test_per_npc_memory_is_small(self):
        """Each NPC should use less than 100KB."""
        result = benchmark_memory_per_npc(n_npcs=20)
        assert result["per_npc_kb"] < 100, f"NPC memory too high: {result['per_npc_kb']}KB"


# ── NPC Scaling Benchmark ──

class TestNPCScalingBenchmark:
    """Test NPC scaling benchmark."""

    def test_returns_valid_structure(self):
        result = benchmark_npc_scaling()
        assert result["name"] == "NPC Scaling"
        assert "results" in result
        assert len(result["results"]) == 3

    def test_scaling_results_have_npc_counts(self):
        result = benchmark_npc_scaling()
        counts = [r["npc_count"] for r in result["results"]]
        assert counts == [10, 50, 100]

    def test_each_result_has_latency(self):
        result = benchmark_npc_scaling()
        for r in result["results"]:
            assert "avg_ms" in r
            assert "p95_ms" in r
            assert r["avg_ms"] > 0

    def test_latency_stays_reasonable(self):
        """Even at 100 NPCs, latency should stay under 10ms."""
        result = benchmark_npc_scaling()
        for r in result["results"]:
            assert r["avg_ms"] < 10.0, f"Scaling issue at {r['npc_count']} NPCs: {r['avg_ms']}ms"


# ── Social Fabric Benchmark ──

class TestSocialFabricBenchmark:
    """Test social fabric tick benchmark."""

    def test_returns_valid_structure(self):
        result = benchmark_social_fabric()
        assert result["name"] == "Social Fabric Tick"
        assert "results" in result
        assert len(result["results"]) == 3

    def test_tick_results_have_npc_counts(self):
        result = benchmark_social_fabric()
        counts = [r["npc_count"] for r in result["results"]]
        assert counts == [20, 50, 100]

    def test_each_result_has_tick_latency(self):
        result = benchmark_social_fabric()
        for r in result["results"]:
            assert "avg_tick_ms" in r
            assert "p95_tick_ms" in r
            assert r["avg_tick_ms"] > 0

    def test_tick_is_fast(self):
        """Social fabric tick should be under 5ms even at 100 NPCs."""
        result = benchmark_social_fabric()
        for r in result["results"]:
            assert r["avg_tick_ms"] < 5.0


# ── Save/Load Benchmark ──

class TestSaveLoadBenchmark:
    """Test save/load benchmark."""

    def test_returns_valid_structure(self):
        result = benchmark_save_load()
        assert result["name"] == "Save/Load"
        assert "npc_count" in result
        assert "save_ms" in result
        assert "load_ms" in result
        assert "total_file_size_kb" in result

    def test_npc_count(self):
        result = benchmark_save_load()
        assert result["npc_count"] == 20

    def test_save_load_values_positive(self):
        result = benchmark_save_load()
        assert result["save_ms"] > 0
        assert result["load_ms"] > 0
        assert result["total_file_size_kb"] > 0

    def test_save_is_fast(self):
        """Save 20 NPCs should be under 100ms."""
        result = benchmark_save_load()
        assert result["save_ms"] < 100.0

    def test_load_is_fast(self):
        """Load 20 NPCs should be under 100ms."""
        result = benchmark_save_load()
        assert result["load_ms"] < 100.0


# ── Kernel Bridge Benchmark ──

class TestKernelBridgeBenchmark:
    """Test kernel bridge benchmark."""

    def test_returns_valid_structure(self):
        result = benchmark_kernel_bridge()
        assert result["name"] == "Kernel Bridge (Fallback)"
        assert "iterations" in result
        assert "avg_ms" in result
        assert "p50_ms" in result
        assert "p99_ms" in result

    def test_iterations_count(self):
        result = benchmark_kernel_bridge()
        assert result["iterations"] == 4000  # 1000 * 4 queries

    def test_kernel_is_fast(self):
        """Kernel bridge should be sub-millisecond."""
        result = benchmark_kernel_bridge()
        assert result["avg_ms"] < 1.0


# ── Comparison ──

class TestComparison:
    """Test comparison data generation."""

    def test_returns_valid_structure(self):
        result = generate_comparison()
        assert result["name"] == "Synthesus vs LLM NPC Comparison"
        assert "synthesus" in result
        assert "openai_gpt4" in result
        assert "local_llama_7b" in result

    def test_synthesus_advantages(self):
        result = generate_comparison()
        syn = result["synthesus"]
        assert syn["gpu_required"] is False
        assert syn["deterministic"] is True
        assert syn["offline_capable"] is True
        assert "1000+" in syn["max_concurrent_npcs"]

    def test_all_platforms_have_latency(self):
        result = generate_comparison()
        for platform in ["synthesus", "openai_gpt4", "local_llama_7b"]:
            assert "latency_ms" in result[platform]


# ── Full Suite Runner ──

class TestFullSuiteRunner:
    """Test the complete benchmark suite runner."""

    def test_run_all_returns_results(self):
        results = run_all_benchmarks()
        assert "timestamp" in results
        assert "benchmarks" in results
        assert "comparison" in results

    def test_all_benchmarks_present(self):
        results = run_all_benchmarks()
        names = [b["name"] for b in results["benchmarks"]]
        assert "Pattern Matching" in names
        assert "Full Cognitive Pipeline" in names
        assert "Memory Per NPC" in names
        assert "NPC Scaling" in names
        assert "Social Fabric Tick" in names
        assert "Save/Load" in names
        assert "Kernel Bridge (Fallback)" in names

    def test_benchmark_count(self):
        results = run_all_benchmarks()
        assert len(results["benchmarks"]) == 7

    def test_timestamp_is_recent(self):
        results = run_all_benchmarks()
        assert results["timestamp"] > time.time() - 300  # within 5 min


# ── Demo Reel ──

class TestDemoReel:
    """Test demo reel script components."""

    def test_demo_reel_importable(self):
        from demo_reel import (
            MERCHANT_BIO,
            MERCHANT_PATTERNS,
            GUARD_BIO,
            GUARD_PATTERNS,
            demo_1_npc_creation,
            demo_2_conversation,
            demo_3_social_fabric,
            demo_4_persistence,
            demo_5_kernel_bridge,
            demo_6_benchmark_summary,
            main,
        )

    def test_merchant_bio_complete(self):
        from demo_reel import MERCHANT_BIO
        assert MERCHANT_BIO["name"] == "Aldric the Merchant"
        assert MERCHANT_BIO["role"] == "merchant"

    def test_guard_bio_complete(self):
        from demo_reel import GUARD_BIO
        assert GUARD_BIO["name"] == "Captain Lyra"
        assert GUARD_BIO["role"] == "guard_captain"

    def test_npc_creation_demo(self):
        from demo_reel import demo_1_npc_creation
        merchant, guard = demo_1_npc_creation()
        assert merchant is not None
        assert guard is not None

    def test_conversation_demo(self):
        from demo_reel import demo_1_npc_creation, demo_2_conversation
        merchant, _ = demo_1_npc_creation()
        # Should not raise
        demo_2_conversation(merchant)
