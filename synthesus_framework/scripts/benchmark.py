"""Synthesus 2.0 Benchmark Suite - Performance testing for core subsystems"""
import time
import asyncio
import json
import logging
import statistics
from typing import Dict, Any, List, Callable
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


class BenchmarkResult:
    def __init__(self, name: str, times: List[float]):
        self.name = name
        self.times = times

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.times) * 1000

    @property
    def median_ms(self) -> float:
        return statistics.median(self.times) * 1000

    @property
    def p95_ms(self) -> float:
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx] * 1000

    @property
    def throughput(self) -> float:
        return len(self.times) / sum(self.times)

    def report(self) -> str:
        return (
            f"[{self.name}]\n"
            f"  Mean: {self.mean_ms:.2f}ms\n"
            f"  Median: {self.median_ms:.2f}ms\n"
            f"  P95: {self.p95_ms:.2f}ms\n"
            f"  Throughput: {self.throughput:.1f} ops/s\n"
            f"  Runs: {len(self.times)}"
        )


def benchmark(fn: Callable, iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    """Benchmark a synchronous function."""
    name = getattr(fn, "__name__", "unknown")
    # Warmup
    for _ in range(warmup):
        fn()
    # Measure
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        end = time.perf_counter()
        times.append(end - start)
    return BenchmarkResult(name, times)


async def async_benchmark(fn: Callable, iterations: int = 100, warmup: int = 10) -> BenchmarkResult:
    """Benchmark an async function."""
    name = getattr(fn, "__name__", "unknown")
    for _ in range(warmup):
        await fn()
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        await fn()
        end = time.perf_counter()
        times.append(end - start)
    return BenchmarkResult(name, times)


def bench_archetype_loading():
    from unpc_engine.archetype_loader import load_all_archetypes, clear_cache
    clear_cache()
    load_all_archetypes()


def bench_pattern_engine():
    try:
        from core.pattern_engine import PatternEngine
        pe = PatternEngine({})
        pe.match("How are you today?", context={})
    except Exception:
        pass


def run_all_benchmarks():
    benchmarks = [
        (bench_archetype_loading, 50, 5),
        (bench_pattern_engine, 100, 10),
    ]
    results = []
    print("=" * 60)
    print("SYNTHESUS 2.0 BENCHMARK SUITE")
    print("=" * 60)
    for fn, iters, warmup in benchmarks:
        print(f"\nRunning: {fn.__name__}...")
        result = benchmark(fn, iterations=iters, warmup=warmup)
        results.append(result)
        print(result.report())
    print("\n" + "=" * 60)
    print("All benchmarks complete.")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_all_benchmarks()
