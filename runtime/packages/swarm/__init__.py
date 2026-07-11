"""Persona-Clone Expert Swarm — one resident base model + N cheap deltas.

Load-bearing constraint: inference is GPU-bound and shared. Never run N model
copies. Experts are persona/system-prompt + optional LoRA adapter *data* +
retrieval namespace. Isolation between cooperating experts on a single-GPU
local host is forbidden (wastes the single GPU).

Disjoint from packages/foreman. Builds on core.chal.quad_brain.QuadBrainOrchestrator.
"""

from .registry import (
    Expert,
    ExpertRegistry,
    ExpertResult,
    SwarmAnswer,
    SwarmRequest,
)
from .scheduler import SwarmScheduler
from .arbiter import SwarmArbiter

__all__ = [
    "Expert",
    "ExpertRegistry",
    "ExpertResult",
    "SwarmAnswer",
    "SwarmRequest",
    "SwarmScheduler",
    "SwarmArbiter",
]
