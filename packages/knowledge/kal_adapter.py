"""
KAL (Knowledge Abstraction Layer) — CHAL Memory Controller
Synthesus 4.1 CHAL Line

Mounts Knowledge Cloud partitions as virtual cognitive hardware.
Routes queries to the appropriate partition based on locality, trust, and domain.
"""

from __future__ import annotations

import logging
import re
import time
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
    # Fallback definitions if chal interfaces aren't available yet
    from dataclasses import dataclass, field
    from enum import Enum
    
    class MountType(str, Enum):
        ROM = "ROM"
        PARAMETER_DISK = "PARAMETER_DISK"
        CACHE_SEED = "CACHE_SEED"
        GROUNDING_CORPUS = "GROUNDING_CORPUS"
        SOURCE_PROVENANCE = "SOURCE_PROVENANCE"
        WRITEBACK_MEMORY = "WRITEBACK_MEMORY"

    @dataclass
    class TelemetryRecord:
        operation_id: str
        latency_ms: float
        cache_hit: bool
        confidence: float
        source: str
        metadata: Dict[str, Any] = field(default_factory=dict)

    @dataclass
    class Partition:
        partition_id: str
        namespace: str
        is_read_only: bool
        schema_model: Optional[str] = None
        metadata: Dict[str, Any] = field(default_factory=dict)

    @dataclass
    class Mount:
        mount_path: str
        mount_type: MountType
        partition: Partition
        locality: str = "local"
        trust_level: float = 1.0
        latency_profile: str = "fast"
        is_active: bool = True


logger = logging.getLogger(__name__)


class CHALMemoryController:
    """
    Mount manager and memory controller for the Cognitive Hardware Abstraction Layer.
    Replaces legacy template fallback paths with explicit virtual hardware routing.
    """
    
    def __init__(self):
        self._mounts: Dict[str, Mount] = {}
        self._knowledge_cloud = None
        self._runtime = None
        
        self._init_core_services()
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
        """Mount the standard Synthesus 4.1 cognitive hardware."""
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

    def mount(self, mount_point: Mount) -> None:
        """Register a new CHAL mount point."""
        self._mounts[mount_point.mount_path] = mount_point
        logger.info(f"CHAL: Mounted {mount_point.mount_type.value} at {mount_point.mount_path}")

    def get_mounts(self, mount_type: Optional[MountType] = None) -> List[Mount]:
        """Get all active mounts, optionally filtered by type."""
        if not mount_type:
            return list(self._mounts.values())
        return [m for m in self._mounts.values() if m.mount_type == mount_type and m.is_active]

    def query(self, text: str, trust_available: float = 1.0) -> Tuple[Optional[str], TelemetryRecord]:
        """
        Route a query through the mounted cognitive hardware.
        Returns the resolved context and a telemetry record.
        """
        start_time = time.time()
        text = (text or "").strip()
        if not text:
            return None, self._telemetry("empty_query", start_time, False, 0.0, "none")
            
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
                        return result["response"], self._telemetry("kc_lookup", start_time, True, confidence, source, result)
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

    def _telemetry(
        self, op_id: str, start_time: float, hit: bool, conf: float, source: str, meta: Optional[Dict[str, Any]] = None
    ) -> TelemetryRecord:
        latency = (time.time() - start_time) * 1000.0
        return TelemetryRecord(
            operation_id=op_id,
            latency_ms=latency,
            cache_hit=hit,
            confidence=conf,
            source=source,
            metadata=meta or {}
        )


class SynthesusAdapter:
    """
    Legacy wrapper for pre-CHAL systems. 
    Delegates to CHALMemoryController to obey the Synthesus 4.1 Maximum Directive.
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

__all__ = ["CHALMemoryController", "SynthesusAdapter"]
