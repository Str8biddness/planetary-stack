"""
KAL Configuration — V4

Loads settings from config.yaml and provides factory functions
to build the service stack with support for IVFFlat backend,
L1 cache sizing, and hemisphere latency budgets.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Default path to the project-level config
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


class KalConfig(BaseModel):
    """Configuration for the Knowledge Abstraction Layer (V4)."""

    enabled: bool = Field(default=True, description="Master switch for KAL.")
    backend_type: str = Field(
        default="faiss",
        description="Backend implementation: 'faiss' (FlatIP) or 'faiss_ivf' (IVFFlat).",
    )
    default_domains: List[str] = Field(
        default_factory=lambda: ["general"],
        description="Default namespace list when caller omits namespaces.",
    )
    default_top_k: int = Field(default=8, ge=1, le=100)
    use_for_retrieval: bool = Field(
        default=True,
        description="If True, route retrieval through KAL; if False, use legacy RAGPipeline.",
    )

    # V4 additions
    cache_size: int = Field(
        default=1024,
        ge=0,
        description="L1 LRU cache entries for exact_match mode. 0 to disable caching.",
    )
    ivf_nlist: int = Field(
        default=100,
        ge=1,
        description="Number of Voronoi cells for IVFFlat backend.",
    )
    left_hemisphere_latency_ms: float = Field(
        default=0.5,
        description="Strict latency budget for exact_match (Left Hemisphere) queries.",
    )
    right_hemisphere_latency_ms: float = Field(
        default=5.0,
        description="Latency budget for semantic_graph (Right Hemisphere) queries.",
    )


def load_kal_config(config_path: Optional[str | Path] = None) -> KalConfig:
    """Read the ``kal`` section from a YAML config file.

    Falls back to defaults if the file or section doesn't exist.
    """
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    if not path.exists():
        logger.info("KAL config file not found at %s — using defaults.", path)
        return KalConfig()

    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("pyyaml not installed — using default KAL config.")
        return KalConfig()

    with open(path) as f:
        data: Dict[str, Any] = yaml.safe_load(f) or {}

    kal_data = data.get("kal", {})
    if not kal_data:
        logger.info("No 'kal' section in %s — using defaults.", path)
        return KalConfig()

    return KalConfig(**kal_data)


def build_kal_service(config: KalConfig, rag_pipeline: Any = None):
    """Instantiate backend → service → client from config.

    Returns:
        (KalService, KalClient) tuple.
    """
    from .client import KalClient
    from .service import KalService

    if config.backend_type == "faiss":
        from .backends.faiss_backend import FaissKalBackend
        if rag_pipeline is None:
            from core.rag_pipeline import RAGPipeline
            rag_pipeline = RAGPipeline()
        backend = FaissKalBackend(rag_pipeline)

    elif config.backend_type == "faiss_ivf":
        from .backends.ivfflat_backend import IVFFlatKalBackend
        backend = IVFFlatKalBackend(
            embedding_dim=128,
            nlist=config.ivf_nlist,
        )

    else:
        raise ValueError(f"Unknown KAL backend_type: {config.backend_type!r}")

    service = KalService(backend=backend, cache_size=config.cache_size)
    client = KalClient(service=service, default_domains=config.default_domains)
    return service, client
