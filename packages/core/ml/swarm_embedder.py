"""Compatibility export for the Knowledge Cloud SwarmEmbedder."""

from __future__ import annotations

import importlib.util
from pathlib import Path

try:
    from knowledge.swarm_embedder import SwarmEmbedder
except ModuleNotFoundError:
    embedder_path = Path(__file__).resolve().parents[2] / "knowledge" / "swarm_embedder.py"
    spec = importlib.util.spec_from_file_location("_synthesus_knowledge_swarm_embedder", embedder_path)
    if spec is None or spec.loader is None:
        raise
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    SwarmEmbedder = module.SwarmEmbedder


__all__ = ["SwarmEmbedder"]
