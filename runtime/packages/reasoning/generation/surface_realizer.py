"""Surface realization interface for bounded generation.

The realizer is responsible for turning a ``ResponsePlan`` into candidate text
without leaking canned templates into normal dialogue. Safety refusals and
system-policy responses are the only acceptable fixed-form outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .response_plan import GenerationTrace, ResponsePlan


@dataclass(frozen=True)
class RealizationRequest:
    """Request payload for the realization pass."""

    plan: ResponsePlan
    context: str = ""
    seed_text: str = ""
    max_attempts: int = 1


@dataclass(frozen=True)
class RealizationResult:
    """Candidate text and trace emitted by the realization pass."""

    text: str
    trace: GenerationTrace
    diagnostics: dict[str, str] = field(default_factory=dict)


class SurfaceRealizer:
    """Generate candidate text from a bounded response plan."""

    def realize(self, request: RealizationRequest) -> RealizationResult:
        """Realize candidate text from a plan.

        TODO: Wire this to the probabilistic decoder / VGD path and remove the
        seed-text bootstrap once model-backed realization is mandatory.
        """
        text = request.seed_text.strip()
        trace = GenerationTrace(
            text=text,
            constraints_satisfied=self._constraints_satisfied(text, request.plan),
            forbidden_triggered=self._forbidden_triggered(text, request.plan),
            decode_attempts=max(1, request.max_attempts),
        )
        return RealizationResult(text=text, trace=trace)

    def _constraints_satisfied(self, text: str, plan: ResponsePlan) -> bool:
        """Check required response anchors.

        TODO: Replace literal matching with normalized semantic entailment.
        """
        lowered = text.lower()
        required = [*plan.key_points, *plan.required_phrases]
        return all(item.lower() in lowered for item in required if item)

    def _forbidden_triggered(self, text: str, plan: ResponsePlan) -> bool:
        """Check forbidden phrases.

        TODO: Add policy-class matching for safety and identity violations.
        """
        lowered = text.lower()
        return any(item.lower() in lowered for item in plan.forbidden_phrases if item)

