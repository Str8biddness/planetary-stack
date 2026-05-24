"""
ONNX Integration Hooks for AIVM
Provides ONNX Runtime model loading, session management, and inference execution
with proper isolation and resource management for Synthesus models.
"""
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
import logging
import numpy as np

logger = logging.getLogger(__name__)

# ONNX Runtime availability check
ONNX_AVAILABLE = False
onnx = None
ORT = None

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
    ORT = ort
    logger.info("ONNX Runtime available for AIVM integration")
except ImportError:
    logger.warning("ONNX Runtime not installed — ONNX integration disabled")


class SessionPolicy(Enum):
    """Session lifecycle and reuse policies."""
    REUSE = "reuse"           # Reuse sessions within pool limits
    EXCLUSIVE = "exclusive"   # One session per model
    EPHEMERAL = "ephemeral"    # New session per inference (higher overhead)


@dataclass
class ONNXModelConfig:
    """Configuration for ONNX model loading and execution."""
    model_path: str
    session_policy: SessionPolicy = SessionPolicy.REUSE
    execution_provider: str = "CPUExecutionProvider"
    intra_op_threads: int = 1
    inter_op_threads: int = 1
    memory_limit_mb: float = 512.0
    enable_profiling: bool = False
    session_options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ONNXSession:
    """Wrapper for ONNX Runtime inference session."""
    session_id: str
    model_id: str
    session: Any  # ort.InferenceSession
    config: ONNXModelConfig
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    execution_count: int = 0
    is_active: bool = True


