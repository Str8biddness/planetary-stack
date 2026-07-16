"""
Tests for Module 13: C++ Kernel Bridge

Tests cover:
- Bridge auto-detection (falls back to Python in test env)
- Fallback ThreadPool, MessageBus, MemoryAllocator, PPBRS, Watchdog
- KernelBridge query pipeline
- Memory store/recall/delete
- Message pub/sub
- Health reporting
- Lifecycle (startup, shutdown)
- Performance (<1ms per query in fallback mode)
"""

import time
import pytest
from kernel.bridge import (
    KernelBridge,
    BridgeMode,
    KernelQuery,
    KernelResult,
    FallbackThreadPool,
    FallbackMessageBus,
    FallbackMemoryAllocator,
    FallbackContextMemory,
    FallbackPPBRS,
    FallbackWatchdog,
    ThreadPoolStats,
)


# ══════════════════════════════════════
# Fallback ThreadPool Tests
# ══════════════════════════════════════

class TestFallbackThreadPool:
    def test_create(self):
        pool = FallbackThreadPool(size=8)
        assert pool.size == 8

    def test_submit_executes(self):
        pool = FallbackThreadPool()
        results = []
        pool.submit(lambda: results.append(42))
        assert results == [42]

    def test_stats(self):
        pool = FallbackThreadPool(size=4)
        pool.submit(lambda: None)
        pool.submit(lambda: None)
        stats = pool.stats()
        assert isinstance(stats, ThreadPoolStats)
        assert stats.completed_tasks == 2
        assert stats.pool_size == 4


# ══════════════════════════════════════
# Fallback MessageBus Tests
# ══════════════════════════════════════

class TestFallbackMessageBus:
    def test_publish_subscribe(self):
        bus = FallbackMessageBus()
        received = []
        bus.subscribe("test", lambda data: received.append(data))
        bus.publish("test", "hello")
        assert received == ["hello"]

    def test_multiple_subscribers(self):
        bus = FallbackMessageBus()
        a, b = [], []
        bus.subscribe("topic", lambda d: a.append(d))
        bus.subscribe("topic", lambda d: b.append(d))
        bus.publish("topic", "msg")
        assert a == ["msg"]
        assert b == ["msg"]

    def test_no_crosstalk(self):
        bus = FallbackMessageBus()
        received = []
        bus.subscribe("topic_a", lambda d: received.append(d))
        bus.publish("topic_b", "wrong")
        assert received == []

    def test_unsubscribe(self):
        bus = FallbackMessageBus()
        received = []
        handler = lambda d: received.append(d)
        bus.subscribe("test", handler)
        bus.unsubscribe("test", handler)
        bus.publish("test", "nope")
        assert received == []

    def test_message_count(self):
        bus = FallbackMessageBus()
        bus.publish("a", 1)
        bus.publish("b", 2)
        assert bus.message_count == 2

    def test_topic_count(self):
        bus = FallbackMessageBus()
        bus.subscribe("a", lambda d: None)
        bus.subscribe("b", lambda d: None)
        assert bus.topic_count == 2


# ══════════════════════════════════════
# Fallback MemoryAllocator Tests
# ══════════════════════════════════════

