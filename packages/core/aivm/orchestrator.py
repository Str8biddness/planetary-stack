"""
AIVM Orchestrator — Top-level unified interface for all AIVM components.

Wires together:
- ExecutionEngine (instruction dispatcher + resource pool)
- ModelLoader (hot-swap model management)
- ModelIsolationLayer (session pools + model isolation)
- SandboxManager (execution sandboxing with SIGALRM timeout)
- ExecutionContextManager (context lifecycle + snapshots)
- InferenceScheduler (priority queue + concurrent execution)
- ErrorRecoveryManager (circuit breakers + retry logic)

Provides a single entry point for AIVM operations with proper error recovery
and concurrent multi-model support.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .execution_engine import (
    ExecutionEngine,
    InstructionDispatcher,
    InstructionResult,
    InstructionType,
    ResourcePool,
    VMInstruction,
)
from .model_loader import (
    InferenceResult as ModelInferenceResult,
    ModelLoader,
    ModelState,
)
from .isolation_layer import ModelIsolationLayer, ModelIsolationConfig, IsolationMode
from .sandbox import SandboxManager, SandboxConfig, ModelSandbox, IsolationLevel
from .context_manager import ExecutionContextManager, ContextState, ExecutionContext
from .inference_scheduler import InferenceScheduler, InferencePriority, InferenceRequest
from .error_recovery import (
    ErrorRecoveryManager,
    ErrorSeverity,
    CircuitBreakerConfig,
    CircuitState,
    ErrorRecord,
)

logger = logging.getLogger(__name__)


class AIVMStatus(Enum):
    """
    Enum representing the operational status of the AIVM Orchestrator.
    """
    STOPPED = "stopped"
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"


@dataclass
class AIVMConfig:
    """
    Configuration settings for the AIVM Orchestrator.

    Attributes:
        max_memory_mb: Maximum memory allowed for AIVM operations in MB.
        max_threads: Maximum number of worker threads for instruction execution.
        max_concurrent_inference: Maximum number of concurrent inference requests.
        max_contexts: Maximum number of active execution contexts.
        sandbox_timeout_seconds: Default timeout for sandboxed execution in seconds.
        sandbox_memory_mb: Memory limit for sandboxed processes in MB.
        inference_queue_size: Maximum size of the inference request queue.
        enable_error_recovery: Whether to enable automatic error recovery.
        enable_circuit_breakers: Whether to enable circuit breakers for components.
        circuit_breaker_threshold: Number of failures before a circuit breaker opens.
        circuit_breaker_recovery_seconds: Time to wait before attempting circuit breaker recovery.
    """
    max_memory_mb: int = 512
    max_threads: int = 4
    max_concurrent_inference: int = 4
    max_contexts: int = 64
    sandbox_timeout_seconds: float = 30.0
    sandbox_memory_mb: int = 512
    inference_queue_size: int = 1000
    enable_error_recovery: bool = True
    enable_circuit_breakers: bool = True
    circuit_breaker_threshold: int = 5
    circuit_breaker_recovery_seconds: float = 30.0


class AIVMOrchestrator:
    """
    Unified orchestrator for all AIVM infrastructure components.
    
    Provides a single entry point for model management, inference execution,
    and resource allocation with built-in error recovery and concurrent
    multi-model support.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initializes the AIVMOrchestrator and all its underlying components.

        Sets up the model loader, execution engine, isolation layer, sandbox manager,
        context manager, inference scheduler, and error recovery manager.

        Args:
            config: Optional dictionary containing configuration overrides for AIVMConfig.
        """
        self._config = AIVMConfig(**(config or {}))
        self._status = AIVMStatus.STOPPED
        self._lock = threading.RLock()
        self._start_time: Optional[float] = None

        # Core engine components
        self._model_loader = ModelLoader(
            models_dir="data/models",
            default_timeout=self._config.sandbox_timeout_seconds,
        )
        self._execution_engine = ExecutionEngine(
            model_loader=self._model_loader,
            max_memory_mb=self._config.max_memory_mb,
            max_threads=self._config.max_threads,
        )

        # Isolation and sandboxing
        isolation_config = ModelIsolationConfig(
            mode=IsolationMode.HARD,
            max_sessions_per_model=self._config.max_concurrent_inference,
            session_timeout_seconds=300.0,
            memory_threshold_mb=float(self._config.sandbox_memory_mb),
        )
        self._isolation_layer = ModelIsolationLayer(config=isolation_config)
        self._sandbox_manager = SandboxManager(
            default_config=SandboxConfig(
                isolation_level=IsolationLevel.PROCESS,
                memory_limit_mb=self._config.sandbox_memory_mb,
                timeout_seconds=self._config.sandbox_timeout_seconds,
            )
        )

        # Context and scheduling
        self._context_manager = ExecutionContextManager(max_contexts=self._config.max_contexts)
        self._inference_scheduler = InferenceScheduler(
            max_concurrent_per_model=self._config.max_concurrent_inference,
            max_queue_size=self._config.inference_queue_size,
        )

        # Error recovery
        self._error_recovery = ErrorRecoveryManager()
        self._setup_circuit_breakers()
        self._setup_recovery_handlers()

        # Model handler registry
        self._model_handlers: Dict[str, Callable] = {}

    def _setup_circuit_breakers(self):
        """
        Initializes circuit breakers for critical AIVM components.

        Sets up circuit breakers for the dispatcher, model loader, and inference
        scheduler based on the provided configuration.
        """
        if not self._config.enable_circuit_breakers:
            return

        cb_config = CircuitBreakerConfig(
            failure_threshold=self._config.circuit_breaker_threshold,
            recovery_timeout_seconds=self._config.circuit_breaker_recovery_seconds,
        )

        self._error_recovery.register_circuit_breaker("dispatcher", cb_config)
        self._error_recovery.register_circuit_breaker("model_loader", cb_config)
        self._error_recovery.register_circuit_breaker("inference_scheduler", cb_config)

    def _setup_recovery_handlers(self):
        """
        Registers recovery handlers for various component failures.

        Configures handlers to attempt automatic recovery for model loader
        and inference scheduler errors.
        """
        if not self._config.enable_error_recovery:
            return

        self._error_recovery.register_recovery_handler(
            "model_loader", self._recovery_reload_model
        )
        self._error_recovery.register_recovery_handler(
            "inference_scheduler", self._recovery_retry_inference
        )

    def _recovery_reload_model(self, error: ErrorRecord):
        """
        Attempts to reload a model that has failed.

        Args:
            error: The error record containing context about the failure.
        """
        model_id = error.context.get("model_id")
        if not model_id:
            return
        logger.info(f"Recovery: attempting reload of model {model_id}")
        self._model_loader.load_model(model_id)

    def _recovery_retry_inference(self, error: ErrorRecord):
        """
        Logs a failed inference attempt for potential retry or analysis.

        Args:
            error: The error record containing context about the failure.
        """
        logger.warning(f"Recovery: inference failed, context={error.context}")

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def initialize(self) -> bool:
        """
        Initializes all AIVM components and starts background services.

        Returns:
            bool: True if initialization was successful, False otherwise.
        """
        with self._lock:
            if self._status != AIVMStatus.STOPPED:
                return True

            self._status = AIVMStatus.INITIALIZING
            try:
                self._execution_engine.start()
                self._inference_scheduler.start()
                self._status = AIVMStatus.RUNNING
                self._start_time = time.time()
                logger.info("AIVM Orchestrator initialized successfully")
                return True
            except Exception as e:
                self._status = AIVMStatus.STOPPED
                self._error_recovery.record_error(
                    component="orchestrator",
                    error_type="initialization",
                    message=str(e),
                    severity=ErrorSeverity.CRITICAL,
                )
                logger.error(f"AIVM initialization failed: {e}")
                return False

    def shutdown(self):
        """
        Gracefully shuts down all AIVM components and stops services.

        Ensures all models are unloaded and worker threads are terminated.
        """
        with self._lock:
            if self._status == AIVMStatus.STOPPED:
                return

            self._status = AIVMStatus.STOPPING
            try:
                self._inference_scheduler.stop()
                self._execution_engine.stop()

                # Unload all models
                for model_id in list(self._model_loader.list_loaded_models().keys()):
                    try:
                        self._model_loader.unload_model(model_id)
                    except Exception as e:
                        logger.warning(f"Error unloading model {model_id}: {e}")

                self._status = AIVMStatus.STOPPED
                logger.info("AIVM Orchestrator shutdown complete")
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
                self._status = AIVMStatus.STOPPED

    @property
    def status(self) -> AIVMStatus:
        """
        Gets the current operational status of the AIVM Orchestrator.

        Returns:
            AIVMStatus: The current status enum value.
        """
        return self._status

    @property
    def is_running(self) -> bool:
        """
        Checks if the AIVM Orchestrator is currently in the RUNNING state.

        Returns:
            bool: True if running, False otherwise.
        """
        return self._status == AIVMStatus.RUNNING

    # -------------------------------------------------------------------------
    # Model Management
    # -------------------------------------------------------------------------

    def load_model(
        self,
        model_id: str,
        model_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Load a model with hot-swap support.
        
        Args:
            model_id: Unique identifier for the model
            model_path: Optional explicit path to model file
            metadata: Optional model metadata
            
        Returns:
            True if load succeeded
        """
        try:
            success = self._model_loader.load_model(model_id, model_path, metadata)
            if success:
                self._isolation_layer.register_model(model_id, model_path or f"data/models/{model_id}.onnx")
            return success
        except Exception as e:
            self._error_recovery.record_error(
                component="model_loader",
                error_type="load_failure",
                message=str(e),
                severity=ErrorSeverity.ERROR,
                context={"model_id": model_id},
            )
            return False

    def unload_model(self, model_id: str) -> bool:
        """
        Unloads a specific model and reclaims its associated resources.

        Args:
            model_id: The unique identifier of the model to unload.

        Returns:
            bool: True if the model was successfully unloaded, False otherwise.
        """
        try:
            self._isolation_layer.unload_model(model_id)
            return self._model_loader.unload_model(model_id)
        except Exception as e:
            self._error_recovery.record_error(
                component="model_loader",
                error_type="unload_failure",
                message=str(e),
                severity=ErrorSeverity.WARNING,
                context={"model_id": model_id},
            )
            return False

    def hotswap_model(self, old_model_id: str, new_model_id: str) -> bool:
        """
        Atomically swap one model for another.
        
        Args:
            old_model_id: Model to unload
            new_model_id: Model to load
            
        Returns:
            True if swap succeeded
        """
        try:
            # Check circuit breaker
            cb = self._error_recovery.get_circuit_breaker("model_loader")
            if cb and not cb.can_execute():
                logger.warning("Circuit breaker open for model_loader, hotswap rejected")
                return False

            # Perform swap
            old_info = self._model_loader.get_model_info(old_model_id)
            if not old_info:
                logger.error(f"Old model {old_model_id} not loaded")
                return False

            new_path = f"data/models/{new_model_id}.onnx"
            
            self._isolation_layer.hotswap_model(old_model_id, new_model_id)
            
            if self._model_loader.unload_model(old_model_id):
                success = self._model_loader.load_model(new_model_id, new_path)
                if success:
                    cb.record_success() if cb else None
                    logger.info(f"Hot-swap {old_model_id} -> {new_model_id} completed")
                    return True
                else:
                    cb.record_failure() if cb else None
                    # Try to restore old model
                    self._model_loader.load_model(old_model_id, old_info.model_path)
                    return False
            return False
        except Exception as e:
            self._error_recovery.record_error(
                component="model_loader",
                error_type="hotswap_failure",
                message=str(e),
                severity=ErrorSeverity.ERROR,
                context={"old_model_id": old_model_id, "new_model_id": new_model_id},
            )
            cb = self._error_recovery.get_circuit_breaker("model_loader")
            cb.record_failure() if cb else None
            return False

    # -------------------------------------------------------------------------
    # Inference Execution
    # -------------------------------------------------------------------------

    def register_model_handler(self, model_id: str, handler: Callable):
        """
        Register an inference handler for a model.
        
        Args:
            model_id: Model identifier
            handler: Callable that takes input_data dict and returns output
        """
        self._model_handlers[model_id] = handler
        self._inference_scheduler.register_model(model_id, handler)
        logger.info(f"Registered inference handler for model {model_id}")

    def run_inference(
        self,
        model_id: str,
        input_data: Dict[str, Any],
        timeout_seconds: Optional[float] = None,
        priority: InferencePriority = InferencePriority.NORMAL,
    ) -> Optional[Dict[str, Any]]:
        """
        Run inference on a model with sandboxed execution.
        
        Args:
            model_id: Model to run
            input_data: Input data dict
            timeout_seconds: Optional timeout override
            priority: Inference priority level
            
        Returns:
            Inference result dict or None on failure
        """
        if not self.is_running:
            logger.error("AIVM orchestrator not running")
            return None

        request = InferenceRequest(
            request_id=str(uuid.uuid4()),
            model_id=model_id,
            input_data=input_data,
            priority=priority,
            timeout_seconds=timeout_seconds or self._config.sandbox_timeout_seconds,
        )

        try:
            result = self._inference_scheduler.submit_and_wait(request)
            if result.error:
                self._error_recovery.record_error(
                    component="inference_scheduler",
                    error_type="inference_failure",
                    message=result.error,
                    severity=ErrorSeverity.ERROR,
                    context={"model_id": model_id, "request_id": request.request_id},
                )
            return {
                "request_id": result.request_id,
                "model_id": result.model_id,
                "output": result.output,
                "error": result.error,
                "execution_time_ms": result.execution_time_ms,
                "queued_time_ms": result.queued_time_ms,
            }
        except Exception as e:
            self._error_recovery.record_error(
                component="inference_scheduler",
                error_type="inference_exception",
                message=str(e),
                severity=ErrorSeverity.ERROR,
                context={"model_id": model_id},
            )
            return None

    def run_inference_async(
        self,
        model_id: str,
        input_data: Dict[str, Any],
        callback: Optional[Callable] = None,
        timeout_seconds: Optional[float] = None,
        priority: InferencePriority = InferencePriority.NORMAL,
    ) -> str:
        """
        Submit inference request asynchronously.
        
        Returns request_id that can be used with get_inference_result().
        """
        request = InferenceRequest(
            request_id=str(uuid.uuid4()),
            model_id=model_id,
            input_data=input_data,
            priority=priority,
            timeout_seconds=timeout_seconds or self._config.sandbox_timeout_seconds,
            callback=callback,
        )
        return self._inference_scheduler.submit(request)

    def get_inference_result(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get result of an async inference request."""
        result = self._inference_scheduler.get_result(request_id)
        if not result:
            return None
        return {
            "request_id": result.request_id,
            "model_id": result.model_id,
            "output": result.output,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms,
            "queued_time_ms": result.queued_time_ms,
        }

    # -------------------------------------------------------------------------
    # Context Management
    # -------------------------------------------------------------------------

    def create_context(
        self,
        model_id: str,
        session_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        isolation_level: int = 1,
    ) -> Optional[str]:
        """Create an isolated execution context for a model."""
        try:
            return self._context_manager.create_context(
                model_id=model_id,
                session_data=session_data,
                metadata=metadata,
                isolation_level=isolation_level,
            )
        except Exception as e:
            self._error_recovery.record_error(
                component="context_manager",
                error_type="create_context_failure",
                message=str(e),
                severity=ErrorSeverity.ERROR,
                context={"model_id": model_id},
            )
            return None

    def initialize_context(self, context_id: str) -> bool:
        """Initialize a created context (transition to READY)."""
        return self._context_manager.initialize_context(context_id)

    def terminate_context(self, context_id: str) -> bool:
        """Terminate and cleanup a context."""
        return self._context_manager.terminate_context(context_id)

    def get_context(self, context_id: str) -> Optional[ExecutionContext]:
        """Get context details by ID."""
        return self._context_manager.get_context(context_id)

    def update_context_data(self, context_id: str, key: str, value: Any) -> bool:
        """Update session data in a context."""
        return self._context_manager.update_session_data(context_id, key, value)

    def get_context_data(self, context_id: str, key: str) -> Any:
        """Get session data from a context."""
        return self._context_manager.get_session_data(context_id, key)

    # -------------------------------------------------------------------------
    # Sandbox Execution
    # -------------------------------------------------------------------------

    def execute_in_sandbox(
        self,
        fn: Callable,
        model_id: str,
        *args,
        **kwargs,
    ):
        """Execute a function within a model's sandbox."""
        return self._sandbox_manager.execute_in_sandbox(fn, model_id, *args, **kwargs)

    def create_sandbox(
        self,
        model_id: str,
        memory_limit_mb: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ) -> Optional[str]:
        """Create an execution sandbox for a model."""
        config = SandboxConfig(
            memory_limit_mb=memory_limit_mb or self._config.sandbox_memory_mb,
            timeout_seconds=timeout_seconds or self._config.sandbox_timeout_seconds,
        )
        return self._sandbox_manager.create_sandbox(model_id, config)

    def destroy_sandbox(self, model_id: str) -> bool:
        """Destroy a model's sandbox."""
        return self._sandbox_manager.destroy_sandbox(model_id)

    # -------------------------------------------------------------------------
    # VM Instructions
    # -------------------------------------------------------------------------

    def execute_instruction(self, instruction: VMInstruction) -> InstructionResult:
        """Execute a VM instruction through the dispatcher."""
        return self._execution_engine.execute(instruction)

    def dispatch_instruction(
        self,
        instruction_type: InstructionType,
        payload: Optional[Dict[str, Any]] = None,
        priority: int = 0,
        timeout_seconds: float = 30.0,
    ) -> InstructionResult:
        """Convenience method to dispatch a typed instruction."""
        instruction = VMInstruction(
            instruction_id=str(uuid.uuid4()),
            instruction_type=instruction_type,
            payload=payload or {},
            priority=priority,
            timeout_seconds=timeout_seconds,
        )
        return self.execute_instruction(instruction)

    # -------------------------------------------------------------------------
    # Resource Management
    # -------------------------------------------------------------------------

    def allocate_memory(self, tag: str, size_bytes: int) -> Dict[str, Any]:
        """Allocate memory through the resource pool."""
        result = self.dispatch_instruction(
            InstructionType.ALLOCATE_MEMORY,
            {"tag": tag, "size_bytes": size_bytes},
        )
        return result.result or {}

    def release_memory(self, allocation_id: str) -> bool:
        """Release a memory allocation."""
        result = self.dispatch_instruction(
            InstructionType.DEALLOCATE_MEMORY,
            {"allocation_id": allocation_id},
        )
        return result.success

    def get_resource_stats(self) -> Dict[str, Any]:
        """Get current resource allocation statistics."""
        return self._execution_engine.resource_pool.stats()

    # -------------------------------------------------------------------------
    # Health & Status
    # -------------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Perform health check across all components."""
        result = self.dispatch_instruction(InstructionType.HEALTH_CHECK)
        return result.result or {}

    def get_full_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all AIVM components."""
        uptime = time.time() - self._start_time if self._start_time else 0.0

        return {
            "status": self._status.value,
            "initialized": self._status != AIVMStatus.STOPPED,
            "running": self.is_running,
            "uptime_seconds": uptime,
            "execution_engine": self._execution_engine.stats(),
            "model_loader": self._model_loader.stats(),
            "inference_scheduler": self._inference_scheduler.get_stats(),
            "sandbox_manager": self._sandbox_manager.get_manager_stats(),
            "context_manager": self._context_manager.get_stats(),
            "isolation_layer": self._isolation_layer.get_stats(),
            "error_recovery": self._error_recovery.get_stats(),
            "config": {
                "max_memory_mb": self._config.max_memory_mb,
                "max_threads": self._config.max_threads,
                "max_concurrent_inference": self._config.max_concurrent_inference,
                "sandbox_timeout_seconds": self._config.sandbox_timeout_seconds,
            },
        }

    # -------------------------------------------------------------------------
    # Error Recovery
    # -------------------------------------------------------------------------

    def get_circuit_breaker_state(self, name: str) -> Optional[str]:
        """Get the state of a circuit breaker."""
        cb = self._error_recovery.get_circuit_breaker(name)
        return cb.state.value if cb else None

    def reset_circuit_breaker(self, name: str):
        """Manually reset a circuit breaker to closed state."""
        cb = self._error_recovery.get_circuit_breaker(name)
        if cb:
            cb._state = CircuitState.CLOSED
            cb._failure_count = 0
            logger.info(f"Circuit breaker {name} manually reset")

    def get_unresolved_errors(self, component: Optional[str] = None) -> List[ErrorRecord]:
        """Get unresolved errors, optionally filtered by component."""
        return self._error_recovery.get_unresolved_errors(component)

    # -------------------------------------------------------------------------
    # Properties for test access
    # -------------------------------------------------------------------------

    @property
    def _dispatcher(self) -> InstructionDispatcher:
        """Internal property to access the instruction dispatcher from the execution engine.

        Returns:
            The InstructionDispatcher instance.
        """
        return self._execution_engine.dispatcher

    @property
    def _resource_allocator(self):
        """Internal property to access the resource pool allocator from the execution engine.

        Returns:
            The ResourcePool instance.
        """
        return self._execution_engine.resource_pool