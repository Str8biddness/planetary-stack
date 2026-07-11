"""Persona-Clone Expert Swarm — one resident base model + N cheap deltas.

Load-bearing constraint: inference is GPU-bound and shared. Never run N model
copies. Experts are persona/system-prompt + optional LoRA adapter *data* +
retrieval namespace. Isolation between cooperating experts on a single-GPU
local host is forbidden (wastes the single GPU).

v1 capability boundary (honest):
  - Applied delta = system_prompt + namespace (always).
  - LoRA/adapter files are validated as DATA for base-compat; not hot-swapped.
  - Firecracker MicroVM envelopes are HOSTED-only (local → loud BLOCK).

Disjoint from packages/foreman. Builds on core.chal.quad_brain.QuadBrainOrchestrator.

Quick start::

    from swarm import Expert, ExpertRegistry, SwarmRequest, SwarmScheduler, SwarmRuntime
    from swarm.model_client import SharedOllamaClient

    reg = ExpertRegistry()
    reg.register(Expert(
        expert_id="guide", persona="Guide",
        system_prompt="You are a brief guide.",
        namespace="ns_guide",
    ))
    runtime = SwarmRuntime(SwarmScheduler(reg, model_client=SharedOllamaClient()))
    answer = runtime.answer(SwarmRequest(query="Hello", expert_ids=["guide"]))
    print(answer.response, answer.contributing_experts)
"""

from .registry import (
    Expert,
    ExpertRegistry,
    ExpertResult,
    SwarmAnswer,
    SwarmRequest,
)
from .scheduler import SwarmScheduler
from .arbiter import SwarmArbiter, SwarmRuntime
from .model_client import SharedOllamaClient
from .adapters.loader import AdapterLoader

__all__ = [
    "Expert",
    "ExpertRegistry",
    "ExpertResult",
    "SwarmAnswer",
    "SwarmRequest",
    "SwarmScheduler",
    "SwarmArbiter",
    "SwarmRuntime",
    "SharedOllamaClient",
    "AdapterLoader",
]