class TestFallbackMemoryAllocator:
    def test_allocate(self):
        alloc = FallbackMemoryAllocator(pool_size_mb=1)
        assert alloc.allocate("test", 1024) is True
        assert alloc.used_bytes == 1024

    def test_allocate_exceeds_pool(self):
        alloc = FallbackMemoryAllocator(pool_size_mb=1)  # 1MB
        assert alloc.allocate("big", 2 * 1024 * 1024) is False

    def test_deallocate(self):
        alloc = FallbackMemoryAllocator(pool_size_mb=1)
        alloc.allocate("test", 1024)
        freed = alloc.deallocate("test")
        assert freed == 1024
        assert alloc.used_bytes == 0

    def test_utilization(self):
        alloc = FallbackMemoryAllocator(pool_size_mb=1)
        total = 1 * 1024 * 1024
        alloc.allocate("half", total // 2)
        assert abs(alloc.utilization - 0.5) < 0.01

    def test_free_bytes(self):
        alloc = FallbackMemoryAllocator(pool_size_mb=1)
        total = 1 * 1024 * 1024
        alloc.allocate("some", 100)
        assert alloc.free_bytes == total - 100


# ══════════════════════════════════════
# Fallback ContextMemory Tests
# ══════════════════════════════════════

class TestFallbackContextMemory:
    def test_store_recall(self):
        mem = FallbackContextMemory()
        mem.store("key1", "value1")
        assert mem.recall("key1") == "value1"

    def test_recall_missing(self):
        mem = FallbackContextMemory()
        assert mem.recall("nonexistent") is None

    def test_delete(self):
        mem = FallbackContextMemory()
        mem.store("key1", "value1")
        assert mem.delete("key1") is True
        assert mem.recall("key1") is None

    def test_delete_nonexistent(self):
        mem = FallbackContextMemory()
        assert mem.delete("nope") is False

    def test_keys(self):
        mem = FallbackContextMemory()
        mem.store("a", "1")
        mem.store("b", "2")
        assert set(mem.keys()) == {"a", "b"}

    def test_size(self):
        mem = FallbackContextMemory()
        mem.store("a", "1")
        mem.store("b", "2")
        assert mem.size == 2

    def test_ttl_expiry(self):
        mem = FallbackContextMemory()
        mem.store("temp", "value", ttl_seconds=0.001)
        time.sleep(0.01)
        assert mem.recall("temp") is None

    def test_ttl_not_expired(self):
        mem = FallbackContextMemory()
        mem.store("temp", "value", ttl_seconds=60)
        assert mem.recall("temp") == "value"

    def test_permanent_entry(self):
        mem = FallbackContextMemory()
        mem.store("perm", "value", ttl_seconds=0)  # 0 = permanent
        assert mem.recall("perm") == "value"


# ══════════════════════════════════════
# Fallback PPBRS Tests
# ══════════════════════════════════════

class TestFallbackPPBRS:
    def test_add_route(self):
        ppbrs = FallbackPPBRS()
        ppbrs.add_route("buy sell trade", "commerce")
        assert ppbrs.route_count == 1

    def test_route_match(self):
        ppbrs = FallbackPPBRS()
        ppbrs.add_route("buy sell trade", "commerce")
        result = ppbrs.route("I want to buy something")
        assert result.confidence > 0
        assert result.module_used == "commerce"

    def test_route_no_match(self):
        ppbrs = FallbackPPBRS()
        ppbrs.add_route("buy sell trade", "commerce")
        result = ppbrs.route("what is the weather")
        assert result.module_used == "fallback"
        assert result.confidence == 0.0

    def test_priority_routing(self):
        ppbrs = FallbackPPBRS()
        ppbrs.add_route("hello hi greet", "greeting", priority=1.0)
        ppbrs.add_route("hello welcome", "intro", priority=2.0)
        result = ppbrs.route("hello there")
        assert result.module_used == "intro"  # Higher priority

    def test_query_count(self):
        ppbrs = FallbackPPBRS()
        ppbrs.route("test")
        ppbrs.route("test")
        assert ppbrs.query_count == 2


# ══════════════════════════════════════
# Fallback Watchdog Tests
# ══════════════════════════════════════

class TestFallbackWatchdog:
    def test_start_stop(self):
        wd = FallbackWatchdog()
        assert wd.is_running is False
        wd.start()
        assert wd.is_running is True
        wd.stop()
        assert wd.is_running is False

    def test_health_check(self):
        wd = FallbackWatchdog()
        wd.start()
        health = wd.health_check()
        assert health["running"] is True
        assert health["status"] == "healthy"
        assert health["uptime_seconds"] >= 0

    def test_health_check_counter(self):
        wd = FallbackWatchdog()
        wd.health_check()
        wd.health_check()
        health = wd.health_check()
        assert health["health_checks"] == 3


# ══════════════════════════════════════
# KernelBridge Tests
# ══════════════════════════════════════

class TestKernelBridge:
    def test_creates_in_fallback_mode(self):
        bridge = KernelBridge()
        assert bridge.mode == BridgeMode.FALLBACK
        assert bridge.is_fallback is True

    def test_force_mode(self):
        bridge = KernelBridge(force_mode=BridgeMode.FALLBACK)
        assert bridge.mode == BridgeMode.FALLBACK

    def test_query(self):
        bridge = KernelBridge()
        bridge.ppbrs.add_route("hello hi greet", "greeting")
        result = bridge.query(KernelQuery(text="hello world"))
        assert isinstance(result, KernelResult)
        assert result.latency_ms >= 0

    def test_query_matched(self):
        bridge = KernelBridge()
        bridge.ppbrs.add_route("buy sell trade", "commerce")
        result = bridge.query(KernelQuery(text="I want to buy"))
        assert result.module_used == "commerce"
        assert result.confidence > 0

    def test_query_unmatched(self):
        bridge = KernelBridge()
        result = bridge.query(KernelQuery(text="random query"))
        assert result.module_used == "fallback"

    def test_memory_api(self):
        bridge = KernelBridge()
        bridge.store_memory("player_name", "Alex")
        assert bridge.recall_memory("player_name") == "Alex"
        assert bridge.delete_memory("player_name") is True
        assert bridge.recall_memory("player_name") is None

    def test_messaging_api(self):
        bridge = KernelBridge()
        received = []
        bridge.subscribe("npc_event", lambda d: received.append(d))
        bridge.publish("npc_event", "quest_completed")
        assert received == ["quest_completed"]

    def test_health(self):
        bridge = KernelBridge()
        health = bridge.health()
        assert health["mode"] == "fallback"
        assert "watchdog" in health
        assert health["total_queries"] == 0

    def test_health_after_queries(self):
        bridge = KernelBridge()
        bridge.query(KernelQuery(text="test"))
        bridge.query(KernelQuery(text="test2"))
        health = bridge.health()
        assert health["total_queries"] == 2
        assert health["avg_latency_ms"] >= 0

    def test_shutdown(self):
        bridge = KernelBridge()
        bridge.shutdown()
        assert bridge.watchdog.is_running is False

    def test_stores_last_query(self):
        bridge = KernelBridge()
        bridge.query(KernelQuery(text="what is the price"))
        assert bridge.recall_memory("last_query") == "what is the price"


# ══════════════════════════════════════
# Performance Tests
# ══════════════════════════════════════

class TestPerformance:
    def test_fallback_query_under_1ms(self):
        bridge = KernelBridge()
        bridge.ppbrs.add_route("buy sell trade", "commerce")
        
        times = []
        for _ in range(100):
            start = time.time()
            bridge.query(KernelQuery(text="I want to buy something"))
            times.append((time.time() - start) * 1000)
        
        avg = sum(times) / len(times)
        assert avg < 1.0, f"Average query time {avg:.3f}ms, should be <1ms"

    def test_message_bus_throughput(self):
        bus = FallbackMessageBus()
        counter = [0]
        bus.subscribe("perf", lambda d: counter.__setitem__(0, counter[0] + 1))
        
        start = time.time()
        for i in range(10000):
            bus.publish("perf", i)
        elapsed = (time.time() - start) * 1000
        
        assert counter[0] == 10000
        assert elapsed < 100, f"10K messages took {elapsed:.1f}ms, should be <100ms"

    def test_memory_throughput(self):
        mem = FallbackContextMemory()
        start = time.time()
        for i in range(1000):
            mem.store(f"key_{i}", f"value_{i}")
        for i in range(1000):
            mem.recall(f"key_{i}")
        elapsed = (time.time() - start) * 1000
        assert elapsed < 50, f"2K ops took {elapsed:.1f}ms, should be <50ms"
