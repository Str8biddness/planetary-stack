"""
AIVM Execution Engine — VM Instruction Dispatcher & Resource Allocation.

Routes VM instructions to appropriate handlers with concurrent model execution
support, resource tracking, and error recovery.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class InstructionType(Enum):
    """
    Enum defining the various types of instructions that the AIVM can execute.
    """
    LOAD_MODEL = "load_model"
    UNLOAD_MODEL = "unload_model"
    RUN_INFERENCE = "run_inference"
    ALLOCATE_MEMORY = "allocate_memory"
    DEALLOCATE_MEMORY = "deallocate_memory"
    SYNC_STATE = "sync_state"
    GET_STATS = "get_stats"
    HEALTH_CHECK = "health_check"
    HOTSWAP = "hotswap"
    EMERGENCY_STOP = "emergency_stop"


@dataclass
class VMInstruction:
    """
    Represents a single instruction to be executed by the AIVM.

    Attributes:
        instruction_id: A unique identifier for the instruction.
        instruction_type: The type of instruction to execute.
        payload: Data required for the instruction's execution.
        created_at: Timestamp when the instruction was created.
        priority: Execution priority (lower values are higher priority).
        timeout_seconds: Maximum time allowed for instruction execution.
        metadata: Additional contextual information.
    """
    instruction_id: str
    instruction_type: InstructionType
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    priority: int = 0
    timeout_seconds: float = 30.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InstructionResult:
    """
    Represents the result of an AIVM instruction execution.

    Attributes:
        instruction_id: The ID of the instruction this result belongs to.
        success: Whether the instruction was executed successfully.
        result: The output data from the instruction handler.
        error: Error message if execution failed.
        latency_ms: Time taken to execute the instruction in milliseconds.
        metadata: Additional metadata from the execution.
    """
    instruction_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceAllocation:
    """
    Represents a memory or resource allocation within the AIVM.

    Attributes:
        allocation_id: Unique identifier for the allocation.
        resource_type: Type of resource (e.g., 'memory').
        requested_bytes: Number of bytes requested.
        allocated_bytes: Number of bytes actually allocated.
        granted: Whether the allocation request was granted.
        created_at: Timestamp when the allocation was made.
        released_at: Timestamp when the allocation was released.
    """
    allocation_id: str
    resource_type: str
    requested_bytes: int
    allocated_bytes: int
    granted: bool
    created_at: float = field(default_factory=time.time)
    released_at: Optional[float] = None


class ResourcePool:
    """Tracks and allocates system resources for AIVM operations."""

    def __init__(self, max_memory_mb: int = 512, max_threads: int = 4):
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.max_threads = max_threads
        self._memory_used = 0
        self._lock = threading.Lock()
        self._allocations: Dict[str, ResourceAllocation] = {}
        self._thread_usage = 0

    def allocate_memory(self, tag: str, size_bytes: int) -> ResourceAllocation:
        """
        Allocates memory from the pool.

        Args:
            tag: A string tag to associate with the allocation.
            size_bytes: The number of bytes to allocate.

        Returns:
            ResourceAllocation: An object containing details of the allocation.
        """
        with self._lock:
            alloc_id = f"mem_{tag}_{int(time.time() * 1000)}"
            if self._memory_used + size_bytes <= self.max_memory_bytes:
                self._memory_used += size_bytes
                alloc = ResourceAllocation(
                    allocation_id=alloc_id,
                    resource_type="memory",
                    requested_bytes=size_bytes,
                    allocated_bytes=size_bytes,
                    granted=True,
                )
                self._allocations[alloc_id] = alloc
                logger.debug(f"Memory allocated: {alloc_id} ({size_bytes} bytes)")
                return alloc
            else:
                alloc = ResourceAllocation(
                    allocation_id=alloc_id,
                    resource_type="memory",
                    requested_bytes=size_bytes,
                    allocated_bytes=0,
                    granted=False,
                )
                self._allocations[alloc_id] = alloc
                logger.warning(f"Memory allocation denied: {alloc_id} (requested {size_bytes}, available {self.available_memory})")
                return alloc

    def release_memory(self, allocation_id: str) -> bool:
        """
        Releases a previously allocated memory block back to the pool.

        Args:
            allocation_id: The ID of the allocation to release.

        Returns:
            bool: True if the allocation was found and released, False otherwise.
        """
        with self._lock:
            alloc = self._allocations.get(allocation_id)
            if not alloc:
                return False
            self._memory_used -= alloc.allocated_bytes
            alloc.released_at = time.time()
            logger.debug(f"Memory released: {allocation_id}")
            return True

    def acquire_thread(self) -> bool:
        """
        Attempts to acquire a worker thread from the pool.

        Returns:
            bool: True if a thread was successfully acquired, False otherwise.
        """
        with self._lock:
            if self._thread_usage < self.max_threads:
                self._thread_usage += 1
                return True
            return False

    def release_thread(self) -> None:
        """
        Releases a previously acquired worker thread back to the pool.
        """
        with self._lock:
            self._thread_usage = max(0, self._thread_usage - 1)

    @property
    def available_memory(self) -> int:
        """
        Calculates the amount of memory currently available in the pool.

        Returns:
            int: Available memory in bytes.
        """
        with self._lock:
            return self.max_memory_bytes - self._memory_used

    @property
    def memory_utilization(self) -> float:
        """
        Calculates the current memory utilization as a fraction of total capacity.

        Returns:
            float: Utilization between 0.0 and 1.0.
        """
        with self._lock:
            return self._memory_used / self.max_memory_bytes if self.max_memory_bytes > 0 else 0.0

    def stats(self) -> Dict[str, Any]:
        """
        Returns a dictionary of current resource pool statistics.

        Returns:
            Dict[str, Any]: A dictionary containing usage metrics.
        """
        with self._lock:
            return {
                "memory_used_mb": self._memory_used / (1024 * 1024),
                "memory_available_mb": self.available_memory / (1024 * 1024),
                "memory_utilization": self.memory_utilization,
                "thread_usage": self._thread_usage,
                "thread_capacity": self.max_threads,
                "active_allocations": len([a for a in self._allocations.values() if a.released_at is None]),
            }


class InstructionDispatcher:
    """
    Dispatches VM instructions to registered handlers.
    Handles concurrent execution with error recovery.
    """

    def __init__(self):
        """
        Initializes the InstructionDispatcher with an empty handler map and history.
        """
        self._lock = threading.RLock()
        self._handlers: Dict[InstructionType, Callable] = {}
        self._history: List[InstructionResult] = []
        self._max_history = 1000
        self._active_count = 0

    def register_handler(self, instruction_type: InstructionType, handler: Callable) -> None:
        """Register a handler for an instruction type."""
        with self._lock:
            self._handlers[instruction_type] = handler
            logger.info(f"Registered handler for {instruction_type.value}")

    def dispatch(self, instruction: VMInstruction) -> InstructionResult:
        """
        Dispatch a VM instruction to the appropriate handler.
        Returns InstructionResult with success status.
        """
        start = time.time()
        self._increment_active()

        try:
            with self._lock:
                handler = self._handlers.get(instruction.instruction_type)

            if not handler:
                result = InstructionResult(
                    instruction_id=instruction.instruction_id,
                    success=False,
                    error=f"No handler for {instruction.instruction_type.value}",
                    latency_ms=(time.time() - start) * 1000,
                )
            else:
                try:
                    result_data = handler(instruction.payload)
                    result = InstructionResult(
                        instruction_id=instruction.instruction_id,
                        success=True,
                        result=result_data,
                        latency_ms=(time.time() - start) * 1000,
                        metadata=instruction.metadata,
                    )
                except Exception as e:
                    logger.error(f"Handler error for {instruction.instruction_type.value}: {e}")
                    result = InstructionResult(
                        instruction_id=instruction.instruction_id,
                        success=False,
                        error=str(e),
                        latency_ms=(time.time() - start) * 1000,
                    )
        finally:
            self._decrement_active()

        self._add_history(result)
        return result

    def dispatch_batch(self, instructions: List[VMInstruction]) -> List[InstructionResult]:
        """
        Dispatches a list of instructions to be executed concurrently.

        Args:
            instructions: A list of VMInstruction objects to execute.

        Returns:
            List[InstructionResult]: A list of results for each instruction.
        """
        results = []
        threads = []
        results_lock = threading.Lock()

        def dispatch_one(instr: VMInstruction) -> InstructionResult:
            """
            Internal helper to dispatch a single instruction and collect the result.
            """
            r = self.dispatch(instr)
            with results_lock:
                results.append(r)

        for instr in instructions:
            t = threading.Thread(target=dispatch_one, args=(instr,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        return results

    def _increment_active(self) -> None:
        """
        Increments the count of currently active instructions.
        """
        with self._lock:
            self._active_count += 1

    def _decrement_active(self) -> None:
        """
        Decrements the count of currently active instructions.
        """
        with self._lock:
            self._active_count = max(0, self._active_count - 1)

    def _add_history(self, result: InstructionResult) -> None:
        """
        Adds an execution result to the history log, maintaining the max history size.

        Args:
            result: The InstructionResult to add to history.
        """
        with self._lock:
            self._history.append(result)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

    @property
    def active_count(self) -> int:
        """
        Returns the number of currently active instructions.

        Returns:
            int: The active instruction count.
        """
        with self._lock:
            return self._active_count

    def get_history(self, limit: int = 100) -> List[InstructionResult]:
        """
        Retrieves the most recent instruction execution results.

        Args:
            limit: The maximum number of history entries to return.

        Returns:
            List[InstructionResult]: A list of recent execution results.
        """
        with self._lock:
            return list(self._history[-limit:])

    def stats(self) -> Dict[str, Any]:
        """
        Returns summary statistics for the dispatcher.

        Returns:
            Dict[str, Any]: A dictionary containing instruction counts and handler info.
        """
        with self._lock:
            total = len(self._history)
            successful = sum(1 for r in self._history if r.success)
            failed = total - successful
            return {
                "total_instructions": total,
                "successful": successful,
                "failed": failed,
                "active": self._active_count,
                "registered_handlers": len(self._handlers),
            }


class ExecutionEngine:
    """
    Top-level AIVM execution engine.
    Wires instruction dispatcher, resource pool, and model loader together.
    Provides unified API for VM operations with error recovery.
    """

    def __init__(self, model_loader=None, max_memory_mb: int = 512, max_threads: int = 4):
        """
        Initializes the ExecutionEngine with a dispatcher, resource pool, and optional model loader.

        Args:
            model_loader: Optional model loader instance.
            max_memory_mb: Maximum memory allowed for the resource pool in MB.
            max_threads: Maximum number of threads for the resource pool.
        """
        self._dispatcher = InstructionDispatcher()
        self._resource_pool = ResourcePool(max_memory_mb=max_memory_mb, max_threads=max_threads)
        self._model_loader = model_loader
        self._recovery_handlers: Dict[str, Callable] = {}
        self._lock = threading.RLock()
        self._running = False

        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register built-in instruction handlers."""
        self._dispatcher.register_handler(InstructionType.HEALTH_CHECK, self._health_check)
        self._dispatcher.register_handler(InstructionType.GET_STATS, self._get_stats)
        self._dispatcher.register_handler(InstructionType.ALLOCATE_MEMORY, self._allocate_memory)
        self._dispatcher.register_handler(InstructionType.DEALLOCATE_MEMORY, self._deallocate_memory)
        self._dispatcher.register_handler(InstructionType.LOAD_MODEL, self._load_model)
        self._dispatcher.register_handler(InstructionType.UNLOAD_MODEL, self._unload_model)
        self._dispatcher.register_handler(InstructionType.RUN_INFERENCE, self._run_inference)
        self._dispatcher.register_handler(InstructionType.EMERGENCY_STOP, self._emergency_stop)

    def execute(self, instruction: VMInstruction) -> InstructionResult:
        """
        Executes a single VM instruction and handles error recovery.

        Args:
            instruction: The VMInstruction to execute.

        Returns:
            InstructionResult: The result of the instruction execution.
        """
        try:
            result = self._dispatcher.dispatch(instruction)
            if not result.success and instruction.instruction_type in self._recovery_handlers:
                recovery_fn = self._recovery_handlers[instruction.instruction_type.value]
                try:
                    recovery_fn(instruction, result)
                except Exception as e:
                    logger.error(f"Recovery handler failed: {e}")
            return result
        except Exception as e:
            logger.error(f"Execution error: {e}")
            return InstructionResult(
                instruction_id=instruction.instruction_id,
                success=False,
                error=str(e),
            )

    def execute_concurrent(self, instructions: List[VMInstruction]) -> List[InstructionResult]:
        """
        Executes multiple VM instructions concurrently.

        Args:
            instructions: A list of VMInstruction objects to execute.

        Returns:
            List[InstructionResult]: A list of results for the executed instructions.
        """
        return self._dispatcher.dispatch_batch(instructions)

    def register_recovery_handler(self, instruction_type: str, handler: Callable) -> None:
        """
        Registers a custom recovery handler for a specific instruction type.

        Args:
            instruction_type: The type of instruction to handle failures for.
            handler: A callable that will be invoked when an instruction fails.
        """
        with self._lock:
            self._recovery_handlers[instruction_type] = handler

    def _health_check(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Instruction handler for performing a system health check.

        Args:
            payload: The instruction payload (unused).

        Returns:
            Dict[str, Any]: A dictionary containing health status and component stats.
        """
        return {
            "status": "healthy" if self._running else "stopped",
            "timestamp": time.time(),
            "resource_pool": self._resource_pool.stats(),
            "dispatcher": self._dispatcher.stats(),
            "model_loader_stats": self._model_loader.stats() if self._model_loader else {},
        }

    def _get_stats(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Instruction handler for retrieving overall system statistics.

        Args:
            payload: The instruction payload (unused).

        Returns:
            Dict[str, Any]: A dictionary containing metrics from all subsystems.
        """
        return {
            "running": self._running,
            "resource_pool": self._resource_pool.stats(),
            "dispatcher": self._dispatcher.stats(),
            "model_loader": self._model_loader.stats() if self._model_loader else {},
        }

    def _allocate_memory(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Instruction handler for allocating memory from the resource pool.

        Args:
            payload: A dictionary containing 'tag' and 'size_bytes'.

        Returns:
            Dict[str, Any]: The result of the allocation request.
        """
        tag = payload.get("tag", "default")
        size_bytes = payload.get("size_bytes", 0)
        alloc = self._resource_pool.allocate_memory(tag, size_bytes)
        return {
            "allocation_id": alloc.allocation_id,
            "granted": alloc.granted,
            "allocated_bytes": alloc.allocated_bytes,
            "available_mb": self._resource_pool.available_memory / (1024 * 1024),
        }

    def _deallocate_memory(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Instruction handler for releasing memory back to the resource pool.

        Args:
            payload: A dictionary containing 'allocation_id'.

        Returns:
            Dict[str, Any]: Success status of the deallocation.
        """
        allocation_id = payload.get("allocation_id")
        if not allocation_id:
            return {"success": False, "error": "Missing allocation_id"}
        released = self._resource_pool.release_memory(allocation_id)
        return {"success": released, "allocation_id": allocation_id}

    def _load_model(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Instruction handler for loading a model via the model loader.

        Args:
            payload: A dictionary containing 'model_id' and 'model_path'.

        Returns:
            Dict[str, Any]: Success status of the model load.
        """
        if not self._model_loader:
            return {"success": False, "error": "No model loader configured"}
        model_id = payload.get("model_id")
        model_path = payload.get("model_path")
        if not model_id:
            return {"success": False, "error": "Missing model_id"}
        success = self._model_loader.load_model(model_id, model_path)
        return {"success": success, "model_id": model_id}

    def _unload_model(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Instruction handler for unloading a model.

        Args:
            payload: A dictionary containing 'model_id'.

        Returns:
            Dict[str, Any]: Success status of the model unload.
        """
        if not self._model_loader:
            return {"success": False, "error": "No model loader configured"}
        model_id = payload.get("model_id")
        if not model_id:
            return {"success": False, "error": "Missing model_id"}
        success = self._model_loader.unload_model(model_id)
        return {"success": success, "model_id": model_id}

    def _run_inference(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Instruction handler for running inference on a loaded model.

        Args:
            payload: A dictionary containing 'model_id', 'input_data', and 'timeout_seconds'.

        Returns:
            Dict[str, Any]: The inference result or error information.
        """
        if not self._model_loader:
            return {"success": False, "error": "No model loader configured"}
        model_id = payload.get("model_id")
        input_data = payload.get("input_data")
        timeout = payload.get("timeout_seconds")
        if not model_id:
            return {"success": False, "error": "Missing model_id"}
        result = self._model_loader.infer(model_id, input_data, timeout_seconds=timeout)
        return {
            "success": result.success,
            "output": result.output_data,
            "latency_ms": result.latency_ms,
            "error": result.error,
        }

    def _emergency_stop(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Instruction handler for triggering an emergency system stop.

        Args:
            payload: The instruction payload (unused).

        Returns:
            Dict[str, Any]: Confirmation of the stop command.
        """
        logger.warning("Emergency stop triggered")
        self._running = False
        return {"success": True, "stopped": True}

    @property
    def dispatcher(self) -> InstructionDispatcher:
        """
        Returns the instruction dispatcher instance.

        Returns:
            InstructionDispatcher: The dispatcher.
        """
        return self._dispatcher

    @property
    def resource_pool(self) -> ResourcePool:
        """
        Returns the resource pool instance.

        Returns:
            ResourcePool: The resource pool.
        """
        return self._resource_pool

    def start(self) -> None:
        """
        Starts the execution engine, enabling instruction processing.
        """
        self._running = True
        logger.info("ExecutionEngine started")

    def stop(self) -> None:
        """
        Stops the execution engine, preventing further instruction processing.
        """
        self._running = False
        logger.info("ExecutionEngine stopped")

    def stats(self) -> Dict[str, Any]:
        """
        Returns current performance and resource metrics for the engine.

        Returns:
            Dict[str, Any]: A dictionary containing status and usage statistics.
        """
        return {
            "running": self._running,
            "resource_pool": self._resource_pool.stats(),
            "dispatcher": self._dispatcher.stats(),
        }