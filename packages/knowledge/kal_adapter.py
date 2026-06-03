"""
KAL (Knowledge Abstraction Layer) — CHAL Memory Controller
Synthesus 5 CHAL Line

Mounts Knowledge Cloud partitions as virtual cognitive hardware.
Routes queries to the appropriate partition based on locality, trust, and domain.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from core.synth_runtime import get_runtime
except Exception:
    get_runtime = None

try:
    from core.knowledge_cloud import KnowledgeCloud
except Exception:
    KnowledgeCloud = None

try:
    from core.reasoning.query_decomposer import QueryDecomposer
except Exception:
    QueryDecomposer = None

try:
    from core.chal.interfaces import Mount, MountType, Partition, TelemetryRecord
except ImportError:
    try:
        from chal.interfaces import Mount, MountType, Partition, TelemetryRecord
    except ImportError:
        interfaces_path = Path(__file__).resolve().parents[1] / "core" / "chal" / "interfaces.py"
        spec = importlib.util.spec_from_file_location("_synthesus_chal_interfaces", interfaces_path)
        if spec is None or spec.loader is None:
            raise
        interfaces = sys.modules.get(spec.name)
        if interfaces is None:
            interfaces = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = interfaces
            spec.loader.exec_module(interfaces)
        Mount = interfaces.Mount
        MountType = interfaces.MountType
        Partition = interfaces.Partition
        TelemetryRecord = interfaces.TelemetryRecord

try:
    from knowledge.mount_table import KnowledgeCloudMountTable
except Exception:
    KnowledgeCloudMountTable = None


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HotContextEntry:
    response: str
    confidence: float
    source: str
    metadata: Dict[str, Any]
    cached_at_ms: float


class CHALMemoryController:
    """
    Mount manager and memory controller for the Cognitive Hardware Abstraction Layer.
    Replaces legacy template fallback paths with explicit virtual hardware routing.
    """
    
    def __init__(
        self,
        knowledge_root: Optional[str | Path] = None,
        strict_mount_integrity: bool = False,
        hot_context_limit: int = 128,
    ):
        self._mounts: Dict[str, Mount] = {}
        self._knowledge_cloud = None
        self._runtime = None
        self._mount_boot_report = None
        self._hot_context: OrderedDict[str, HotContextEntry] = OrderedDict()
        self._hot_context_limit = max(0, hot_context_limit)
        self._hot_context_hits = 0
        self._hot_context_misses = 0
        self._knowledge_root = Path(
            knowledge_root
            or os.environ.get("SYNTHESUS_KNOWLEDGE_ROOT", "")
            or Path.cwd() / "data"
        )
        self._strict_mount_integrity = strict_mount_integrity
        
        self._init_core_services()
        if not self._boot_manifest_mounts():
            self._init_default_mounts()

    def _init_core_services(self) -> None:
        if get_runtime is not None:
            try:
                self._runtime = get_runtime()
            except Exception as e:
                logger.warning(f"CHAL: Failed to init runtime: {e}")

        if KnowledgeCloud is not None:
            try:
                self._knowledge_cloud = KnowledgeCloud()
            except Exception as e:
                logger.warning(f"CHAL: Failed to init KnowledgeCloud: {e}")

    def _init_default_mounts(self) -> None:
        """Mount the standard Synthesus 5 cognitive hardware."""
        # 1. ROM: Canonical World Lore
        self.mount(Mount(
            mount_path="/mnt/rom/lore",
            mount_type=MountType.ROM,
            partition=Partition(
                partition_id="kc_lore_01",
                namespace="game_lore",
                is_read_only=True
            ),
            locality="local",
            trust_level=1.0,
            latency_profile="fast"
        ))
        
        # 2. PARAMETER_DISK: Rules and Architect Directives
        self.mount(Mount(
            mount_path="/mnt/params/architect",
            mount_type=MountType.PARAMETER_DISK,
            partition=Partition(
                partition_id="kc_directives_01",
                namespace="architect_directives",
                is_read_only=True
            ),
            trust_level=1.0
        ))
        
        # 3. WRITEBACK_MEMORY: Fluid/Crystallized state (Simulated)
        self.mount(Mount(
            mount_path="/mnt/mem/crystallized",
            mount_type=MountType.WRITEBACK_MEMORY,
            partition=Partition(
                partition_id="sys_mem_01",
                namespace="memory_store",
                is_read_only=False
            ),
            locality="local"
        ))
        
        # 4. GROUNDING_CORPUS: Document and context planes
        self.mount(Mount(
            mount_path="/mnt/corpus/grounding",
            mount_type=MountType.GROUNDING_CORPUS,
            partition=Partition(
                partition_id="kc_corpus_01",
                namespace="grounding_corpus",
                is_read_only=True
            ),
            locality="cloud",
            latency_profile="slow"
        ))

    def _boot_manifest_mounts(self) -> bool:
        """Boot CHAL mounts from a Knowledge Cloud manifest when artifacts exist locally."""
        if KnowledgeCloudMountTable is None:
            return False
        manifest_path = self._knowledge_root / "manifest.json"
        if not manifest_path.exists():
            return False

        try:
            report = KnowledgeCloudMountTable().boot(
                self._knowledge_root,
                strict=self._strict_mount_integrity,
            )
        except Exception as e:
            logger.warning(f"CHAL: Knowledge Cloud mount-table boot failed: {e}")
            if self._strict_mount_integrity:
                raise
            return False

        self._mount_boot_report = report
        for mount_point in report.mounts:
            self.mount(mount_point)
        logger.info(
            "CHAL: Booted %s Knowledge Cloud mounts from %s (integrity_ok=%s)",
            len(report.mounts),
            report.manifest_path,
            report.ok,
        )
        return bool(report.mounts)

    def mount(self, mount_point: Mount) -> None:
        """Register a new CHAL mount point."""
        self._mounts[mount_point.mount_path] = mount_point
        logger.info(f"CHAL: Mounted {mount_point.mount_type.value} at {mount_point.mount_path}")

    def get_mounts(self, mount_type: Optional[MountType] = None) -> List[Mount]:
        """Get all active mounts, optionally filtered by type."""
        if not mount_type:
            return list(self._mounts.values())
        return [m for m in self._mounts.values() if m.mount_type == mount_type and m.is_active]

    def get_mount_boot_report(self):
        """Return the manifest boot report when mounts came from Knowledge Cloud artifacts."""
        return self._mount_boot_report

    def get_hot_context_stats(self) -> Dict[str, Any]:
        """Return L1 hot-context cache stats for CHAL trace/debug surfaces."""
        total = self._hot_context_hits + self._hot_context_misses
        return {
            "entries": len(self._hot_context),
            "limit": self._hot_context_limit,
            "hits": self._hot_context_hits,
            "misses": self._hot_context_misses,
            "hit_rate": round(self._hot_context_hits / total, 4) if total else 0.0,
        }

    def clear_hot_context(self) -> None:
        """Clear volatile hot-context cache entries without affecting mounted hardware."""
        self._hot_context.clear()
        self._hot_context_hits = 0
        self._hot_context_misses = 0

    def query(self, text: str, trust_available: float = 1.0) -> Tuple[Optional[str], TelemetryRecord]:
        """
        Route a query through the mounted cognitive hardware.
        Returns the resolved context and a telemetry record.
        """
        start_time = time.time()
        text = (text or "").strip()
        if not text:
            return None, self._telemetry("empty_query", start_time, False, 0.0, "none")

        cache_key = self._hot_context_key(text, trust_available)
        cached = self._get_hot_context(cache_key)
        if cached is not None:
            return cached.response, self._telemetry(
                "hot_context_hit",
                start_time,
                True,
                cached.confidence,
                cached.source,
                {
                    **cached.metadata,
                    "hot_context": True,
                    "cached_at_ms": cached.cached_at_ms,
                },
            )
            
        # Strategy: 
        # 1. Try ROM / Lore mounts (Knowledge Cloud)
        # 2. Try Grounding mounts
        # 3. Fallback to runtime
        
        # Try Knowledge Cloud (mounted at /mnt/rom/lore)
        if self._knowledge_cloud is not None:
            rom_mounts = self.get_mounts(MountType.ROM)
            if rom_mounts:
                try:
                    result = self._knowledge_cloud.lookup(text, trust=trust_available * 100.0)
                    if result and result.get("response"):
                        confidence = result.get("confidence", 0.5)
                        source = f"rom_mount:{rom_mounts[0].partition.partition_id}"
                        metadata = {
                            **result,
                            "hot_context": False,
                            "mounts": self._active_mount_metadata(rom_mounts),
                        }
                        self._put_hot_context(cache_key, result["response"], confidence, source, metadata)
                        return result["response"], self._telemetry("kc_lookup", start_time, False, confidence, source, metadata)
                except Exception as e:
                    logger.warning(f"CHAL: ROM mount query failed: {e}")

        # Try Runtime fallback
        if self._runtime is not None:
            try:
                result = self._runtime.respond("synth", text)
                response = getattr(result, "final_response", None)
                if response:
                    return response, self._telemetry("runtime_fallback", start_time, False, 0.4, "runtime_bridge")
            except Exception as e:
                logger.warning(f"CHAL: Runtime bridge query failed: {e}")

        # Return explicit degraded state instead of generic string
        return (
            "[SYSTEM: DEGRADED_STATE. Cognitive hardware returned no highly confident resolution for the query.]", 
            self._telemetry("degraded_state", start_time, False, 0.0, "chal_arbiter")
        )

    @staticmethod
    def _hot_context_key(text: str, trust_available: float) -> str:
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        return f"{normalized}|trust:{trust_available:.3f}"

    def _get_hot_context(self, cache_key: str) -> Optional[HotContextEntry]:
        if self._hot_context_limit <= 0:
            return None
        cached = self._hot_context.get(cache_key)
        if cached is None:
            self._hot_context_misses += 1
            return None
        self._hot_context_hits += 1
        self._hot_context.move_to_end(cache_key)
        return cached

    def _put_hot_context(
        self,
        cache_key: str,
        response: str,
        confidence: float,
        source: str,
        metadata: Dict[str, Any],
    ) -> None:
        if self._hot_context_limit <= 0:
            return
        self._hot_context[cache_key] = HotContextEntry(
            response=response,
            confidence=confidence,
            source=source,
            metadata=metadata,
            cached_at_ms=time.time() * 1000.0,
        )
        self._hot_context.move_to_end(cache_key)
        while len(self._hot_context) > self._hot_context_limit:
            self._hot_context.popitem(last=False)

    @staticmethod
    def _active_mount_metadata(mounts: List[Mount]) -> List[Dict[str, Any]]:
        active_mounts = []
        for mount in mounts:
            if not mount.is_active:
                continue
            artifact = {
                key: mount.partition.metadata.get(key)
                for key in (
                    "relative_path",
                    "actual_size",
                    "actual_sha256",
                    "integrity_ok",
                )
                if key in mount.partition.metadata
            }
            metadata = {
                "mount_path": mount.mount_path,
                "mount_type": mount.mount_type.value,
                "partition_id": mount.partition.partition_id,
                "namespace": mount.partition.namespace,
                "locality": mount.locality,
                "trust_level": mount.trust_level,
                "latency_profile": mount.latency_profile,
            }
            if artifact:
                metadata["artifact"] = artifact
            active_mounts.append(metadata)
        return active_mounts

    def _telemetry(
        self, op_id: str, start_time: float, hit: bool, conf: float, source: str, meta: Optional[Dict[str, Any]] = None
    ) -> TelemetryRecord:
        latency = (time.time() - start_time) * 1000.0
        budgets = {"latency_ms": 5.0 if op_id in {"kc_lookup", "hot_context_hit"} else 50.0}
        return TelemetryRecord(
            operation_id=op_id,
            latency_ms=latency,
            cache_hit=hit,
            confidence=conf,
            source=source,
            metadata=meta or {},
            budgets=budgets,
        )


class SynthesusAdapter:
    """
    Legacy wrapper for pre-CHAL systems. 
    Delegates to CHALMemoryController to obey the Synthesus 5 CHAL blueprint.
    """
    
    def __init__(self):
        self._controller = CHALMemoryController()
        
    def query(self, text: str) -> str:
        response, telemetry = self._controller.query(text)
        if response:
            return response
        return "I can help with that, but I need a narrower prompt."

    def answer(self, text: str) -> str:
        return self.query(text)

__all__ = ["CHALMemoryController", "HotContextEntry", "SynthesusAdapter"]
