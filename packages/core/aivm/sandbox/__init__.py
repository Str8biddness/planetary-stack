"""
AIVM Model Execution Sandbox
Provides isolated execution environments for Synthesus models.
"""
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
import uuid
import logging
import sys
import io
import contextlib

logger = logging.getLogger(__name__)


class IsolationLevel(Enum):
    """
    Enum defining the different levels of execution isolation available.
    """
    NONE = "none"
    PROCESS = "process"
    CONTAINER = "container"
    VM = "vm"


@dataclass
class SandboxConfig:
    """
    Configuration settings for an execution sandbox.

    Attributes:
        isolation_level: The degree of isolation for the sandbox.
        memory_limit_mb: Maximum memory allowed in MB.
        cpu_limit_percent: Percentage of CPU resources to allocate.
        timeout_seconds: Maximum execution time in seconds.
        allow_file_access: Whether the sandbox can access the filesystem.
        allow_network: Whether the sandbox has network access.
        max_threads: Maximum number of threads allowed in the sandbox.
    """
    isolation_level: IsolationLevel = IsolationLevel.PROCESS
    memory_limit_mb: int = 512
    cpu_limit_percent: float = 100.0
    timeout_seconds: float = 30.0
    allow_file_access: bool = True
    allow_network: bool = False
    max_threads: int = 4


@dataclass
class ExecutionResult:
    """
    Represents the output and metrics of a sandboxed execution.

    Attributes:
        output: The result from the executed function.
        error: Error message if execution failed.
        execution_time_ms: Time taken to execute in milliseconds.
        memory_used_mb: Memory consumed during execution in MB.
        sandbox_id: ID of the sandbox used for execution.
    """
    output: Any
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    memory_used_mb: float = 0.0
    sandbox_id: str = ""


class ModelSandbox:
    """
    Isolated execution sandbox for model inference.
    Provides process-level isolation with resource limits.
    """

    def __init__(self, sandbox_id: str, config: SandboxConfig, model_id: str):
        self.sandbox_id = sandbox_id
        self.config = config
        self.model_id = model_id
        self._active = False
        self._execution_count = 0
        self._created_at = time.time()
        self._lock = threading.RLock()
        self._context: Dict[str, Any] = {}

    def execute(self, fn: Callable, *args, **kwargs) -> ExecutionResult:
        """
        Executes a function within the sandbox with resource monitoring and limits.

        Args:
            fn: The callable to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            ExecutionResult: An object containing the output and execution metrics.
        """
        if not self._active:
            return ExecutionResult(
                output=None,
                error="Sandbox not active",
                sandbox_id=self.sandbox_id,
            )

        start_time = time.time()
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        timeout = self.config.timeout_seconds

        try:
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError(f"Sandbox execution timed out after {timeout}s")

            # Set timeout alarm (only works on Unix)
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(timeout))

            try:
                with contextlib.redirect_stdout(stdout_capture), \
                     contextlib.redirect_stderr(stderr_capture):
                    result = fn(*args, **kwargs)
            finally:
                signal.alarm(0)  # Cancel alarm

            execution_time = (time.time() - start_time) * 1000
            self._execution_count += 1

            return ExecutionResult(
                output=result,
                execution_time_ms=execution_time,
                sandbox_id=self.sandbox_id,
            )

        except TimeoutError as e:
            execution_time = (time.time() - start_time) * 1000
            return ExecutionResult(
                output=None,
                error=str(e),
                execution_time_ms=execution_time,
                sandbox_id=self.sandbox_id,
            )
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error_msg = f"{type(e).__name__}: {str(e)}"
            if stderr_capture.getvalue():
                error_msg += f"\nStderr: {stderr_capture.getvalue()}"
            return ExecutionResult(
                output=None,
                error=error_msg,
                execution_time_ms=execution_time,
                sandbox_id=self.sandbox_id,
            )

    def set_context(self, key: str, value: Any):
        """
        Sets a persistent context value for the sandbox.

        Args:
            key: The context key.
            value: The value to store.
        """
        with self._lock:
            self._context[key] = value

    def get_context(self, key: str) -> Any:
        """
        Retrieves a context value from the sandbox.

        Args:
            key: The key of the context value to retrieve.

        Returns:
            Any: The stored value or None if not found.
        """
        return self._context.get(key)

    def clear_context(self):
        """
        Clears all stored context from the sandbox.
        """
        self._context.clear()

    def activate(self):
        """
        Activates the sandbox, allowing it to process execution requests.
        """
        self._active = True
        logger.info(f"Sandbox {self.sandbox_id} activated for model {self.model_id}")

    def deactivate(self):
        """
        Deactivates the sandbox and stops all processing.
        """
        self._active = False
        logger.info(f"Sandbox {self.sandbox_id} deactivated")

    def get_stats(self) -> Dict[str, Any]:
        """
        Returns operational statistics for the sandbox.

        Returns:
            Dict[str, Any]: A dictionary containing current status and metrics.
        """
        return {
            "sandbox_id": self.sandbox_id,
            "model_id": self.model_id,
            "active": self._active,
            "execution_count": self._execution_count,
            "uptime_seconds": time.time() - self._created_at,
            "isolation_level": self.config.isolation_level.value,
            "memory_limit_mb": self.config.memory_limit_mb,
            "timeout_seconds": self.config.timeout_seconds,
        }


