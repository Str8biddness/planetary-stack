"""
AIVM Resource Allocator
Manages CPU, memory, and GPU resources across multiple concurrent models.
"""
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
import uuid
import logging
import psutil
import os

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    THREAD = "thread"


@dataclass
class ResourceAllocation:
    allocation_id: str
    model_id: str
    resource_type: ResourceType
    requested_units: float
    allocated_units: float
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None


@dataclass
class ResourceQuota:
    max_memory_mb: float = 1024.0
    max_cpu_percent: float = 100.0
    max_threads: int = 8
    max_gpu_memory_mb: float = 2048.0


class ResourceAllocator:
    """
    Manages resource allocation for concurrent AIVM models.
    Implements priority-based allocation with quotas and limits.
    """

    def __init__(self, system_quota: ResourceQuota = None):
        self._allocations: Dict[str, ResourceAllocation] = {}
        self._model_allocations: Dict[str, List[str]] = {}
        self._system_quota = system_quota or ResourceQuota()
        self._lock = threading.RLock()
        self._resource_usage: Dict[str, Dict[str, float]] = {}
        self._reservation_history: List[Dict[str, Any]] = []

    def allocate(
        self,
        model_id: str,
        resource_type: ResourceType,
        requested_units: float,
        priority: int = 0,
        ttl_seconds: float = 0.0
    ) -> Tuple[bool, str]:
        """Allocate resources for a model."""
        allocation_id = str(uuid.uuid4())

        with self._lock:
            if resource_type == ResourceType.MEMORY:
                available = self._get_available_memory()
                if requested_units > available:
                    logger.warning(f"Memory allocation denied for {model_id}: requested {requested_units}MB, available {available}MB")
                    return False, ""
            elif resource_type == ResourceType.CPU:
                available = self._get_available_cpu()
                if requested_units > available:
                    logger.warning(f"CPU allocation denied for {model_id}: requested {requested_units}%, available {available}%")
                    return False, ""

            expires_at = time.time() + ttl_seconds if ttl_seconds > 0 else None
            allocation = ResourceAllocation(
                allocation_id=allocation_id,
                model_id=model_id,
                resource_type=resource_type,
                requested_units=requested_units,
                allocated_units=requested_units,
                priority=priority,
                expires_at=expires_at
            )

            self._allocations[allocation_id] = allocation
            if model_id not in self._model_allocations:
                self._model_allocations[model_id] = []
            self._model_allocations[model_id].append(allocation_id)

            if model_id not in self._resource_usage:
                self._resource_usage[model_id] = {}
            self._resource_usage[model_id][resource_type.value] = requested_units

        self._reservation_history.append({
            "allocation_id": allocation_id,
            "model_id": model_id,
            "resource_type": resource_type.value,
            "units": requested_units,
            "timestamp": time.time(),
        })
        if len(self._reservation_history) > 1000:
            self._reservation_history = self._reservation_history[-500:]

        logger.info(f"Allocated {resource_type.value}={requested_units} for {model_id} (id={allocation_id})")
        return True, allocation_id

    def deallocate(self, allocation_id: str) -> bool:
        """Deallocate resources by allocation ID."""
        with self._lock:
            if allocation_id not in self._allocations:
                return False

            allocation = self._allocations[allocation_id]
            model_id = allocation.model_id

            if model_id in self._model_allocations:
                self._model_allocations[model_id] = [
                    a for a in self._model_allocations[model_id]
                    if a != allocation_id
                ]

            if model_id in self._resource_usage:
                rt = allocation.resource_type.value
                if rt in self._resource_usage[model_id]:
                    self._resource_usage[model_id][rt] = 0.0

            del self._allocations[allocation_id]
            logger.info(f"Deallocated {allocation_id}")
            return True

    def deallocate_model(self, model_id: str) -> int:
        """Deallocate all resources for a model."""
        count = 0
        with self._lock:
            if model_id in self._model_allocations:
                allocation_ids = self._model_allocations[model_id].copy()
                for aid in allocation_ids:
                    if aid in self._allocations:
                        del self._allocations[aid]
                        count += 1
                del self._model_allocations[model_id]
            if model_id in self._resource_usage:
                del self._resource_usage[model_id]
        logger.info(f"Deallocated {count} allocations for model {model_id}")
        return count

    def reallocate(self, allocation_id: str, new_units: float) -> bool:
        """Reallocate resources with new unit count."""
        with self._lock:
            if allocation_id not in self._allocations:
                return False

            allocation = self._allocations[allocation_id]
            allocation.allocated_units = new_units

            if allocation.model_id in self._resource_usage:
                rt = allocation.resource_type.value
                self._resource_usage[allocation.model_id][rt] = new_units

        logger.info(f"Reallocated {allocation_id} to {new_units}")
        return True

    def get_allocation(self, allocation_id: str) -> Optional[ResourceAllocation]:
        """Get allocation details."""
        return self._allocations.get(allocation_id)

    def get_model_allocations(self, model_id: str) -> List[ResourceAllocation]:
        """Get all allocations for a model."""
        with self._lock:
            if model_id not in self._model_allocations:
                return []
            return [
                self._allocations[aid]
                for aid in self._model_allocations[model_id]
                if aid in self._allocations
            ]

    def _get_available_memory(self) -> float:
        """Get available system memory in MB."""
        mem = psutil.virtual_memory()
        used_by_models = sum(
            self._resource_usage.get(m, {}).get("memory", 0.0)
            for m in self._resource_usage
        )
        available = mem.available / (1024 * 1024) - used_by_models
        return max(0, available)

    def _get_available_cpu(self) -> float:
        """Get available CPU percentage."""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        used_by_models = sum(
            self._resource_usage.get(m, {}).get("cpu", 0.0)
            for m in self._resource_usage
        )
        available = 100.0 - cpu_percent - used_by_models
        return max(0, min(100.0, available))

    def get_system_usage(self) -> Dict[str, Any]:
        """Get current system resource usage."""
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        return {
            "memory_total_mb": mem.total / (1024 * 1024),
            "memory_available_mb": mem.available / (1024 * 1024),
            "memory_used_mb": mem.used / (1024 * 1024),
            "memory_percent": mem.percent,
            "cpu_total_percent": 100.0,
            "cpu_used_percent": cpu,
            "cpu_available_percent": 100.0 - cpu,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get allocator statistics."""
        with self._lock:
            return {
                "total_allocations": len(self._allocations),
                "active_models": len(self._model_allocations),
                "system_usage": self.get_system_usage(),
                "history_size": len(self._reservation_history),
            }