class ONNXModelLoader:
    """
    Manages ONNX model loading with session pooling and resource limits.
    Part of the AIVM isolation layer for model execution sandboxing.
    """

    def __init__(self, max_sessions_per_model: int = 4):
        self._sessions: Dict[str, List[ONNXSession]] = {}
        self._active_sessions: Dict[str, ONNXSession] = {}
        self._configs: Dict[str, ONNXModelConfig] = {}
        self._max_sessions = max_sessions_per_model
        self._lock = threading.RLock()
        self._stats = {
            "total_loads": 0,
            "total_unloads": 0,
            "total_inferences": 0,
            "failed_loads": 0,
            "failed_inferences": 0,
        }

    @property
    def is_available(self) -> bool:
        """Check if ONNX Runtime is available."""
        return ONNX_AVAILABLE

    def load_model(self, model_id: str, config: ONNXModelConfig) -> bool:
        """
        Load an ONNX model into a session pool.
        
        Args:
            model_id: Unique identifier for the model
            config: ONNXModelConfig with model path and execution settings
            
        Returns:
            True if loading succeeded, False otherwise
        """
        if not ONNX_AVAILABLE:
            logger.error("ONNX Runtime not available")
            return False

        with self._lock:
            # Check if already loaded
            if model_id in self._configs:
                logger.info(f"Model {model_id} already loaded")
                return True

            try:
                # Configure session options
                sess_options = ORT.SessionOptions()
                sess_options.intra_op_num_threads = config.intra_op_threads
                sess_options.inter_op_num_threads = config.inter_op_threads
                sess_options.enable_profiling = config.enable_profiling

                for key, value in config.session_options.items():
                    setattr(sess_options, key, value)

                # Create session
                session = ORT.InferenceSession(
                    config.model_path,
                    sess_options,
                    providers=[config.execution_provider]
                )

                # Create session wrapper
                session_id = f"{model_id}_{time.time_ns()}"
                onnx_session = ONNXSession(
                    session_id=session_id,
                    model_id=model_id,
                    session=session,
                    config=config,
                    created_at=time.time(),
                    last_used=time.time(),
                )

                # Store in pool
                self._sessions[model_id] = [onnx_session]
                self._active_sessions[session_id] = onnx_session
                self._configs[model_id] = config

                self._stats["total_loads"] += 1
                logger.info(f"Loaded ONNX model {model_id} (session {session_id})")
                return True

            except Exception as e:
                logger.error(f"Failed to load ONNX model {model_id}: {e}")
                self._stats["failed_loads"] += 1
                return False

    def unload_model(self, model_id: str) -> bool:
        """
        Unload a model and reclaim all sessions.
        
        Args:
            model_id: Identifier of the model to unload
            
        Returns:
            True if unload succeeded
        """
        with self._lock:
            # Remove from active sessions
            if model_id in self._sessions:
                for sess in self._sessions[model_id]:
                    if sess.session_id in self._active_sessions:
                        del self._active_sessions[sess.session_id]
                del self._sessions[model_id]

            if model_id in self._configs:
                del self._configs[model_id]

            self._stats["total_unloads"] += 1
            logger.info(f"Unloaded ONNX model {model_id}")
            return True

    def run(
        self,
        model_id: str,
        inputs: Dict[str, np.ndarray],
        output_names: Optional[List[str]] = None,
        timeout_seconds: float = 30.0
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Run inference on a loaded ONNX model.
        
        Args:
            model_id: Model identifier
            inputs: Dictionary of input names to numpy arrays
            output_names: Optional list of output names to fetch
            timeout_seconds: Execution timeout (currently enforced via caller)
            
        Returns:
            Dictionary of output name to numpy array, or None on failure
        """
        if not ONNX_AVAILABLE:
            logger.error("ONNX Runtime not available")
            return None

        session = self._acquire_session(model_id)
        if not session:
            logger.error(f"No session available for model {model_id}")
            return None

        try:
            # Convert inputs to ONNX format
            onnx_inputs = {k: v for k, v in inputs.items()}

            # Run inference
            output_list = session.session.run(output_names, onnx_inputs)

            # Build output dict
            if output_names:
                outputs = {name: output_list[i] for i, name in enumerate(output_names)}
            else:
                # Get output names from model if not specified
                output_names = [o.name for o in session.session.get_outputs()]
                outputs = {name: output_list[i] for i, name in enumerate(output_names)}

            # Update stats
            session.execution_count += 1
            session.last_used = time.time()
            self._stats["total_inferences"] += 1

            self._release_session(session)
            return outputs

        except Exception as e:
            logger.error(f"ONNX inference failed for {model_id}: {e}")
            self._stats["failed_inferences"] += 1
            self._release_session(session)
            return None

    def _acquire_session(self, model_id: str) -> Optional[ONNXSession]:
        """Acquire a session from the pool."""
        with self._lock:
            pool = self._sessions.get(model_id, [])
            for sess in pool:
                if sess.is_active:
                    sess.last_used = time.time()
                    return sess
            return None

    def _release_session(self, session: ONNXSession):
        """Release session back to pool."""
        with self._lock:
            session.is_active = True

    def get_stats(self) -> Dict[str, Any]:
        """Get model loader statistics."""
        with self._lock:
            pool_sizes = {mid: len(pool) for mid, pool in self._sessions.items()}
            return {
                "onnx_available": ONNX_AVAILABLE,
                "loaded_models": len(self._configs),
                "active_sessions": len(self._active_sessions),
                "pool_sizes": pool_sizes,
                **self._stats,
            }


class ONNXIntegrationHooks:
    """
    High-level ONNX integration hooks for AIVM orchestration.
    Provides model lifecycle management, inference scheduling, and
    error recovery integrated with the AIVM dispatcher and sandbox.
    """

    def __init__(self, max_sessions_per_model: int = 4):
        self._loader = ONNXModelLoader(max_sessions_per_model=max_sessions_per_model)
        self._model_registry: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._error_recovery_enabled = True
        self._recovery_attempts: Dict[str, int] = {}

    @property
    def is_available(self) -> bool:
        """Check if ONNX integration is available."""
        return ONNX_AVAILABLE and self._loader.is_available

    def register_model(
        self,
        model_id: str,
        model_path: str,
        execution_provider: str = "CPUExecutionProvider",
        **kwargs
    ) -> bool:
        """
        Register a model for ONNX-powered inference.
        
        Args:
            model_id: Unique model identifier
            model_path: Path to the ONNX model file
            execution_provider: ONNX Runtime execution provider
            **kwargs: Additional ONNXModelConfig parameters
            
        Returns:
            True if registration succeeded
        """
        if not ONNX_AVAILABLE:
            logger.error("ONNX Runtime not available")
            return False

        config = ONNXModelConfig(
            model_path=model_path,
            execution_provider=execution_provider,
            **kwargs
        )

        with self._lock:
            success = self._loader.load_model(model_id, config)
            if success:
                self._model_registry[model_id] = {
                    "model_path": model_path,
                    "config": config,
                    "registered_at": time.time(),
                    "execution_provider": execution_provider,
                }
            return success

    def unregister_model(self, model_id: str) -> bool:
        """Unregister a model and reclaim resources."""
        with self._lock:
            if model_id in self._model_registry:
                del self._model_registry[model_id]
            return self._loader.unload_model(model_id)

    def run_inference(
        self,
        model_id: str,
        input_data: Dict[str, np.ndarray],
        output_names: Optional[List[str]] = None,
        timeout_seconds: float = 30.0
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Run inference via ONNX Runtime with error recovery.
        
        Args:
            model_id: Model identifier
            input_data: Input tensors as numpy arrays
            output_names: Optional output names
            timeout_seconds: Execution timeout
            
        Returns:
            Output tensors or None on failure
        """
        if model_id not in self._model_registry:
            logger.error(f"Model {model_id} not registered")
            return None

        try:
            result = self._loader.run(model_id, input_data, output_names, timeout_seconds)
            # Clear error counts on success
            if model_id in self._recovery_attempts:
                del self._recovery_attempts[model_id]
            return result

        except Exception as e:
            logger.error(f"Inference error for {model_id}: {e}")

            if self._error_recovery_enabled:
                self._recovery_attempts[model_id] = self._recovery_attempts.get(model_id, 0) + 1
                attempts = self._recovery_attempts[model_id]

                if attempts >= 3:
                    logger.warning(f"Auto-unloading {model_id} after {attempts} failures")
                    self.unregister_model(model_id)
                elif attempts >= 2:
                    logger.info(f"Attempting reload of {model_id}")
                    model_info = self._model_registry.get(model_id)
                    if model_info:
                        self._loader.unload_model(model_id)
                        self._loader.load_model(model_id, model_info["config"])

            return None

    def hotswap_model(self, old_model_id: str, new_model_id: str) -> bool:
        """
        Hot-swap one model for another.
        
        Args:
            old_model_id: Model to unload
            new_model_id: Model to load
            
        Returns:
            True if swap succeeded
        """
        if not ONNX_AVAILABLE:
            return False

        # Check if new model is registered
        new_info = self._model_registry.get(new_model_id)
        if not new_info:
            logger.error(f"New model {new_model_id} not registered for hotswap")
            return False

        # Unload old
        self._loader.unload_model(old_model_id)

        # Load new
        return self._loader.load_model(new_model_id, new_info["config"])

    def get_model_status(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get status for a specific model."""
        with self._lock:
            if model_id not in self._model_registry:
                return None

            stats = self._loader.get_stats()
            pool_sizes = stats.get("pool_sizes", {})

            return {
                "model_id": model_id,
                "registered": True,
                "pool_size": pool_sizes.get(model_id, 0),
                "execution_provider": self._model_registry[model_id]["execution_provider"],
            }

    def list_models(self) -> List[Dict[str, Any]]:
        """List all registered models."""
        with self._lock:
            return [
                {"model_id": mid, **info}
                for mid, info in self._model_registry.items()
            ]

    def get_stats(self) -> Dict[str, Any]:
        """Get integration hook statistics."""
        return self._loader.get_stats()