class SandboxManager:
    """
    Manages multiple model sandboxes with hot-swap support.
    """

    def __init__(self, default_config: SandboxConfig = None):
        self._sandboxes: Dict[str, ModelSandbox] = {}
        self._default_config = default_config or SandboxConfig()
        self._lock = threading.RLock()
        self._active_model_id: Optional[str] = None
        self._execution_history: List[Dict[str, Any]] = []

    def create_sandbox(self, model_id: str, config: SandboxConfig = None) -> str:
        """
        Creates and activates a new sandbox for a specific model.

        Args:
            model_id: The ID of the model.
            config: Optional configuration for the new sandbox.

        Returns:
            str: The unique ID of the created sandbox.
        """
        sandbox_id = str(uuid.uuid4())
        config = config or self._default_config

        with self._lock:
            sandbox = ModelSandbox(sandbox_id, config, model_id)
            sandbox.activate()
            self._sandboxes[sandbox_id] = sandbox
            self._sandboxes[model_id] = sandbox  # Also index by model_id

        logger.info(f"Created sandbox {sandbox_id} for model {model_id}")
        return sandbox_id

    def destroy_sandbox(self, sandbox_id: str) -> bool:
        """
        Deactivates and removes a sandbox from the manager.

        Args:
            sandbox_id: The ID of the sandbox to destroy.

        Returns:
            bool: True if the sandbox was found and destroyed, False otherwise.
        """
        with self._lock:
            if sandbox_id in self._sandboxes:
                sandbox = self._sandboxes[sandbox_id]
                sandbox.deactivate()
                del self._sandboxes[sandbox_id]
                logger.info(f"Destroyed sandbox {sandbox_id}")
                return True
        return False

    def get_sandbox(self, sandbox_id: str = None, model_id: str = None) -> Optional[ModelSandbox]:
        """
        Retrieves a sandbox instance by its ID or associated model ID.

        Args:
            sandbox_id: Optional ID of the sandbox.
            model_id: Optional ID of the model.

        Returns:
            Optional[ModelSandbox]: The sandbox instance or None if not found.
        """
        with self._lock:
            if sandbox_id:
                return self._sandboxes.get(sandbox_id)
            if model_id:
                return self._sandboxes.get(model_id)
        return None

    def execute_in_sandbox(
        self,
        fn: Callable,
        model_id: str,
        *args,
        create_if_missing: bool = True,
        **kwargs
    ) -> ExecutionResult:
        """
        Executes a function in a model's sandbox, creating it if necessary.

        Args:
            fn: The function to execute.
            model_id: The ID of the model.
            *args: Arguments for the function.
            create_if_missing: If True, creates a sandbox if one doesn't exist.
            **kwargs: Keyword arguments for the function.

        Returns:
            ExecutionResult: The result of the sandboxed execution.
        """
        sandbox = self.get_sandbox(model_id=model_id)

        if not sandbox and create_if_missing:
            self.create_sandbox(model_id)
            sandbox = self.get_sandbox(model_id=model_id)

        if not sandbox:
            return ExecutionResult(
                output=None,
                error=f"No sandbox for model {model_id}",
            )

        result = sandbox.execute(fn, *args, **kwargs)
        self._execution_history.append({
            "model_id": model_id,
            "sandbox_id": sandbox.sandbox_id,
            "execution_time_ms": result.execution_time_ms,
            "error": result.error,
            "timestamp": time.time(),
        })
        if len(self._execution_history) > 1000:
            self._execution_history = self._execution_history[-500:]

        return result

    def hotswap_model(self, old_model_id: str, new_model_id: str, new_config: SandboxConfig = None) -> bool:
        """
        Replaces the model associated with an existing sandbox.

        Args:
            old_model_id: The current model ID.
            new_model_id: The new model ID.
            new_config: Optional new configuration for the sandbox.

        Returns:
            bool: True if the swap was successful, False otherwise.
        """
        sandbox = self.get_sandbox(model_id=old_model_id)
        if not sandbox:
            return False

        with self._lock:
            sandbox.model_id = new_model_id
            if new_config:
                sandbox.config = new_config

        logger.info(f"Hot-swapped model {old_model_id} -> {new_model_id}")
        return True

    def list_sandboxes(self) -> List[Dict[str, Any]]:
        """
        Returns a list of all managed sandboxes and their status.

        Returns:
            List[Dict[str, Any]]: A list of status dictionaries.
        """
        with self._lock:
            return [
                {"sandbox_id": k, **s.get_stats()}
                for k, s in self._sandboxes.items()
                if isinstance(s, ModelSandbox)
            ]

    def get_manager_stats(self) -> Dict[str, Any]:
        """
        Returns aggregate statistics for the sandbox manager.

        Returns:
            Dict[str, Any]: A dictionary containing overall status and history.
        """
        with self._lock:
            active = sum(1 for s in self._sandboxes.values() if s._active)
            total_executions = sum(s._execution_count for s in self._sandboxes.values())
            return {
                "total_sandboxes": len(self._sandboxes),
                "active_sandboxes": active,
                "total_executions": total_executions,
                "history_size": len(self._execution_history),
            }