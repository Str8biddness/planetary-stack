"""ONNX Model Runner - Python interface for ONNX Runtime inference"""
from typing import Dict, Any, Optional, List
import logging
import threading
import time
import numpy as np

logger = logging.getLogger(__name__)


class ModelRunner:
    """Manages ONNX model loading and inference for Synthesus.
    
    Provides thread-safe session management for concurrent model execution
    with proper integration to the AIVM isolation layer.
    """

    def __init__(self, model_dir: str = "./models", device: str = "auto"):
        self.model_dir = model_dir
        self.device = device
        self._sessions: Dict[str, Any] = {}
        self._session_info: Dict[str, Dict[str, Any]] = {}
        self._available = False
        self._lock = threading.RLock()
        self._stats = {
            "total_loads": 0,
            "total_unloads": 0,
            "total_inferences": 0,
            "failed_loads": 0,
            "failed_inferences": 0,
        }
        self._try_import()

    def _try_import(self):
        try:
            import onnxruntime as ort
            self._ort = ort
            # Select provider based on device
            providers = self._select_providers()
            self._providers = providers
            self._available = True
            logger.info(f"ONNX Runtime available. Providers: {providers}")
        except ImportError:
            logger.warning("onnxruntime not installed. Model runner in stub mode.")
            self._ort = None

    def _select_providers(self) -> List[str]:
        if not self._ort:
            return []
        available = self._ort.get_available_providers()
        if self.device == "auto":
            for pref in ["CUDAExecutionProvider", "ROCMExecutionProvider",
                         "TensorrtExecutionProvider", "CPUExecutionProvider"]:
                if pref in available:
                    return [pref, "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def load_model(self, model_name: str, model_path: Optional[str] = None) -> bool:
        """Load an ONNX model by name with thread-safe session tracking."""
        if not self._available:
            logger.warning(f"Cannot load {model_name}: ONNX Runtime not available")
            return False
        path = model_path or f"{self.model_dir}/{model_name}.onnx"
        try:
            opts = self._ort.SessionOptions()
            opts.graph_optimization_level = (
                self._ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
            session = self._ort.InferenceSession(
                path, sess_options=opts, providers=self._providers
            )
            with self._lock:
                self._sessions[model_name] = session
                self._session_info[model_name] = {
                    "path": path,
                    "loaded_at": time.time(),
                    "execution_count": 0,
                }
                self._stats["total_loads"] += 1
            logger.info(f"Loaded model: {model_name} from {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load {model_name}: {e}")
            self._stats["failed_loads"] += 1
            return False

    def run(self, model_name: str, inputs: Dict[str, np.ndarray]) -> Optional[Dict[str, np.ndarray]]:
        """Run inference on a loaded model with thread-safe session tracking."""
        if model_name not in self._sessions:
            logger.error(f"Model not loaded: {model_name}")
            return None
        try:
            session = self._sessions[model_name]
            output_names = [o.name for o in session.get_outputs()]
            results = session.run(output_names, inputs)
            with self._lock:
                if model_name in self._session_info:
                    self._session_info[model_name]["execution_count"] += 1
                    self._session_info[model_name]["last_used"] = time.time()
                self._stats["total_inferences"] += 1
            return dict(zip(output_names, results))
        except Exception as e:
            logger.error(f"Inference error on {model_name}: {e}")
            self._stats["failed_inferences"] += 1
            return None

    def unload_model(self, model_name: str):
        """Unload a model and reclaim resources with thread-safe tracking."""
        with self._lock:
            if model_name in self._sessions:
                del self._sessions[model_name]
            if model_name in self._session_info:
                del self._session_info[model_name]
            self._stats["total_unloads"] += 1
        logger.info(f"Unloaded model: {model_name}")

    def list_loaded(self) -> List[str]:
        """List all loaded model names."""
        with self._lock:
            return list(self._sessions.keys())

    def get_stats(self) -> Dict[str, Any]:
        """Get model runner statistics."""
        with self._lock:
            session_stats = {
                mid: info.copy() for mid, info in self._session_info.items()
            }
            return {
                "available": self._available,
                "loaded_models": list(self._sessions.keys()),
                "session_info": session_stats,
                **self._stats,
            }

    @property
    def is_available(self) -> bool:
        return self._available