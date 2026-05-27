"""Bounded response planning interface for the generation pipeline.

The planner converts grounded reasoning state into a ``ResponsePlan``. It is
intentionally small: orchestration remains in Python, while model-backed
realization and critic loops can evolve behind this stable contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .response_plan import ResponsePlan


@dataclass(frozen=True)
class PlanningContext:
    """Inputs required to plan a bounded response."""

    query: str
    intent: str = "inform"
    domain: str = "general"
    style: str = "direct"
    safety_level: float = 0.3
    target_length: int = 128
    key_points: list[str] = field(default_factory=list)
    required_phrases: list[str] = field(default_factory=list)
    forbidden_phrases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ResponsePlanner:
    """Create bounded generation plans from reasoning context."""

    def plan(self, context: PlanningContext) -> ResponsePlan:
        """Build a ResponsePlan from explicit context.

        TODO: Add policy-aware intent refinement once VRD plan objects are
        stable across runtime and NPC call paths.
        """
        return ResponsePlan(
            intent=context.intent,
            style=context.style,
            safety_level=context.safety_level,
            target_length=context.target_length,
            key_points=list(context.key_points),
            required_phrases=list(context.required_phrases),
            forbidden_phrases=list(context.forbidden_phrases),
            domain=context.domain,
            decoder_mode="stochastic",
        )

