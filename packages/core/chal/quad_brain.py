"""Serialized Quad Brain arbitration for the Synthesus 5 CHAL path."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
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
class QuadBrainStateTransition:
    role: QuadBrainRole
    input_refs: list[str]
    output_refs: list[str]
    device: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "input_refs": list(self.input_refs),
            "output_refs": list(self.output_refs),
            "device": self.device,
        }


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

    def to_replay_record(
        self,
        *,
        prompt_ref: str | None = None,
        runtime_preset: str | None = None,
    ) -> dict[str, Any]:
        output_roles = [output.role.value for output in self.outputs]
        output_devices = {output.role.value: output.device for output in self.outputs}
        output_confidence = {
            output.role.value: round(float(output.confidence), 6)
            for output in self.outputs
        }
        return {
            "schema": "synthesus.chal.quad_brain_replay.v1",
            "trace_id": self.trace_id,
            "prompt_ref": prompt_ref,
            "runtime_preset": runtime_preset,
            "selected_source": self.selected_source,
            "selected_response_sha256": sha256(
                self.selected_response.encode("utf-8")
            ).hexdigest(),
            "selected_response_chars": len(self.selected_response),
            "serial_order": list(self.serial_order),
            "output_roles": output_roles,
            "output_devices": output_devices,
            "output_confidence": output_confidence,
            "state_contract": {
                "topology": self.state_contract.get("topology"),
                "parallel_brain_spawn": self.state_contract.get("parallel_brain_spawn"),
                "serialized_arbitration": self.state_contract.get("serialized_arbitration"),
                "required_roles": list(self.state_contract.get("required_roles", [])),
                "state_transitions": list(self.state_contract.get("state_transitions", [])),
                "critic_input_ref": self.state_contract.get("critic_input_ref"),
                "critic_reviewed_candidate_id": self.state_contract.get(
                    "critic_reviewed_candidate_id"
                ),
                "final_output_ref": self.state_contract.get("final_output_ref"),
                "final_output_owner": self.state_contract.get("final_output_owner"),
                "integrity": dict(self.state_contract.get("integrity", {})),
            },
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
        runtime_preset: str | None = None,
        max_tokens: int = 512,
        surface: TemplateSurface = TemplateSurface.NORMAL,
    ) -> QuadBrainArbitration:
        start = time.time()
        serial_order = [role.value for role in QuadBrainRole]
        transitions = self._state_transitions()

        knowledge = self._knowledge_grounding(
            query=query,
            decision=decision,
            bridge_result=bridge_result,
            rag_context=rag_context,
            transition=transitions[QuadBrainRole.KNOWLEDGE_GROUNDING],
        )
        executive = self._executive_reasoning(
            query=query,
            decision=decision,
            bridge_result=bridge_result,
            knowledge=knowledge,
            character_context=character_context,
            constraints=constraints or [],
            runtime_preset=runtime_preset,
            max_tokens=max_tokens,
            transition=transitions[QuadBrainRole.EXECUTIVE_REASONING],
        )
        cgpu = self._cgpu_rendering(
            query=query,
            decision=decision,
            executive=executive,
            knowledge=knowledge,
            character_context=character_context,
            runtime_preset=runtime_preset,
            transition=transitions[QuadBrainRole.CGPU_RENDERING],
        )
        critic = self._critic_metacognition(
            cgpu=cgpu,
            surface=surface,
            transition=transitions[QuadBrainRole.CRITIC_METACOGNITION],
        )

        selected_response = str(critic.content.get("selected_response") or "")
        selected_source = "critic_metacognition"
        if not selected_response:
            selected_response = str(bridge_result.get("response", ""))
            selected_source = "hemisphere_bridge_fallback"

        outputs = [knowledge, executive, cgpu, critic]
        state_contract = {
            "topology": "knowledge->executive->cgpu->critic",
            "parallel_brain_spawn": False,
            "serialized_arbitration": True,
            "template_leakage_allowed": surface is not TemplateSurface.NORMAL,
            "bridge_trace_id": bridge_result.get("hypervisor_trace", {}).get("trace_id"),
            "route": decision.route.value,
            "required_roles": serial_order,
            "state_transitions": [
                transitions[role].to_dict()
                for role in QuadBrainRole
            ],
            "critic_input_ref": "cgpu.selected_candidate",
            "critic_reviewed_candidate_id": cgpu.content.get("selected_candidate_id"),
            "final_output_ref": "critic.selected_response",
            "final_output_owner": selected_source,
        }
        state_contract["integrity"] = self._state_contract_integrity(
            outputs=outputs,
            serial_order=serial_order,
            transitions=state_contract["state_transitions"],
            selected_source=selected_source,
        )

        return QuadBrainArbitration(
            trace_id=decision.trace_id,
            selected_response=selected_response,
            selected_source=selected_source,
            outputs=outputs,
            serial_order=serial_order,
            state_contract=state_contract,
            latency_ms=(time.time() - start) * 1000,
        )

    def _knowledge_grounding(
        self,
        *,
        query: str,
        decision: HypervisorDecision,
        bridge_result: Mapping[str, Any],
        rag_context: str,
        transition: QuadBrainStateTransition,
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
            trace={
                "trace_id": decision.trace_id,
                "source": "rag_context_or_bridge_result",
                "state_transition": transition.to_dict(),
            },
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
        runtime_preset: str | None,
        max_tokens: int,
        transition: QuadBrainStateTransition,
    ) -> QuadBrainOutput:
        facts = [str(fact) for fact in knowledge.content.get("facts", []) if str(fact).strip()]
        business_preset = runtime_preset == "business_bot"
        style = "concise" if business_preset or max_tokens <= 256 else "balanced"
        mode = "business_bot" if business_preset else "persona" if character_context else "general"
        forbidden = ["[module]", "[fallback]", "response_template", "Handled:", "No route matched"]
        plan = ResponsePlan(
            intent="business_action" if business_preset else self._intent_for_route(decision.route),
            style=style,
            safety_level=0.8 if decision.route == HypervisorRoute.SAFETY_PATH else 0.25,
            target_length=max(48, min(160 if business_preset else max_tokens, 220)),
            personality=[
                str(character_context.get("persona") or character_context.get("character_id"))
            ] if character_context and not business_preset else [],
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
            trace={
                "trace_id": decision.trace_id,
                "candidate_budget": decision.budget.candidate_count,
                "state_transition": transition.to_dict(),
            },
        )

    def _cgpu_rendering(
        self,
        *,
        query: str,
            decision: HypervisorDecision,
            executive: QuadBrainOutput,
            knowledge: QuadBrainOutput,
            character_context: Mapping[str, Any] | None,
            runtime_preset: str | None,
            transition: QuadBrainStateTransition,
    ) -> QuadBrainOutput:
        plan = ResponsePlan(**executive.content["plan"])
        facts = [str(fact) for fact in knowledge.content.get("facts", []) if str(fact).strip()]
        mode = "business_bot" if runtime_preset == "business_bot" else "persona" if character_context else "general"
        frame = CGPUFrame.create(
            query=query,
            plan=plan,
            trace_id=decision.trace_id,
            grounded_state={"facts": facts},
            mode=mode,
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
            trace={**output.trace, "state_transition": transition.to_dict()},
            warnings=list(output.warnings),
        )

    def _critic_metacognition(
        self,
        *,
        cgpu: QuadBrainOutput,
        surface: TemplateSurface,
        transition: QuadBrainStateTransition,
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
                "reviewed_candidate_ref": "cgpu.selected_candidate",
                "template_guard": guard_result.to_dict(),
                "cgpu_confidence": cgpu.confidence,
            },
            confidence=cgpu.confidence if guard_result.allowed else 0.0,
            trace={
                "trace_id": cgpu.content.get("trace_id") or f"critic-{uuid.uuid4().hex[:12]}",
                "safety_arbitration_required": True,
                "input_refs": ["cgpu.selected_candidate", "template_surface"],
                "reviewed_candidate_id": cgpu.content.get("selected_candidate_id"),
                "state_transition": transition.to_dict(),
            },
            warnings=warnings,
        )

    def _state_transitions(self) -> dict[QuadBrainRole, QuadBrainStateTransition]:
        return {
            QuadBrainRole.KNOWLEDGE_GROUNDING: QuadBrainStateTransition(
                role=QuadBrainRole.KNOWLEDGE_GROUNDING,
                device="chal://knowledge/grounding",
                input_refs=["query", "rag_context", "hemisphere_bridge.response"],
                output_refs=["knowledge.facts", "knowledge.provenance"],
            ),
            QuadBrainRole.EXECUTIVE_REASONING: QuadBrainStateTransition(
                role=QuadBrainRole.EXECUTIVE_REASONING,
                device="chal://reasoning/executive",
                input_refs=["hypervisor.decision", "knowledge.facts", "constraints"],
                output_refs=["executive.response_plan", "executive.constraints"],
            ),
            QuadBrainRole.CGPU_RENDERING: QuadBrainStateTransition(
                role=QuadBrainRole.CGPU_RENDERING,
                device="chal://cgpu/render",
                input_refs=["executive.response_plan", "knowledge.facts", "character_context"],
                output_refs=["cgpu.candidates", "cgpu.selected_candidate"],
            ),
            QuadBrainRole.CRITIC_METACOGNITION: QuadBrainStateTransition(
                role=QuadBrainRole.CRITIC_METACOGNITION,
                device="chal://critic/metacognition",
                input_refs=["cgpu.selected_candidate", "template_surface"],
                output_refs=["critic.selected_response", "critic.template_guard"],
            ),
        }

    def _state_contract_integrity(
        self,
        *,
        outputs: list[QuadBrainOutput],
        serial_order: list[str],
        transitions: list[dict[str, Any]],
        selected_source: str,
    ) -> dict[str, Any]:
        output_roles = [output.role.value for output in outputs]
        transition_roles = [str(transition.get("role")) for transition in transitions]
        mirrored_transitions = [
            output.trace.get("state_transition") == transition
            for output, transition in zip(outputs, transitions)
        ]
        cgpu_output = next(
            (output for output in outputs if output.role == QuadBrainRole.CGPU_RENDERING),
            None,
        )
        critic_output = next(
            (output for output in outputs if output.role == QuadBrainRole.CRITIC_METACOGNITION),
            None,
        )
        selected_candidate_id = (
            cgpu_output.content.get("selected_candidate_id")
            if cgpu_output
            else None
        )
        reviewed_candidate_id = (
            critic_output.content.get("selected_candidate_id")
            if critic_output
            else None
        )
        checks = {
            "roles_complete": output_roles == serial_order,
            "serial_order_valid": serial_order == [role.value for role in QuadBrainRole],
            "transitions_complete": transition_roles == serial_order,
            "output_transition_mirrors": all(mirrored_transitions)
            and len(mirrored_transitions) == len(serial_order),
            "critic_handoff_valid": bool(selected_candidate_id)
            and selected_candidate_id == reviewed_candidate_id,
            "final_output_owned_by_critic": selected_source == "critic_metacognition",
        }
        return {
            "status": "passed" if all(checks.values()) else "failed",
            "checks": checks,
            "selected_candidate_id": selected_candidate_id,
            "reviewed_candidate_id": reviewed_candidate_id,
        }

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
