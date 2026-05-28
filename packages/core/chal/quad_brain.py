"""Serialized Quad Brain arbitration for the Synthesus 5 CHAL path."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping

try:
    from reasoning.generation import (
        CGPUFrame,
        CGPURenderer,
        ResponsePlan,
        TemplateLeakageGuard,
        TemplateSurface,
    )
except ModuleNotFoundError:  # pragma: no cover - package-root compatibility path
    from packages.reasoning.generation import (
        CGPUFrame,
        CGPURenderer,
        ResponsePlan,
        TemplateLeakageGuard,
        TemplateSurface,
    )

from .hypervisor import HypervisorDecision, HypervisorRoute


class QuadBrainRole(str, Enum):
    KNOWLEDGE_GROUNDING = "knowledge_grounding"
    EXECUTIVE_REASONING = "executive_reasoning"
    CGPU_RENDERING = "cgpu_rendering"
    CRITIC_METACOGNITION = "critic_metacognition"


@dataclass(frozen=True)
class QuadBrainOutput:
    role: QuadBrainRole
    device: str
    content: dict[str, Any]
    confidence: float
    trace: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["role"] = self.role.value
        return data


@dataclass(frozen=True)
class QuadBrainArbitration:
    trace_id: str
    selected_response: str
    selected_source: str
    outputs: list[QuadBrainOutput]
    serial_order: list[str]
    state_contract: dict[str, Any]
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "synthesus.chal.quad_brain_arbitration.v1",
            "trace_id": self.trace_id,
            "selected_response": self.selected_response,
            "selected_source": self.selected_source,
            "outputs": [output.to_dict() for output in self.outputs],
            "serial_order": list(self.serial_order),
            "state_contract": dict(self.state_contract),
            "latency_ms": self.latency_ms,
        }


class QuadBrainOrchestrator:
    """Run the four Synthesus 5 brains through one serialized arbiter."""

    def __init__(
        self,
        cgpu_renderer: CGPURenderer | None = None,
        template_guard: TemplateLeakageGuard | None = None,
    ):
        self._cgpu_renderer = cgpu_renderer or CGPURenderer()
        self._template_guard = template_guard or TemplateLeakageGuard()

    def arbitrate(
        self,
        *,
        query: str,
        decision: HypervisorDecision,
        bridge_result: Mapping[str, Any],
        rag_context: str = "",
        character_context: Mapping[str, Any] | None = None,
        constraints: list[str] | None = None,
        max_tokens: int = 512,
        surface: TemplateSurface = TemplateSurface.NORMAL,
    ) -> QuadBrainArbitration:
        start = time.time()
        serial_order = [role.value for role in QuadBrainRole]

        knowledge = self._knowledge_grounding(
            query=query,
            decision=decision,
            bridge_result=bridge_result,
            rag_context=rag_context,
        )
        executive = self._executive_reasoning(
            query=query,
            decision=decision,
            bridge_result=bridge_result,
            knowledge=knowledge,
            character_context=character_context,
            constraints=constraints or [],
            max_tokens=max_tokens,
        )
        cgpu = self._cgpu_rendering(
            query=query,
            decision=decision,
            executive=executive,
            knowledge=knowledge,
            character_context=character_context,
        )
        critic = self._critic_metacognition(cgpu=cgpu, surface=surface)

        selected_response = str(critic.content.get("selected_response") or "")
        selected_source = "critic_metacognition"
        if not selected_response:
            selected_response = str(bridge_result.get("response", ""))
            selected_source = "hemisphere_bridge_fallback"

        return QuadBrainArbitration(
            trace_id=decision.trace_id,
            selected_response=selected_response,
            selected_source=selected_source,
            outputs=[knowledge, executive, cgpu, critic],
            serial_order=serial_order,
            state_contract={
                "topology": "knowledge->executive->cgpu->critic",
                "parallel_brain_spawn": False,
                "serialized_arbitration": True,
                "template_leakage_allowed": surface is not TemplateSurface.NORMAL,
                "bridge_trace_id": bridge_result.get("hypervisor_trace", {}).get("trace_id"),
                "route": decision.route.value,
            },
            latency_ms=(time.time() - start) * 1000,
        )

    def _knowledge_grounding(
        self,
        *,
        query: str,
        decision: HypervisorDecision,
        bridge_result: Mapping[str, Any],
        rag_context: str,
    ) -> QuadBrainOutput:
        facts = self._facts_from_context(rag_context)
        if not facts:
            response = str(bridge_result.get("response", "")).strip()
            if response:
                facts.append(response)
        provenance = []
        if rag_context.strip():
            provenance.append({"source": "rag_context", "trace_id": decision.trace_id})
        return QuadBrainOutput(
            role=QuadBrainRole.KNOWLEDGE_GROUNDING,
            device="chal://knowledge/grounding",
            content={
                "query": query,
                "facts": facts,
                "provenance": provenance,
                "grounding_required": bool(
                    rag_context.strip()
                    or "ground_response_in_mounted_knowledge" in decision.constraints
                ),
            },
            confidence=0.78 if facts else 0.35,
            trace={"trace_id": decision.trace_id, "source": "rag_context_or_bridge_result"},
            warnings=[] if facts else ["no_grounding_facts_available"],
        )

    def _executive_reasoning(
        self,
        *,
        query: str,
        decision: HypervisorDecision,
        bridge_result: Mapping[str, Any],
        knowledge: QuadBrainOutput,
        character_context: Mapping[str, Any] | None,
        constraints: list[str],
        max_tokens: int,
    ) -> QuadBrainOutput:
        facts = [str(fact) for fact in knowledge.content.get("facts", []) if str(fact).strip()]
        style = "concise" if max_tokens <= 256 else "balanced"
        mode = "persona" if character_context else "general"
        forbidden = ["[module]", "[fallback]", "response_template", "Handled:", "No route matched"]
        plan = ResponsePlan(
            intent=self._intent_for_route(decision.route),
            style=style,
            safety_level=0.8 if decision.route == HypervisorRoute.SAFETY_PATH else 0.25,
            target_length=max(48, min(max_tokens, 220)),
            personality=[
                str(character_context.get("persona") or character_context.get("character_id"))
            ] if character_context else [],
            key_points=facts[:2],
            required_phrases=[],
            forbidden_phrases=forbidden,
            domain=mode,
            decoder_mode="deterministic",
        )
        return QuadBrainOutput(
            role=QuadBrainRole.EXECUTIVE_REASONING,
            device="chal://reasoning/executive",
            content={
                "plan": asdict(plan),
                "constraints": [*decision.constraints, *constraints],
                "bridge_hemisphere_used": bridge_result.get("hemisphere_used"),
            },
            confidence=0.82,
            trace={"trace_id": decision.trace_id, "candidate_budget": decision.budget.candidate_count},
        )

    def _cgpu_rendering(
        self,
        *,
        query: str,
        decision: HypervisorDecision,
        executive: QuadBrainOutput,
        knowledge: QuadBrainOutput,
        character_context: Mapping[str, Any] | None,
    ) -> QuadBrainOutput:
        plan = ResponsePlan(**executive.content["plan"])
        facts = [str(fact) for fact in knowledge.content.get("facts", []) if str(fact).strip()]
        frame = CGPUFrame.create(
            query=query,
            plan=plan,
            trace_id=decision.trace_id,
            grounded_state={"facts": facts},
            mode="persona" if character_context else "general",
            candidate_count=decision.budget.candidate_count,
            critic_passes=decision.budget.critic_passes,
            constraints=list(executive.content.get("constraints", [])),
            persona=dict(character_context or {}),
            provenance=list(knowledge.content.get("provenance", [])),
        )
        output = self._cgpu_renderer.render(frame)
        return QuadBrainOutput(
            role=QuadBrainRole.CGPU_RENDERING,
            device=output.device,
            content=output.to_dict(),
            confidence=output.confidence,
            trace=output.trace,
            warnings=list(output.warnings),
        )

    def _critic_metacognition(
        self,
        *,
        cgpu: QuadBrainOutput,
        surface: TemplateSurface,
    ) -> QuadBrainOutput:
        selected = str(cgpu.content.get("selected_text") or "")
        guard_result = self._template_guard.inspect(selected, surface=surface)
        warnings = list(cgpu.warnings)
        if guard_result.rewritten:
            warnings.append("template_surface_quarantined")
        return QuadBrainOutput(
            role=QuadBrainRole.CRITIC_METACOGNITION,
            device="chal://critic/metacognition",
            content={
                "selected_response": guard_result.text,
                "selected_candidate_id": cgpu.content.get("selected_candidate_id"),
                "template_guard": guard_result.to_dict(),
                "cgpu_confidence": cgpu.confidence,
            },
            confidence=cgpu.confidence if guard_result.allowed else 0.0,
            trace={
                "trace_id": cgpu.content.get("trace_id") or f"critic-{uuid.uuid4().hex[:12]}",
                "safety_arbitration_required": True,
            },
            warnings=warnings,
        )

    def _intent_for_route(self, route: HypervisorRoute) -> str:
        if route == HypervisorRoute.SAFETY_PATH:
            return "safety"
        if route == HypervisorRoute.QUAD_BRAIN_PATH:
            return "render"
        if route == HypervisorRoute.GROUNDED_PATH:
            return "grounded_answer"
        if route == HypervisorRoute.DEEP_REASONING_PATH:
            return "reason"
        return "inform"

    def _facts_from_context(self, context: str) -> list[str]:
        return [
            line.strip("-• \t")
            for line in context.splitlines()
            if line.strip("-• \t")
        ][:4]
