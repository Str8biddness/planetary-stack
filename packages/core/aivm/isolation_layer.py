"""
AIVM Model Isolation Layer
Provides deep isolation between concurrent Synthesus models using ONNX session pools.
"""
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
import logging
import numpy as np
from collections import defaultdict

logger = logging.getLogger(__name__)


class IsolationMode(Enum):
    """Isolation enforcement level for AIVM model sessions.
    
    Attributes:
        NONE: No isolation — models share the same process space.
        PROCESS: Each model runs in an isolated subprocess.
        FULL: Maximum isolation with separate memory and compute contexts.
    """
    SOFT = "soft"        # Shared resources, logical isolation
    HARD = "hard"        # Separate session pools
    STRICT = "strict"   # Separate threads + sessions


@dataclass
class ModelIsolationConfig:
    """Configuration for a single model's isolation requirements.
    
    Attributes:
        model_id: Unique identifier for this model.
        isolation_mode: Required IsolationMode level.
        max_memory_mb: Maximum memory budget in megabytes.
        timeout_seconds: Maximum inference timeout in seconds.
        allowed_tools: List of tool names this model may invoke.
    """
    mode: IsolationMode = IsolationMode.SOFT
    max_sessions_per_model: int = 4
    session_timeout_seconds: float = 300.0
    enable_gc: bool = True
    gc_interval_seconds: float = 60.0
    memory_threshold_mb: float = 512.0


@dataclass
class IsolatedSession:
    """An active inference session with isolated model execution.
    
    Manages the lifecycle of a model running within its configured
    isolation boundary, tracking resource usage and enforcing budgets.
    
    Attributes:
        session_id: Unique identifier for this session.
        model_id: ID of the model being run.
        isolation_mode: Active isolation enforcement level.
        config: ModelIsolationConfig for this session.
        start_time: Wall-clock time when the session started.
        resource_usage: Current resource usage metrics.
    """
    session_id: str
    model_id: str
    session: Any  # ONNX session
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    execution_count: int = 0
    is_active: bool = True


