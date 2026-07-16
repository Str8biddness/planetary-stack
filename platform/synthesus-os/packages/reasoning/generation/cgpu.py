"""CGPU candidate rendering contract for Synthesus 5.

The Cognitive GPU renders surface candidates from grounded state. It does not
own truth: every frame carries grounding, constraints, provenance, and critic
results so the hypervisor/arbiter can decide what may be emitted.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .critic import CriticDecision, Critique, ResponseCritic
from .response_plan import GenerationTrace, ResponsePlan
from .surface_realizer import RealizationRequest, SurfaceRealizer


@dataclass(frozen=True)
class CGPUFrame:
    """Input frame for the CHAL CGPU render device."""

    frame_id: str
    trace_id: str
    query: str
    plan: ResponsePlan
    grounded_state: dict[str, Any] = field(default_factory=dict)
    mode: str = "general"
    candidate_count: int = 1
    critic_passes: int = 1
    constraints: list[str] = field(default_factory=list)
    persona: dict[str, Any] = field(default_factory=dict)
    provenance: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        query: str,
        plan: ResponsePlan,
        trace_id: str | None = None,
        grounded_state: dict[str, Any] | None = None,
        mode: str = "general",
        candidate_count: int = 1,
        critic_passes: int = 1,
        constraints: list[str] | None = None,
        persona: dict[str, Any] | None = None,
        provenance: list[dict[str, Any]] | None = None,
    ) -> "CGPUFrame":
        frame_id = f"cgpu-{uuid.uuid4().hex[:12]}"
        return cls(
            frame_id=frame_id,
            trace_id=trace_id or frame_id,
            query=query,
            plan=plan,
            grounded_state=grounded_state or {},
            mode=mode,
            candidate_count=max(1, candidate_count),
            critic_passes=max(0, critic_passes),
            constraints=list(constraints or []),
            persona=dict(persona or {}),
            provenance=list(provenance or []),
        )

    def grounding_required(self) -> bool:
        return bool(
            self.plan.key_points
            or self.plan.required_phrases
            or self.grounded_state.get("facts")
            or self.grounded_state.get("evidence")
            or self.provenance
            or "ground_response_in_mounted_knowledge" in self.constraints
        )


@dataclass(frozen=True)
class CGPUCandidate:
    """One rendered surface candidate and its critic result."""

    candidate_id: str
    text: str
    mode: str
    critique: Critique
    trace: GenerationTrace
    rewrite_count: int = 0
    blocked: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.critique.decision == CriticDecision.ACCEPT and not self.blocked

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["critique"]["decision"] = self.critique.decision.value
        data["accepted"] = self.accepted
        return data


@dataclass(frozen=True)
class CGPUOutputFrame:
    """Output frame emitted by the CHAL CGPU render device."""

    frame_id: str
    parent_frame_id: str
    trace_id: str
    device: str
    kind: str
    candidates: list[CGPUCandidate]
    selected_candidate_id: str | None
    confidence: float
    cost: dict[str, Any]
    trace: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    @property
    def selected_text(self) -> str:
        for candidate in self.candidates:
            if candidate.candidate_id == self.selected_candidate_id:
                return candidate.text
        return ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "parent_frame_id": self.parent_frame_id,
            "trace_id": self.trace_id,
            "device": self.device,
            "kind": self.kind,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "selected_candidate_id": self.selected_candidate_id,
            "selected_text": self.selected_text,
            "confidence": self.confidence,
            "cost": dict(self.cost),
            "trace": dict(self.trace),
            "warnings": list(self.warnings),
        }


class CGPURenderer:
    """Render bounded surface candidates from grounded cognitive state."""

    device = "chal://cgpu/render"

    def __init__(
        self,
        realizer: SurfaceRealizer | None = None,
        critic: ResponseCritic | None = None,
    ):
        self.realizer = realizer or SurfaceRealizer()
        self.critic = critic or ResponseCritic()

    def render(self, frame: CGPUFrame) -> CGPUOutputFrame:
        start = time.time()
        warnings: list[str] = []
        if frame.grounding_required() and not self._has_grounded_content(frame):
            warnings.append("grounding_required_but_empty")

        candidates = [
            self._render_candidate(frame, index)
            for index in range(frame.candidate_count)
        ]
        selected = self._select_candidate(candidates)
        if selected is None:
            warnings.append("no_candidate_passed_critic")

        confidence = selected.critique.score if selected else 0.0
        latency_ms = (time.time() - start) * 1000
        return CGPUOutputFrame(
            frame_id=f"cgpu-out-{uuid.uuid4().hex[:12]}",
            parent_frame_id=frame.frame_id,
            trace_id=frame.trace_id,
            device=self.device,
            kind="candidate_set",
            candidates=candidates,
            selected_candidate_id=selected.candidate_id if selected else None,
            confidence=confidence,
            cost={
                "latency_ms": latency_ms,
                "candidate_count": len(candidates),
                "critic_passes": frame.critic_passes,
            },
            trace={
                "mode": frame.mode,
                "constraints": list(frame.constraints),
                "provenance": list(frame.provenance),
                "grounding_required": frame.grounding_required(),
                "safety_arbitration_required": True,
            },
            warnings=warnings,
        )

    def _render_candidate(self, frame: CGPUFrame, index: int) -> CGPUCandidate:
        seed = self._seed_text(frame, index)
        realization = self.realizer.realize(
            RealizationRequest(
                plan=frame.plan,
                context=self._context_text(frame),
                seed_text=seed,
                max_attempts=frame.critic_passes + 1,
            )
        )
        text = realization.text
        critique = self.critic.critique(text, frame.plan)
        rewrite_count = 0

        while critique.decision == CriticDecision.REWRITE and rewrite_count < frame.critic_passes:
            text = self._rewrite_candidate(text, critique, frame)
            critique = self.critic.critique(text, frame.plan)
            rewrite_count += 1

        trace = GenerationTrace(
            text=text,
            mean_logprob=critique.score,
            constraints_satisfied=critique.decision == CriticDecision.ACCEPT,
            forbidden_triggered=critique.decision == CriticDecision.BLOCK,
            decode_attempts=1 + rewrite_count,
        )
        return CGPUCandidate(
            candidate_id=f"{frame.frame_id}-cand-{index + 1}",
            text=text,
            mode=frame.mode,
            critique=critique,
            trace=trace,
            rewrite_count=rewrite_count,
            blocked=critique.decision == CriticDecision.BLOCK,
            diagnostics=realization.diagnostics,
        )

    def _seed_text(self, frame: CGPUFrame, index: int) -> str:
        facts = self._facts(frame)
        anchors = self._anchors(frame)
        focus = facts[index % len(facts)] if facts else frame.query.strip()
        required = " ".join(anchor for anchor in anchors if anchor and anchor.lower() not in focus.lower())
        if required:
            focus = f"{focus} {required}".strip()

        if frame.mode in {"business", "business_bot"}:
            return self._business_seed(frame, focus, index)
        if frame.mode in {"npc", "persona", "dialogue"}:
            return self._persona_seed(frame, focus, index)
        if index == 0:
            return focus
        if index == 1:
            return f"{focus} The route stays grounded before final arbitration."
        return f"{frame.query.strip()} {focus}".strip()

    def _business_seed(self, frame: CGPUFrame, focus: str, index: int) -> str:
        prefix = "Direct answer:" if index == 0 else "Recommended next step:"
        return f"{prefix} {focus}".strip()

    def _persona_seed(self, frame: CGPUFrame, focus: str, index: int) -> str:
        name = frame.persona.get("name") or frame.persona.get("character_id") or frame.plan.style
        stance = frame.persona.get("stance") or "in character"
        if index == 0:
            return f"{name}: {focus}"
        return f"{name} stays {stance}: {focus}"

    def _rewrite_candidate(self, text: str, critique: Critique, frame: CGPUFrame) -> str:
        additions: list[str] = []
        for hint in critique.rewrite_hints:
            marker = "Include required content: "
            if hint.startswith(marker):
                required = hint.removeprefix(marker)
                if required and required.lower() not in text.lower():
                    additions.append(required)
        if not additions and not text.strip():
            additions = self._anchors(frame) or self._facts(frame) or [frame.query]
        return " ".join(part for part in [text.strip(), *additions] if part).strip()

    def _select_candidate(self, candidates: list[CGPUCandidate]) -> CGPUCandidate | None:
        accepted = [candidate for candidate in candidates if candidate.accepted]
        if accepted:
            return max(accepted, key=lambda candidate: candidate.critique.score)
        non_blocked = [candidate for candidate in candidates if not candidate.blocked]
        if non_blocked:
            return max(non_blocked, key=lambda candidate: candidate.critique.score)
        return None

    def _has_grounded_content(self, frame: CGPUFrame) -> bool:
        return bool(self._facts(frame) or frame.provenance)

    def _anchors(self, frame: CGPUFrame) -> list[str]:
        return [*frame.plan.key_points, *frame.plan.required_phrases]

    def _facts(self, frame: CGPUFrame) -> list[str]:
        facts = frame.grounded_state.get("facts") or frame.grounded_state.get("evidence") or []
        if isinstance(facts, str):
            return [facts]
        return [str(fact) for fact in facts if str(fact).strip()]

    def _context_text(self, frame: CGPUFrame) -> str:
        return "\n".join(self._facts(frame))
