"""
AIVM Hot-Swap Model Loader
Handles dynamic loading, unloading, and hot-swapping of ONNX models
with proper session cleanup and resource reclamation.
"""
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
import logging
import os
import importlib

logger = logging.getLogger(__name__)


class LoadState(Enum):
    """
    Enum representing the possible load states of an ONNX model.
    """
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    UNLOADING = "unloading"
    ERROR = "error"


@dataclass
class ModelMetadata:
    """
    Metadata associated with a model managed by the HotSwapModelLoader.

    Attributes:
        model_id: Unique identifier for the model.
        model_path: File path to the ONNX model.
        file_hash: SHA-256 hash of the model file.
        file_size_mb: Size of the model file in megabytes.
        loaded_at: Timestamp when the model was loaded.
        last_used: Timestamp when the model was last used for inference.
        load_attempts: Number of times loading this model has been attempted.
        load_errors: List of error messages encountered during loading.
        state: Current load state of the model.
    """
    model_id: str
    model_path: str
    file_hash: str = ""
    file_size_mb: float = 0.0
    loaded_at: Optional[float] = None
    last_used: Optional[float] = None
    load_attempts: int = 0
    load_errors: List[str] = field(default_factory=list)
    state: LoadState = LoadState.UNLOADED


class HotSwapModelLoader:
    """
    Manages the lifecycle of ONNX models with hot-swap support.
    Loads models from disk, manages session pools, and provides
    atomic swap operations with proper cleanup.
    """

    def __init__(
        self,
        models_dir: str = "./models",
        max_sessions_per_model: int = 4,
        session_timeout_seconds: float = 300.0,
        enable_gc: bool = True,
        gc_interval_seconds: float = 60.0,
    ):
        self._models_dir = models_dir
        self._max_sessions = max_sessions_per_model
        self._session_timeout = session_timeout_seconds
        self._enable_gc = enable_gc
        self._gc_interval = gc_interval_seconds

        self._metadata: Dict[str, ModelMetadata] = {}
        self._sessions: Dict[str, List[Any]] = {}
        self._active_session: Dict[str, Any] = {}
        self._handlers: Dict[str, Callable] = {}
        self._lock = threading.RLock()
        self._gc_thread: Optional[threading.Thread] = None
        self._running = False
        self._onnx_available = self._check_onnx()
        self._stats = {
            "total_loads": 0,
            "total_unloads": 0,
            "total_swaps": 0,
            "failed_loads": 0,
            "failed_swaps": 0,
        }

    def _check_onnx(self) -> bool:
        try:
            import onnxruntime
            return True
        except ImportError:
            logger.warning("onnxruntime not installed — ONNX loading disabled")
            return False

    def _compute_hash(self, path: str) -> str:
        import hashlib
        try:
            with open(path, "rb") as f:
                return hashlib.sha256(f.read(1024 * 1024)).hexdigest()[:16]
        except Exception:
            return ""

    def _get_model_path(self, model_id: str, explicit_path: Optional[str] = None) -> Optional[str]:
        if explicit_path:
            return explicit_path if os.path.exists(explicit_path) else None
        candidates = [
            os.path.join(self._models_dir, f"{model_id}.onnx"),
            os.path.join(self._models_dir, model_id, "model.onnx"),
            explicit_path,
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
        return None

    def register_handler(self, model_id: str, handler: Callable):
        """
        Registers an inference handler for a specific model ID.

        Args:
            model_id: The ID of the model to associate with the handler.
            handler: A callable that handles inference for this model.
        """
        with self._lock:
            self._handlers[model_id] = handler
        logger.info(f"Registered inference handler for model {model_id}")

    def load(
        self,
        model_id: str,
        model_path: Optional[str] = None,
        timeout_seconds: float = 60.0,
        reload: bool = False,
    ) -> Tuple[bool, str]:
        """
        Loads a model into the session pool, potentially with a timeout.

        Args:
            model_id: Unique identifier for the model.
            model_path: Optional explicit path to the model file.
            timeout_seconds: Maximum time allowed for the load operation.
            reload: If True, forces a reload even if already loaded.

        Returns:
            Tuple[bool, str]: (Success status, message or error details).
        """
        if not self._onnx_available:
            return False, "ONNX Runtime not available"

        path = self._get_model_path(model_id, model_path)
        if not path:
            return False, f"Model file not found for {model_id}"

        with self._lock:
            if model_id in self._metadata and not reload:
                meta = self._metadata[model_id]
                if meta.state == LoadState.LOADED:
                    return True, "Already loaded"

            meta = self._metadata.get(model_id, ModelMetadata(model_id=model_id, model_path=path))
            meta.state = LoadState.LOADING
            meta.load_attempts += 1
            self._metadata[model_id] = meta

        try:
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError(f"Model load timed out after {timeout_seconds}s")

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(timeout_seconds))

            try:
                import onnxruntime as ort

                sess_options = ort.SessionOptions()
                sess_options.graph_optimization_level = (
                    ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                )

                available = ort.get_available_providers()
                providers = ["CPUExecutionProvider"]
                for pref in ["CUDAExecutionProvider", "CoreMLExecutionProvider"]:
                    if pref in available:
                        providers.insert(0, pref)
                        break

                session = ort.InferenceSession(path, sess_options=sess_options, providers=providers)
            finally:
                signal.alarm(0)

            with self._lock:
                meta.state = LoadState.LOADED
                meta.file_hash = self._compute_hash(path)
                meta.file_size_mb = os.path.getsize(path) / (1024 * 1024)
                meta.loaded_at = time.time()
                meta.last_used = time.time()
                meta.load_errors = []

                self._sessions[model_id] = [session]
                self._active_session[model_id] = session

                if model_id not in self._sessions:
                    self._sessions[model_id] = []
                self._sessions[model_id].append(session)

                self._stats["total_loads"] += 1

            logger.info(
                f"Loaded model {model_id} from {path} "
                f"({meta.file_size_mb:.1f}MB, hash={meta.file_hash})"
            )
            return True, f"Loaded {meta.file_hash}"

        except TimeoutError as e:
            with self._lock:
                meta.state = LoadState.ERROR
                meta.load_errors.append(str(e))
                self._stats["failed_loads"] += 1
            logger.error(f"Load timeout for {model_id}: {e}")
            return False, str(e)

        except Exception as e:
            with self._lock:
                meta.state = LoadState.ERROR
                meta.load_errors.append(str(e))
                self._stats["failed_loads"] += 1
            logger.error(f"Failed to load {model_id}: {e}")
            return False, str(e)

    def unload(self, model_id: str, timeout_seconds: float = 10.0) -> Tuple[bool, str]:
        """
        Unloads a model and releases all associated session resources.

        Args:
            model_id: The ID of the model to unload.
            timeout_seconds: Maximum time allowed for the unload operation.

        Returns:
            Tuple[bool, str]: (Success status, message or error details).
        """
        with self._lock:
            if model_id not in self._metadata:
                return False, "Model not registered"

            meta = self._metadata[model_id]
            meta.state = LoadState.UNLOADING

        try:
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError(f"Model unload timed out after {timeout_seconds}s")

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(timeout_seconds))

            try:
                with self._lock:
                    if model_id in self._sessions:
                        for session in self._sessions[model_id]:
                            del session
                        self._sessions[model_id] = []

                    if model_id in self._active_session:
                        del self._active_session[model_id]

                    if model_id in self._handlers:
                        del self._handlers[model_id]

                    meta.state = LoadState.UNLOADED
                    meta.loaded_at = None
                    self._stats["total_unloads"] += 1

                logger.info(f"Unloaded model {model_id}")
                return True, "Unloaded"

            finally:
                signal.alarm(0)

        except TimeoutError as e:
            with self._lock:
                self._stats["failed_loads"] += 1
            logger.error(f"Unload timeout for {model_id}: {e}")
            return False, str(e)

        except Exception as e:
            logger.error(f"Error unloading {model_id}: {e}")
            return False, str(e)

    def hotswap(
        self,
        old_model_id: str,
        new_model_id: str,
        new_model_path: Optional[str] = None,
        timeout_seconds: float = 60.0,
    ) -> Tuple[bool, str]:
        """
        Atomically swaps an old model for a new one.

        The old model is fully unloaded before the new model is loaded to ensure
        clean resource handover.

        Args:
            old_model_id: ID of the model to be replaced.
            new_model_id: ID of the model to load.
            new_model_path: Optional path for the new model.
            timeout_seconds: Timeout for both unload and load operations.

        Returns:
            Tuple[bool, str]: (Success status, message or error details).
        """
        if old_model_id not in self._metadata:
            return False, f"Old model {old_model_id} not loaded"

        new_path = self._get_model_path(new_model_id, new_model_path)
        if not new_path:
            return False, f"New model file not found for {new_model_id}"

        old_meta = self._metadata[old_model_id]
        old_meta.state = LoadState.UNLOADING

        success, msg = self.unload(old_model_id, timeout_seconds=timeout_seconds)
        if not success:
            old_meta.state = LoadState.ERROR
            self._stats["failed_swaps"] += 1
            return False, f"Unload failed: {msg}"

        success, msg = self.load(new_model_id, new_model_path, timeout_seconds=timeout_seconds)
        if not success:
            self._stats["failed_swaps"] += 1
            return False, f"Load failed: {msg}"

        with self._lock:
            self._stats["total_swaps"] += 1

        logger.info(f"Hot-swap {old_model_id} -> {new_model_id} completed")
        return True, f"Swapped to {new_model_id}"

    def get_session(self, model_id: str) -> Optional[Any]:
        """
        Retrieves the active inference session for a given model.

        Args:
            model_id: The ID of the model.

        Returns:
            Optional[Any]: The active session object or None if not loaded.
        """
        with self._lock:
            return self._active_session.get(model_id)

    def get_metadata(self, model_id: str) -> Optional[ModelMetadata]:
        """
        Retrieves metadata for a specific model.

        Args:
            model_id: The ID of the model.

        Returns:
            Optional[ModelMetadata]: Metadata object or None if not found.
        """
        return self._metadata.get(model_id)

    def list_loaded(self) -> List[str]:
        """
        Lists the IDs of all currently loaded models.

        Returns:
            List[str]: A list of model identifiers in the LOADED state.
        """
        with self._lock:
            return [
                mid for mid, meta in self._metadata.items()
                if meta.state == LoadState.LOADED
            ]

    def get_stats(self) -> Dict[str, Any]:
        """
        Returns operational statistics for the hot-swap loader.

        Returns:
            Dict[str, Any]: Dictionary containing cumulative counts and status.
        """
        with self._lock:
            return {
                **self._stats,
                "onnx_available": self._onnx_available,
                "loaded_models": self.list_loaded(),
                "total_registered": len(self._metadata),
            }
