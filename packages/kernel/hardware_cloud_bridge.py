"""
Hardware-to-Cloud Bridge for EmulEngineering.

This module provides the Python-side callable that pybind11 installs into
EmulEngine::query_blueprints. It keeps the FAISS index and SwarmEmbedder hot in
process so C++ can cross the boundary with one direct function call.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import faiss
import numpy as np

from knowledge.universal_substrate import UniversalSubstrate
from ml.swarm_embedder import SwarmEmbedder

logger = logging.getLogger(__name__)


class HardwareCloudBridge:
    """
    Hot in-process FAISS lookup service for hardware blueprints.

    The callable contract is intentionally small:
        lookup(hardware_id: str, top_k: int) -> str

    The returned string is JSON so the C++ side does not need to link a JSON
    library or know the metadata schema produced by kn_populator.py.
    """

    def __init__(
        self,
        index_path: str | Path = "data/knowledge_cache/faiss.index",
        metadata_path: str | Path = "data/knowledge_cache/faiss_metadata.json",
        model_dir: str | Path = "data/knowledge_cache/models",
        parameter_endpoint: str = "http://localhost:8000/parameter-cloud/v2",
        local_data_dir: str | Path = "data",
        embedding_dim: int = 128,
        score_threshold: float = 0.25,
        overfetch: int = 4,
    ) -> None:
        self.index_path = Path(index_path)
        self.metadata_path = Path(metadata_path)
        self.model_dir = Path(model_dir) if model_dir else None
        self.local_data_dir = Path(local_data_dir)
        self.embedding_dim = embedding_dim
        self.score_threshold = score_threshold
        self.overfetch = max(1, overfetch)

        self._lock = threading.RLock()
        self._index: Optional[faiss.Index] = None
        self._metadata: List[Dict[str, Any]] = []
        self._embedder = SwarmEmbedder(model_dir=self.model_dir, dim=embedding_dim)
        self._parameter_substrate = UniversalSubstrate(
            endpoint=parameter_endpoint,
            local_data_dir=str(self.local_data_dir),
            knowledge_cloud_dir=str(self.local_data_dir / "knowledge_cloud"),
        )
        self._dimension_error: Optional[str] = None

        self.reload()

    def reload(self) -> None:
        """Reload FAISS, metadata, and ensure the embedder is query-ready."""
        with self._lock:
            if not self.index_path.exists():
                raise FileNotFoundError(f"FAISS index not found: {self.index_path}")
            if not self.metadata_path.exists():
                raise FileNotFoundError(f"FAISS metadata not found: {self.metadata_path}")

            self._index = faiss.read_index(str(self.index_path))
            with self.metadata_path.open("r", encoding="utf-8") as f:
                self._metadata = json.load(f)

            if not self._embedder.is_fitted and self._metadata:
                self._embedder.dim = self._index.d
                corpus = [str(item.get("pattern", "")) for item in self._metadata]
                self._embedder.fit(corpus)

            if self._embedder.dim != self._index.d:
                self._dimension_error = (
                    f"embedding dimension mismatch: FAISS index d={self._index.d}, "
                    f"SwarmEmbedder dim={self._embedder.dim}. Rebuild the FAISS index "
                    "and SwarmEmbedder artifacts from the same kn_populator.py run."
                )
                logger.warning(self._dimension_error)
            else:
                self._dimension_error = None

            logger.info(
                "HardwareCloudBridge ready: %s vectors, %s metadata rows",
                self._index.ntotal,
                len(self._metadata),
            )

    def lookup(self, hardware_id: str, top_k: int = 5) -> str:
        """Return top blueprint matches as a compact JSON string."""
        started = time.perf_counter()
        query = hardware_id.strip()
        if not query:
            return self._json(
                {
                    "available": False,
                    "hardware_id": hardware_id,
                    "results": [],
                    "error": "empty hardware_id",
                }
            )

        with self._lock:
            if self._index is None or self._index.ntotal == 0:
                return self._json(
                    {
                        "available": False,
                        "hardware_id": hardware_id,
                        "results": [],
                        "error": "FAISS index is empty",
                    }
                )
            if self._dimension_error:
                return self._json(
                    {
                        "available": False,
                        "hardware_id": hardware_id,
                        "results": [],
                        "error": self._dimension_error,
                    }
                )

            vector = self._embedder.embed_texts([query]).astype(np.float32)
            k = max(1, min(int(top_k), self._index.ntotal))
            search_k = max(k, min(self._index.ntotal, k * self.overfetch))
            scores, indices = self._index.search(vector, search_k)

            results: List[Dict[str, Any]] = []
            for score, idx in zip(scores[0], indices[0]):
                idx = int(idx)
                score = float(score)
                if idx < 0 or idx >= len(self._metadata):
                    continue
                if score < self.score_threshold:
                    continue

                meta = dict(self._metadata[idx])
                results.append(
                    {
                        "index": idx,
                        "score": round(score, 6),
                        "pattern": meta.get("pattern", ""),
                        "response": meta.get("response", ""),
                        "source": meta.get("source", ""),
                        "domain": meta.get("domain", ""),
                        "character_id": meta.get("character_id", "global"),
                        "metadata": meta,
                    }
                )
                if len(results) >= k:
                    break

        latency_ms = (time.perf_counter() - started) * 1000.0
        return self._json(
            {
                "available": bool(results),
                "hardware_id": hardware_id,
                "top_k": k,
                "latency_ms": round(latency_ms, 4),
                "results": results,
            }
        )

    def attach(self, engine: Any, top_k: int = 5) -> Any:
        """Attach this bridge to a pybind11 EmulEngine instance."""
        engine.set_blueprint_top_k(top_k)
        engine.set_blueprint_lookup(self.lookup)
        if hasattr(engine, "set_parameter_lookup"):
            engine.set_parameter_lookup(self.lookup_parameter)
        return engine

    def lookup_parameter(self, parameter_id: str) -> bytes:
        """
        Fetch a Knowledge Cloud / Parameter Cloud value as bytes for VPD.

        Accepted keys:
            "domain:namespace"       -> explicit domain
            "domain.namespace.path"  -> explicit known domain prefix
            "namespace.path"         -> right_hemisphere fallback
        """
        domain, namespace = self._split_parameter_id(parameter_id)
        entry = self._parameter_substrate.get_parameter(namespace, domain=domain)
        if not entry:
            raise KeyError(f"parameter not found: {parameter_id}")
        return self._entry_to_bytes(entry)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "index_path": str(self.index_path),
                "metadata_path": str(self.metadata_path),
                "model_dir": str(self.model_dir) if self.model_dir else None,
                "vectors": self._index.ntotal if self._index else 0,
                "metadata_entries": len(self._metadata),
                "embedder_fitted": self._embedder.is_fitted,
                "faiss_dim": self._index.d if self._index else None,
                "embedder_dim": self._embedder.dim,
                "dimension_error": self._dimension_error,
                "score_threshold": self.score_threshold,
            }

    @staticmethod
    def _json(payload: Dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

    @staticmethod
    def _split_parameter_id(parameter_id: str) -> tuple[str, str]:
        if ":" in parameter_id:
            domain, namespace = parameter_id.split(":", 1)
            return domain or "right_hemisphere", namespace

        known_domains = {
            "left_hemisphere",
            "right_hemisphere",
            "knowledge_cloud",
            "parameter_cloud",
        }
        head, _, tail = parameter_id.partition(".")
        if tail and head in known_domains:
            return head, tail
        return "right_hemisphere", parameter_id

    @staticmethod
    def _entry_to_bytes(entry: Dict[str, Any]) -> bytes:
        value = entry.get("value", entry)
        if isinstance(value, bytes):
            return value
        if isinstance(value, bytearray):
            return bytes(value)
        if isinstance(value, str):
            return value.encode("utf-8")
        return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def create_bridged_emul_engine(
    *,
    top_k: int = 5,
    index_path: str | Path = "data/knowledge_cache/faiss.index",
    metadata_path: str | Path = "data/knowledge_cache/faiss_metadata.json",
    model_dir: str | Path = "data/knowledge_cache/models",
) -> Any:
    """
    Convenience factory for Python callers.

    The pybind module may be named either _synthesus_kernel by CMake or
    synthesus_kernel by a direct compiler invocation.
    """
    try:
        import _synthesus_kernel as native_kernel  # type: ignore
    except ImportError:
        import synthesus_kernel as native_kernel  # type: ignore

    bridge = HardwareCloudBridge(
        index_path=index_path,
        metadata_path=metadata_path,
        model_dir=model_dir,
    )
    engine = native_kernel.EmulEngine()
    engine._hardware_cloud_bridge = bridge
    return bridge.attach(engine, top_k=top_k)
