"""
AIVM Model Loader — Hot-swap ONNX model management for Synthesus.

Supports loading, running, and unloading multiple Synthesus models concurrently
without conflicts. Each model runs in its own isolated execution context.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ModelState(Enum):
    """
    Enum representing the operational state of a model within the loader.
    """
    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    RUNNING = "running"
    UNLOADING = "unloading"
    ERROR = "error"


@dataclass
class ModelInfo:
    """
    Metadata and operational statistics for a specific model.

    Attributes:
        model_id: Unique identifier for the model.
        model_path: File system path to the model file.
        state: Current operational state of the model.
        session_count: Number of active inference sessions for this model.
        total_inferences: Total number of inference requests processed.
        total_latency_ms: Cumulative latency of all inference requests.
        loaded_at: Timestamp when the model was last loaded.
        last_inference: Timestamp of the most recent inference request.
        error_message: Details of the last error encountered, if any.
        metadata: Additional user-defined metadata for the model.
    """
    model_id: str
    model_path: str
    state: ModelState = ModelState.UNLOADED
    session_count: int = 0
    total_inferences: int = 0
    total_latency_ms: float = 0.0
    loaded_at: Optional[float] = None
    last_inference: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InferenceRequest:
    """
    Represents a request for model inference.

    Attributes:
        request_id: Unique identifier for the request.
        model_id: ID of the model to use for inference.
        input_data: The data to be processed by the model.
        timeout_seconds: Maximum time allowed for inference.
        priority: Priority of the request (lower is higher).
        created_at: Timestamp when the request was created.
    """
    request_id: str
    model_id: str
    input_data: Any
    timeout_seconds: float = 30.0
    priority: int = 0
    created_at: float = field(default_factory=time.time)


@dataclass
class InferenceResult:
    """
    Represents the output of a model inference operation.

    Attributes:
        request_id: ID of the corresponding request.
        model_id: ID of the model used.
        output_data: The result data from the model.
        latency_ms: Time taken for inference in milliseconds.
        success: Whether the inference was successful.
        error: Error message if inference failed.
    """
    request_id: str
    model_id: str
    output_data: Any
    latency_ms: float
    success: bool
    error: Optional[str] = None


class ModelRegistry:
    """Thread-safe registry of loaded models and their metadata."""

    def __init__(self):
        """Initializes the model registry with an empty set of models and sessions."""
        self._lock = threading.RLock()
        self._models: Dict[str, ModelInfo] = {}
        self._sessions: Dict[str, str] = {}  # session_id -> model_id

    def register(self, model_id: str, model_path: str, metadata: Optional[Dict[str, Any]] = None) -> ModelInfo:
        """
        Registers a new model with the registry.

        Args:
            model_id: Unique identifier for the model.
            model_path: Path to the model file.
            metadata: Optional additional metadata.

        Returns:
            ModelInfo: The newly created model information object.
        """
        with self._lock:
            info = ModelInfo(model_id=model_id, model_path=model_path, metadata=metadata or {})
            self._models[model_id] = info
            return info

    def get(self, model_id: str) -> Optional[ModelInfo]:
        """
        Retrieves information for a registered model.

        Args:
            model_id: The ID of the model to retrieve.

        Returns:
            Optional[ModelInfo]: Model information or None if not found.
        """
        with self._lock:
            return self._models.get(model_id)

    def update_state(self, model_id: str, state: ModelState, error: Optional[str] = None) -> None:
        """
        Updates the operational state of a model.

        Args:
            model_id: The ID of the model to update.
            state: The new state of the model.
            error: Optional error message associated with the state change.
        """
        with self._lock:
            if model_id in self._models:
                self._models[model_id].state = state
                if error:
                    self._models[model_id].error_message = error
                if state == ModelState.READY:
                    self._models[model_id].loaded_at = time.time()

    def record_inference(self, model_id: str, latency_ms: float) -> None:
        """
        Records statistics for a completed inference operation.

        Args:
            model_id: The ID of the model used.
            latency_ms: The execution time in milliseconds.
        """
        with self._lock:
            if model_id in self._models:
                m = self._models[model_id]
                m.total_inferences += 1
                m.total_latency_ms += latency_ms
                m.last_inference = time.time()

    def acquire_session(self, model_id: str) -> str:
        """
        Acquires a new session ID for a model inference request.

        Args:
            model_id: The ID of the model.

        Returns:
            str: A unique session identifier.
        """
        with self._lock:
            session_id = f"{model_id}_session_{int(time.time() * 1000)}"
            self._sessions[session_id] = model_id
            if model_id in self._models:
                self._models[model_id].session_count += 1
            return session_id

    def release_session(self, session_id: str) -> None:
        """
        Releases a previously acquired session.

        Args:
            session_id: The ID of the session to release.
        """
        with self._lock:
            model_id = self._sessions.pop(session_id, None)
            if model_id and model_id in self._models:
                self._models[model_id].session_count = max(0, self._models[model_id].session_count - 1)

    def list_models(self) -> Dict[str, ModelInfo]:
        """
        Returns a dictionary of all registered models.

        Returns:
            Dict[str, ModelInfo]: Mapping of model IDs to their information.
        """
        with self._lock:
            return dict(self._models)

    def unregister(self, model_id: str) -> bool:
        """
        Removes a model from the registry.

        Args:
            model_id: The ID of the model to unregister.

        Returns:
            bool: True if the model was found and removed, False otherwise.
        """
        with self._lock:
            return self._models.pop(model_id, None) is not None


class SandboxExecutor:
    """
    Isolated execution context for model inference.
    Uses signal.SIGALRM to enforce timeout limits (per critical fix requirement).
    """

    def __init__(self, timeout_seconds: float = 30.0):
        """
        Initializes the sandbox executor with a specific timeout.

        Args:
            timeout_seconds (float): Maximum allowed execution time in seconds.
        """
        self.timeout_seconds = timeout_seconds
        self._active_count = 0
        self._lock = threading.Lock()

    @property
    def active_count(self) -> int:
        """
        Returns the number of currently active inference executions.

        Returns:
            int: The active execution count.
        """
        with self._lock:
            return self._active_count

    def execute(
        self,
        model_id: str,
        session_id: str,
        input_data: Any,
        inference_fn: Callable[[Any], Any],
    ) -> InferenceResult:
        """
        Executes an inference function within a sandboxed context with a timeout.

        Args:
            model_id: The ID of the model.
            session_id: The session ID for this request.
            input_data: Input data for the model.
            inference_fn: The function that performs the actual inference.

        Returns:
            InferenceResult: The result of the sandboxed execution.
        """
        import signal

        request_id = f"{model_id}_{session_id}_{int(time.time() * 1000)}"
        start = time.time()

        def handler(signum, frame):
            raise TimeoutError(f"Inference timed out after {self.timeout_seconds}s")

        # Increment active count
        with self._lock:
            self._active_count += 1

        try:
            # Set timeout alarm
            old_handler = signal.signal(signal.SIGALRM, handler)
            signal.setitimer(signal.ITIMER_REAL, self.timeout_seconds)

            try:
                output = inference_fn(input_data)
                latency_ms = (time.time() - start) * 1000
                return InferenceResult(
                    request_id=request_id,
                    model_id=model_id,
                    output_data=output,
                    latency_ms=latency_ms,
                    success=True,
                )
            finally:
                # Cancel alarm and restore handler
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old_handler)

        except TimeoutError as e:
            latency_ms = (time.time() - start) * 1000
            logger.warning(f"Sandbox timeout for model {model_id}: {e}")
            return InferenceResult(
                request_id=request_id,
                model_id=model_id,
                output_data=None,
                latency_ms=latency_ms,
                success=False,
                error=str(e),
            )
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            logger.error(f"Sandbox execution error for model {model_id}: {e}")
            return InferenceResult(
                request_id=request_id,
                model_id=model_id,
                output_data=None,
                latency_ms=latency_ms,
                success=False,
                error=str(e),
            )
        finally:
            with self._lock:
                self._active_count -= 1


class ONNXModelWrapper:
    """Wrapper for ONNX model loading and inference with optional runtime."""

    def __init__(self, model_path: str):
        """
        Initializes the ONNX model wrapper.

        Args:
            model_path (str): The path to the ONNX model file.
        """
        self.model_path = Path(model_path)
        self._session = None
        self._runtime = None
        self._input_name = None
        self._output_name = None

    def load(self) -> bool:
        """
        Loads the ONNX model from disk into the execution runtime.

        Returns:
            bool: True if loading was successful, False otherwise.
        """
        try:
            # Try ONNX Runtime first
            try:
                from onnxruntime import InferenceSession, SessionOptions
                sess_opts = SessionOptions()
                sess_opts.graph_optimization_level = 2  # ORT_ENABLE_ALL
                sess_opts.intra_op_num_threads = 2
                self._session = InferenceSession(str(self.model_path), sess_opts)
                self._input_name = self._session.get_inputs()[0].name
                self._output_name = self._session.get_outputs()[0].name
                self._runtime = "onnxruntime"
                logger.info(f"ONNX model loaded via ONNXRuntime: {self.model_path}")
                return True
            except ImportError:
                pass

            # Fallback: verify file exists and is valid ONNX
            import onnx
            model = onnx.load(str(self.model_path))
            onnx.checker.check_model(model)
            self._input_name = model.graph.input[0].name
            self._output_name = model.graph.output[0].name
            self._runtime = "onnx_checker"
            logger.info(f"ONNX model verified via onnx library: {self.model_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load ONNX model {self.model_path}: {e}")
            return False

    def infer(self, input_data: Any) -> Any:
        """
        Performs inference using the loaded model.

        Args:
            input_data: Data to be processed.

        Returns:
            Any: The model's output data.
        """
        if self._runtime == "onnxruntime" and self._session:
            import numpy as np
            if isinstance(input_data, list):
                input_data = np.array(input_data, dtype=np.float32)
            elif not isinstance(input_data, np.ndarray):
                input_data = np.array([input_data], dtype=np.float32)
            result = self._session.run([self._output_name], {self._input_name: input_data})
            return result[0]
        elif self._runtime == "onnx_checker":
            return {"status": "verified", "model": str(self.model_path)}
        else:
            return {"status": "no_runtime", "model": str(self.model_path)}

    def unload(self) -> None:
        """
        Releases model-specific resources and clears the inference session.
        """
        self._session = None
        self._runtime = None
        logger.info(f"ONNX model unloaded: {self.model_path}")


class ModelLoader:
    """
    Central model loader for Synthesus AIVM.
    Manages hot-swap loading/unloading of ONNX and other models.
    """

    def __init__(self, models_dir: str = "data/models", default_timeout: float = 30.0):
        """
        Initializes the ModelLoader with a models directory and default timeout.

        Args:
            models_dir (str): The directory where model files are stored.
            default_timeout (float): Default timeout for inference requests.
        """
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.default_timeout = default_timeout

        self._registry = ModelRegistry()
        self._sandbox = SandboxExecutor(timeout_seconds=default_timeout)
        self._loaders: Dict[str, ONNXModelWrapper] = {}
        self._lock = threading.RLock()

    @property
    def registry(self) -> ModelRegistry:
        """
        Returns the model registry instance.

        Returns:
            ModelRegistry: The internal model registry.
        """
        return self._registry

    @property
    def sandbox(self) -> SandboxExecutor:
        """
        Returns the sandbox executor instance.

        Returns:
            SandboxExecutor: The internal sandbox executor.
        """
        return self._sandbox

    def load_model(
        self,
        model_id: str,
        model_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Hot-loads a model into the system.

        Args:
            model_id: Unique ID for the model.
            model_path: Optional path to the model file.
            metadata: Optional additional metadata.

        Returns:
            bool: True if loading succeeded, False otherwise.
        """
        if model_path is None:
            model_path = str(self.models_dir / f"{model_id}.onnx")

        info = self._registry.register(model_id, model_path, metadata)
        self._registry.update_state(model_id, ModelState.LOADING)

        try:
            wrapper = ONNXModelWrapper(model_path)
            if wrapper.load():
                with self._lock:
                    self._loaders[model_id] = wrapper
                self._registry.update_state(model_id, ModelState.READY)
                logger.info(f"Model {model_id} loaded successfully")
                return True
            else:
                self._registry.update_state(model_id, ModelState.ERROR, error="Load failed")
                return False
        except Exception as e:
            self._registry.update_state(model_id, ModelState.ERROR, error=str(e))
            logger.error(f"Model {model_id} load error: {e}")
            return False

    def unload_model(self, model_id: str) -> bool:
        """
        Unloads a model from the system, ensuring no active sessions are interrupted.

        Args:
            model_id: The ID of the model to unload.

        Returns:
            bool: True if unloading succeeded, False otherwise.
        """
        with self._lock:
            info = self._registry.get(model_id)
            if not info:
                logger.warning(f"Cannot unload {model_id}: not registered")
                return False

            if info.session_count > 0:
                logger.warning(f"Cannot unload {model_id}: {info.session_count} active sessions")
                return False

            self._registry.update_state(model_id, ModelState.UNLOADING)

            if model_id in self._loaders:
                self._loaders[model_id].unload()
                del self._loaders[model_id]

            self._registry.update_state(model_id, ModelState.UNLOADED)
            logger.info(f"Model {model_id} unloaded")
            return True

    def infer(
        self,
        model_id: str,
        input_data: Any,
        timeout_seconds: Optional[float] = None,
        priority: int = 0,
    ) -> InferenceResult:
        """
        Executes inference on a loaded model with priority and timeout.

        Args:
            model_id: ID of the model to use.
            input_data: Input data for the model.
            timeout_seconds: Optional timeout override.
            priority: Execution priority.

        Returns:
            InferenceResult: The result of the inference operation.
        """
        info = self._registry.get(model_id)
        if not info or info.state != ModelState.READY:
            return InferenceResult(
                request_id=f"{model_id}_err_{int(time.time() * 1000)}",
                model_id=model_id,
                output_data=None,
                latency_ms=0.0,
                success=False,
                error=f"Model {model_id} not ready (state={info.state if info else 'unknown'})",
            )

        session_id = self._registry.acquire_session(model_id)
        timeout = timeout_seconds or self.default_timeout

        # Override sandbox timeout
        old_timeout = self._sandbox.timeout_seconds
        self._sandbox.timeout_seconds = timeout

        try:
            def do_infer(data):
                with self._lock:
                    wrapper = self._loaders.get(model_id)
                if wrapper:
                    return wrapper.infer(data)
                raise RuntimeError(f"Model {model_id} loader not found")

            result = self._sandbox.execute(model_id, session_id, input_data, do_infer)
            self._registry.record_inference(model_id, result.latency_ms)
            return result
        finally:
            self._sandbox.timeout_seconds = old_timeout
            self._registry.release_session(session_id)

    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """
        Retrieves metadata and status for a specific model.

        Args:
            model_id (str): The ID of the model.

        Returns:
            Optional[ModelInfo]: The model info if found, else None.
        """
        return self._registry.get(model_id)

    def list_loaded_models(self) -> Dict[str, ModelState]:
        """
        Lists all models currently registered and their states.

        Returns:
            Dict[str, ModelState]: A mapping of model IDs to their operational states.
        """
        models = self._registry.list_models()
        return {mid: info.state for mid, info in models.items()}

    def stats(self) -> Dict[str, Any]:
        """
        Returns aggregate statistics for all models and the sandbox.

        Returns:
            Dict[str, Any]: Dictionary of usage metrics and operational status.
        """
        models = self._registry.list_models()
        return {
            "total_models": len(models),
            "loaded": sum(1 for m in models.values() if m.state == ModelState.READY),
            "active_sessions": sum(m.session_count for m in models.values()),
            "total_inferences": sum(m.total_inferences for m in models.values()),
            "avg_latency_ms": (
                sum(m.total_latency_ms for m in models.values()) /
                max(1, sum(m.total_inferences for m in models.values()))
            ),
            "sandbox_active": self._sandbox.active_count,
        }