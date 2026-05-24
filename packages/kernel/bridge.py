"""
Module 13: C++ Kernel Bridge — pybind11 Interface Layer

Provides the contract between the Python cognitive engine and the C++ kernel.
Three operating modes:

1. NATIVE: C++ kernel compiled with pybind11 → direct function calls (~0.1ms)
2. IPC: C++ kernel as subprocess → stdin/stdout JSON protocol (~2ms)
3. FALLBACK: Pure Python reimplementation of kernel APIs (~1ms)

The bridge auto-detects which mode is available and gracefully degrades.
Game developers compile the kernel for production; development uses fallback.

Cost: <1ms per call in fallback mode, ~0.1ms native, zero GPU.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Bridge Mode ──

class BridgeMode(Enum):
    NATIVE = "native"      # pybind11 compiled module
    IPC = "ipc"            # subprocess stdin/stdout
    FALLBACK = "fallback"  # Python reimplementation


# ── Data Types (shared contract between C++ and Python) ──

@dataclass
class KernelQuery:
    """Input to the kernel."""
    text: str
    context: str = ""
    character_id: str = ""
    player_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KernelResult:
    """Output from the kernel."""
    response: str
    confidence: float
    module_used: str           # Which kernel module handled it
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryEntry:
    """Kernel memory store entry."""
    key: str
    value: str
    timestamp: float = 0.0
    ttl_seconds: float = 0.0   # 0 = permanent


@dataclass
class ThreadPoolStats:
    """Thread pool status from the kernel."""
    active_threads: int = 0
    queued_tasks: int = 0
    completed_tasks: int = 0
    pool_size: int = 4


# ── Python Fallback Implementations ──

class FallbackThreadPool:
    """Pure Python stand-in for zo::ThreadPool."""

    def __init__(self, size: int = 4):
        self.size = size
        self._completed = 0
        self._active = 0

    def submit(self, fn, *args, **kwargs):
        """Execute synchronously in fallback mode."""
        self._active += 1
        try:
            result = fn(*args, **kwargs)
            self._completed += 1
            return result
        finally:
            self._active -= 1

    def stats(self) -> ThreadPoolStats:
        return ThreadPoolStats(
            active_threads=self._active,
            queued_tasks=0,
            completed_tasks=self._completed,
            pool_size=self.size,
        )


class FallbackMessageBus:
    """Pure Python stand-in for zo::MessageBus."""

    def __init__(self):
        self._subscribers: Dict[str, List] = {}
        self._message_count = 0

    def publish(self, topic: str, data: Any) -> None:
        self._message_count += 1
        for handler in self._subscribers.get(topic, []):
            handler(data)

    def subscribe(self, topic: str, handler) -> None:
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler) -> None:
        if topic in self._subscribers:
            self._subscribers[topic] = [h for h in self._subscribers[topic] if h != handler]

    @property
    def message_count(self) -> int:
        return self._message_count

    @property
    def topic_count(self) -> int:
        return len(self._subscribers)


class FallbackMemoryAllocator:
    """Pure Python stand-in for zo::MemoryAllocator."""

    def __init__(self, pool_size_mb: int = 64):
        self._pool_size = pool_size_mb * 1024 * 1024
        self._allocated = 0
        self._allocations: Dict[str, int] = {}

    def allocate(self, tag: str, size_bytes: int) -> bool:
        if self._allocated + size_bytes > self._pool_size:
            return False
        self._allocations[tag] = self._allocations.get(tag, 0) + size_bytes
        self._allocated += size_bytes
        return True

    def deallocate(self, tag: str) -> int:
        freed = self._allocations.pop(tag, 0)
        self._allocated -= freed
        return freed

    @property
    def used_bytes(self) -> int:
        return self._allocated

    @property
    def free_bytes(self) -> int:
        return self._pool_size - self._allocated

    @property
    def utilization(self) -> float:
        return self._allocated / self._pool_size if self._pool_size > 0 else 0.0


class FallbackContextMemory:
    """Pure Python stand-in for zo::ContextMemory (sqlite-backed in C++)."""

    def __init__(self):
        self._store: Dict[str, MemoryEntry] = {}

    def store(self, key: str, value: str, ttl_seconds: float = 0.0) -> None:
        self._store[key] = MemoryEntry(
            key=key, value=value,
            timestamp=time.time(),
            ttl_seconds=ttl_seconds,
        )

    def recall(self, key: str) -> Optional[str]:
        entry = self._store.get(key)
        if not entry:
            return None
        if entry.ttl_seconds > 0 and (time.time() - entry.timestamp) > entry.ttl_seconds:
            del self._store[key]
            return None
        return entry.value

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def keys(self) -> List[str]:
        return list(self._store.keys())

    @property
    def size(self) -> int:
        return len(self._store)


class FallbackPPBRS:
    """
    Pure Python stand-in for zo::PPBRSRouter.
    Pattern-Prioritized Bayesian Routing System.
    Routes queries to the best-matching module.
    """

    def __init__(self):
        self._routes: List[Dict[str, Any]] = []
        self._query_count = 0

    def add_route(self, pattern: str, module: str, priority: float = 1.0) -> None:
        self._routes.append({
            "pattern": pattern.lower(),
            "module": module,
            "priority": priority,
        })

    def route(self, query: str, context: str = "") -> KernelResult:
        """Route a query through the PPBRS system."""
        self._query_count += 1
        query_lower = query.lower()
        query_words = set(query_lower.split())

        best_match = None
        best_score = 0.0

        for route in self._routes:
            pattern_words = set(route["pattern"].split())
            overlap = len(query_words & pattern_words)
            if overlap > 0:
                score = (overlap / max(len(pattern_words), 1)) * route["priority"]
                if score > best_score:
                    best_score = score
                    best_match = route

        if best_match and best_score > 0.3:
            return KernelResult(
                response=f"[{best_match['module']}] Handled: {query}",
                confidence=min(1.0, best_score),
                module_used=best_match["module"],
            )

        return KernelResult(
            response=f"[fallback] No route matched: {query}",
            confidence=0.0,
            module_used="fallback",
        )

    @property
    def route_count(self) -> int:
        return len(self._routes)

    @property
    def query_count(self) -> int:
        return self._query_count


class FallbackWatchdog:
    """Pure Python stand-in for zo::Watchdog."""

    def __init__(self):
        self._running = False
        self._start_time = 0.0
        self._health_checks = 0

    def start(self) -> None:
        self._running = True
        self._start_time = time.time()

    def stop(self) -> None:
        self._running = False

    def health_check(self) -> Dict[str, Any]:
        self._health_checks += 1
        return {
            "running": self._running,
            "uptime_seconds": time.time() - self._start_time if self._running else 0,
            "health_checks": self._health_checks,
            "status": "healthy" if self._running else "stopped",
        }

    @property
    def is_running(self) -> bool:
        return self._running


# ── Kernel Bridge (Main Entry Point) ──

class KernelBridge:
    """
    Bridge between Python cognitive engine and C++ kernel.

    Auto-detects the best available mode:
    1. Try importing compiled pybind11 module
    2. Try launching C++ kernel subprocess
    3. Fall back to pure Python implementations

    All three modes expose the same API.
    """

    def __init__(
        self,
        kernel_path: Optional[str] = None,
        force_mode: Optional[BridgeMode] = None,
    ):
        self._kernel_path = kernel_path
        self._mode = force_mode or self._detect_mode(kernel_path)
        self._kernel_proc: Optional[subprocess.Popen] = None

        # Initialize subsystems based on mode
        if self._mode == BridgeMode.NATIVE:
            self._init_native()
        elif self._mode == BridgeMode.IPC:
            self._init_ipc(kernel_path)
        else:
            self._init_fallback()

        self._query_count = 0
        self._total_latency_ms = 0.0

        logger.info(f"KernelBridge initialized in {self._mode.value} mode")

    def _detect_mode(self, kernel_path: Optional[str]) -> BridgeMode:
        """Auto-detect the best available mode."""
        # 1. Try pybind11 native module
        try:
            import synthesus_kernel  # noqa: F401
            return BridgeMode.NATIVE
        except ImportError:
            pass

        # 2. Try IPC with compiled binary
        if kernel_path:
            binary = Path(kernel_path)
            if binary.exists() and os.access(str(binary), os.X_OK):
                return BridgeMode.IPC

        # 3. Check default paths
        for default_path in ["./zo_kernel", "./build/zo_kernel", "./build/synthesus_kernel"]:
            p = Path(default_path)
            if p.exists() and os.access(str(p), os.X_OK):
                self._kernel_path = str(p)
                return BridgeMode.IPC

        return BridgeMode.FALLBACK

    def _init_native(self) -> None:
        """Initialize pybind11 native mode."""
        import synthesus_kernel as _kernel  # type: ignore
        self._native = _kernel
        self.thread_pool = _kernel.ThreadPool(4)
        self.message_bus = _kernel.MessageBus()
        self.memory = _kernel.ContextMemory()
        self.ppbrs = _kernel.PPBRSRouter()
        self.watchdog = _kernel.Watchdog()

    def _init_ipc(self, kernel_path: Optional[str]) -> None:
        """Initialize IPC subprocess mode."""
        binary = kernel_path or self._kernel_path
        try:
            self._kernel_proc = subprocess.Popen(
                [binary],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            # Fallback subsystems for local access
            self.thread_pool = FallbackThreadPool()
            self.message_bus = FallbackMessageBus()
            self.memory = FallbackContextMemory()
            self.ppbrs = FallbackPPBRS()
            self.watchdog = FallbackWatchdog()
            self.watchdog.start()
        except (OSError, FileNotFoundError) as e:
            logger.warning(f"IPC init failed ({e}), falling back to Python")
            self._mode = BridgeMode.FALLBACK
            self._init_fallback()

    def _init_fallback(self) -> None:
        """Initialize pure Python fallback mode."""
        self.thread_pool = FallbackThreadPool()
        self.message_bus = FallbackMessageBus()
        self.memory = FallbackContextMemory()
        self.ppbrs = FallbackPPBRS()
        self.watchdog = FallbackWatchdog()
        self.watchdog.start()

    @property
    def mode(self) -> BridgeMode:
        return self._mode

    @property
    def is_native(self) -> bool:
        return self._mode == BridgeMode.NATIVE

    @property
    def is_ipc(self) -> bool:
        return self._mode == BridgeMode.IPC

    @property
    def is_fallback(self) -> bool:
        return self._mode == BridgeMode.FALLBACK

    # ── Core API ──

    def query(self, q: KernelQuery) -> KernelResult:
        """Send a query to the kernel and get a result."""
        start = time.time()
        self._query_count += 1

        if self._mode == BridgeMode.NATIVE:
            result = self._query_native(q)
        elif self._mode == BridgeMode.IPC:
            result = self._query_ipc(q)
        else:
            result = self._query_fallback(q)

        result.latency_ms = (time.time() - start) * 1000
        self._total_latency_ms += result.latency_ms
        return result

    def _query_native(self, q: KernelQuery) -> KernelResult:
        """Query via pybind11 direct call."""
        raw = self._native.route(q.text, q.context)
        return KernelResult(
            response=raw.response,
            confidence=raw.confidence,
            module_used=raw.module_used,
        )

    def _query_ipc(self, q: KernelQuery) -> KernelResult:
        """Query via stdin/stdout IPC."""
        if not self._kernel_proc or self._kernel_proc.poll() is not None:
            return self._query_fallback(q)

        try:
            self._kernel_proc.stdin.write(q.text + "\n")
            self._kernel_proc.stdin.flush()
            line = self._kernel_proc.stdout.readline().strip()
            if line:
                data = json.loads(line)
                return KernelResult(
                    response=data.get("r", ""),
                    confidence=data.get("c", 0.0),
                    module_used=data.get("m", "unknown"),
                )
        except (BrokenPipeError, json.JSONDecodeError, IOError) as e:
            logger.warning(f"IPC query failed: {e}")

        return self._query_fallback(q)

    def _query_fallback(self, q: KernelQuery) -> KernelResult:
        """Query via Python fallback."""
        self.memory.store("last_query", q.text)
        result = self.ppbrs.route(q.text, q.context)
        return result

    # ── Memory API ──

    def store_memory(self, key: str, value: str, ttl: float = 0.0) -> None:
        self.memory.store(key, value, ttl)

    def recall_memory(self, key: str) -> Optional[str]:
        return self.memory.recall(key)

    def delete_memory(self, key: str) -> bool:
        return self.memory.delete(key)

    # ── Messaging API ──

    def publish(self, topic: str, data: Any) -> None:
        self.message_bus.publish(topic, data)

    def subscribe(self, topic: str, handler) -> None:
        self.message_bus.subscribe(topic, handler)

    # ── Health ──

    def health(self) -> Dict[str, Any]:
        return {
            "mode": self._mode.value,
            "watchdog": self.watchdog.health_check(),
            "thread_pool": self.thread_pool.stats().__dict__ if hasattr(self.thread_pool, 'stats') else {},
            "memory_entries": self.memory.size,
            "ppbrs_routes": self.ppbrs.route_count,
            "total_queries": self._query_count,
            "avg_latency_ms": round(self._total_latency_ms / max(1, self._query_count), 2),
        }

    # ── Lifecycle ──

    def shutdown(self) -> None:
        """Cleanly shut down the kernel bridge."""
        self.watchdog.stop()
        if self._kernel_proc:
            try:
                self._kernel_proc.stdin.write("quit\n")
                self._kernel_proc.stdin.flush()
                self._kernel_proc.wait(timeout=5)
            except Exception:
                self._kernel_proc.kill()
            self._kernel_proc = None

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass
