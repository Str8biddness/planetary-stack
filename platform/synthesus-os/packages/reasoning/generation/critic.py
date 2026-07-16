"""Critic interface for the bounded generation rewrite loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .response_plan import ResponsePlan


class CriticDecision(str, Enum):
    """Allowed critic outcomes for a generated candidate."""

    ACCEPT = "accept"
    REWRITE = "rewrite"
    BLOCK = "block"


@dataclass(frozen=True)
class Critique:
    """Structured critique of a candidate generation."""

    decision: CriticDecision
    score: float
    reasons: list[str] = field(default_factory=list)
    rewrite_hints: list[str] = field(default_factory=list)


class ResponseCritic:
    """Evaluate whether candidate text satisfies the bounded plan."""

    def critique(self, text: str, plan: ResponsePlan) -> Critique:
        """Critique a candidate response.

        TODO: Integrate verifier, identity policy, and safety classifiers for a
        full plan -> realize -> critique -> rewrite -> emit loop.
        """
        reasons: list[str] = []
        lowered = text.lower()
        if not text.strip():
            return Critique(
                decision=CriticDecision.REWRITE,
                score=0.0,
                reasons=["empty_candidate"],
                rewrite_hints=["Generate a non-empty response grounded in the plan."],
            )
        forbidden = [phrase for phrase in plan.forbidden_phrases if phrase.lower() in lowered]
        if forbidden:
            return Critique(
                decision=CriticDecision.BLOCK,
                score=0.0,
                reasons=["forbidden_phrase_triggered"],
                rewrite_hints=[f"Remove forbidden phrase: {phrase}" for phrase in forbidden],
            )
        missing = [
            phrase
            for phrase in [*plan.key_points, *plan.required_phrases]
            if phrase and phrase.lower() not in lowered
        ]
        if missing:
            reasons.append("missing_required_content")
            return Critique(
                decision=CriticDecision.REWRITE,
                score=0.5,
                reasons=reasons,
                rewrite_hints=[f"Include required content: {phrase}" for phrase in missing],
            )
        return Critique(decision=CriticDecision.ACCEPT, score=1.0)