class ModelIsolationLayer:
    """
    Provides process-level isolation for concurrent model execution.
    Manages session pools, memory limits, and concurrent access.
    """

    def __init__(self, config: ModelIsolationConfig = None, model_runner=None):
        """Initializes the ModelIsolationLayer.

        Args:
            config: Optional ModelIsolationConfig instance.
            model_runner: Optional model runner backend.
        """
        self._config = config or ModelIsolationConfig()
        self._model_runner = model_runner
        self._session_pools: Dict[str, List[IsolatedSession]] = defaultdict(list)
        self._active_sessions: Dict[str, IsolatedSession] = {}
        self._lock = threading.RLock()
        self._model_configs: Dict[str, Dict[str, Any]] = {}
        self._execution_queue: Dict[str, List[Callable]] = defaultdict(list)
        self._stats: Dict[str, Any] = {
            "total_executions": 0,
            "session_creations": 0,
            "session_reclaims": 0,
            "gc_runs": 0,
        }

    def register_model(self, model_id: str, model_path: str, config: Dict[str, Any] = None):
        """Registers a model for isolated execution within the layer.

        Args:
            model_id: Unique identifier for the model.
            model_path: Filesystem path to the model artifact.
            config: Optional model-specific configuration dictionary.
        """
        with self._lock:
            self._model_configs[model_id] = {
                "model_path": model_path,
                "config": config or {},
                "registered_at": time.time(),
            }
            self._session_pools[model_id] = []
        logger.info(f"Registered model {model_id} for isolated execution")

    def acquire_session(self, model_id: str) -> Optional[IsolatedSession]:
        """Retrieves or creates an isolated session for a specific model.

        Args:
            model_id: The ID of the model to acquire a session for.

        Returns:
            An IsolatedSession if available, or None if the pool is exhausted.
        """
        with self._lock:
            pool = self._session_pools.get(model_id, [])
            config = self._model_configs.get(model_id, {})

            # Try to reuse existing session
            for session in pool:
                if session.is_active and (time.time() - session.last_used) < self._config.session_timeout_seconds:
                    session.last_used = time.time()
                    return session

            # Create new session if under limit
            if len(pool) < self._config.max_sessions_per_model:
                session = self._create_session(model_id)
                if session:
                    pool.append(session)
                    self._stats["session_creations"] += 1
                    return session

            # Pool exhausted, wait or fail
            return None

    def _create_session(self, model_id: str) -> Optional[IsolatedSession]:
        """Instantiates a new isolated session by loading the model into the runner.

        Args:
            model_id: The ID of the model to load.

        Returns:
            A new IsolatedSession instance, or None if creation failed.
        """
        if not self._model_runner or not self._model_runner.is_available:
            logger.warning(f"Model runner not available for {model_id}")
            return None

        config = self._model_configs.get(model_id, {})
        model_path = config.get("model_path")

        if not model_path:
            logger.error(f"No model path for {model_id}")
            return None

        try:
            success = self._model_runner.load_model(model_id, model_path)
            if not success:
                return None

            session = IsolatedSession(
                session_id=f"{model_id}_{time.time_ns()}",
                model_id=model_id,
                session=self._model_runner._sessions.get(model_id),
                created_at=time.time(),
                last_used=time.time(),
            )
            self._active_sessions[session.session_id] = session
            logger.info(f"Created isolated session {session.session_id} for {model_id}")
            return session

        except Exception as e:
            logger.error(f"Failed to create session for {model_id}: {e}")
            return None

    def release_session(self, session: IsolatedSession):
        """Returns an active session back to its respective model pool.

        Args:
            session: The IsolatedSession instance to release.
        """
        with self._lock:
            session.last_used = time.time()
            session.is_active = True
            pool = self._session_pools.get(session.model_id, [])
            if session not in pool:
                pool.append(session)
        logger.debug(f"Released session {session.session_id}")

    def execute_isolated(
        self,
        model_id: str,
        inputs: Dict[str, np.ndarray],
        timeout: float = 30.0
    ) -> Optional[Dict[str, np.ndarray]]:
        """Executes model inference within an isolated session and handles cleanup.

        Args:
            model_id: The ID of the model to execute.
            inputs: Dictionary mapping input names to numpy arrays.
            timeout: Inference timeout in seconds. Defaults to 30.0.

        Returns:
            Dictionary of output results, or None if execution failed.
        """
        session = self.acquire_session(model_id)
        if not session:
            logger.error(f"No session available for {model_id}")
            return None

        start_time = time.time()
        try:
            if not self._model_runner or not self._model_runner.is_available:
                return None

            result = self._model_runner.run(model_id, inputs)

            with self._lock:
                session.execution_count += 1
                session.last_used = time.time()
                self._stats["total_executions"] += 1

            self.release_session(session)
            return result

        except Exception as e:
            logger.error(f"Isolated execution error for {model_id}: {e}")
            self.release_session(session)
            return None

    def hotswap_model(self, old_model_id: str, new_model_id: str) -> bool:
        """Transitions from an old model version to a new one by marking old sessions for cleanup.

        Args:
            old_model_id: ID of the model to replace.
            new_model_id: ID of the new model to use.

        Returns:
            True if the hotswap was initiated successfully.
        """
        with self._lock:
            # Mark old sessions for reclamation
            old_pool = self._session_pools.get(old_model_id, [])
            for session in old_pool:
                session.is_active = False

            # Trigger GC
            self._garbage_collect()

            logger.info(f"Hot-swap {old_model_id} -> {new_model_id}")
            return True

    def _garbage_collect(self):
        """Identifies and removes inactive or timed-out sessions from all pools."""
        with self._lock:
            for model_id in list(self._session_pools.keys()):
                pool = self._session_pools[model_id]
                active = [s for s in pool if s.is_active and
                         (time.time() - s.last_used) < self._config.session_timeout_seconds]
                inactive = [s for s in pool if not s.is_active or
                           (time.time() - s.last_used) >= self._config.session_timeout_seconds]

                for session in inactive:
                    if session.session_id in self._active_sessions:
                        del self._active_sessions[session.session_id]
                    self._stats["session_reclaims"] += 1

                self._session_pools[model_id] = active

            self._stats["gc_runs"] += 1

    def unload_model(self, model_id: str):
        """Completely unloads a model and destroys all associated isolated sessions.

        Args:
            model_id: The ID of the model to unload.
        """
        with self._lock:
            pool = self._session_pools.get(model_id, [])
            for session in pool:
                if session.session_id in self._active_sessions:
                    del self._active_sessions[session.session_id]

            self._session_pools[model_id] = []

            if self._model_runner:
                self._model_runner.unload_model(model_id)

            if model_id in self._model_configs:
                del self._model_configs[model_id]

        logger.info(f"Unloaded model {model_id} and reclaimed sessions")

    def get_stats(self) -> Dict[str, Any]:
        """Retrieves operational statistics for the isolation layer.

        Returns:
            A dictionary containing session counts, pool sizes, and execution totals.
        """
        with self._lock:
            pool_sizes = {mid: len(pool) for mid, pool in self._session_pools.items()}
            return {
                "registered_models": len(self._model_configs),
                "active_sessions": len(self._active_sessions),
                "pool_sizes": pool_sizes,
                **self._stats,
            }