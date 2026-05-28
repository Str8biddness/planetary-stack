"""Synthesus 5 Cognitive Hypervisor MVP.

The hypervisor owns route selection, budget shaping, and trace packaging. It
delegates actual hemisphere execution to the existing bridge so this first
slice changes orchestration without rewriting the runtime.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

try:
    from aivm.isolation.guard import AIVMExecutionGuard, DeviceExecutionResult
except ModuleNotFoundError:  # pragma: no cover - package-root compatibility path
    from packages.aivm.isolation.guard import AIVMExecutionGuard, DeviceExecutionResult

try:
    from reasoning.generation.template_guard import TemplateLeakageGuard, TemplateSurface
except ModuleNotFoundError:  # pragma: no cover - package-root compatibility path
    from packages.reasoning.generation.template_guard import TemplateLeakageGuard, TemplateSurface


class HypervisorRoute(str, Enum):
    FAST_PATH = "fast_path"
    GROUNDED_PATH = "grounded_path"
    DEEP_REASONING_PATH = "deep_reasoning_path"
    QUAD_BRAIN_PATH = "quad_brain_path"
    SAFETY_PATH = "safety_path"


@dataclass(frozen=True)
class HypervisorBudget:
    latency_ms: float
    retrieval_depth: int
    candidate_count: int
    critic_passes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HypervisorDecision:
    trace_id: str
    route: HypervisorRoute
    hemisphere_mode: str
    budget: HypervisorBudget
    reasons: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["route"] = self.route.value
        return data


@dataclass(frozen=True)
class HypervisorResult:
    response: str
    decision: HypervisorDecision
    bridge_result: dict[str, Any]
    telemetry: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "response": self.response,
            "decision": self.decision.to_dict(),
            "bridge_result": self.bridge_result,
            "telemetry": self.telemetry,
        }


BridgeFactory = Callable[[], Any]


class CognitiveHypervisor:
    """Route and dispatch Synthesus 5 cognitive workloads."""

    def __init__(
        self,
        bridge_factory: BridgeFactory | None = None,
        execution_guard: AIVMExecutionGuard | None = None,
        template_guard: TemplateLeakageGuard | None = None,
    ):
        self._bridge_factory = bridge_factory
        self._bridge: Any | None = None
        self._execution_guard = execution_guard or AIVMExecutionGuard()
        self._template_guard = template_guard or TemplateLeakageGuard()

    def plan(
        self,
        query: str,
        *,
        rag_context: str = "",
        character_context: Mapping[str, Any] | None = None,
        constraints: list[str] | None = None,
        max_tokens: int = 512,
    ) -> HypervisorDecision:
        normalized = query.lower()
        active_constraints = list(constraints or [])
        reasons: list[str] = []

        if self._is_safety_workload(normalized, active_constraints):
            route = HypervisorRoute.SAFETY_PATH
            hemisphere_mode = "both"
            budget = HypervisorBudget(
                latency_ms=900.0,
                retrieval_depth=2,
                candidate_count=1,
                critic_passes=2,
            )
            reasons.append("safety_or_platform_constraint")
            active_constraints.append("critic_must_validate_before_emit")
        elif rag_context.strip() or self._needs_grounding(normalized):
            route = HypervisorRoute.GROUNDED_PATH
            hemisphere_mode = "auto"
            budget = HypervisorBudget(
                latency_ms=750.0,
                retrieval_depth=4,
                candidate_count=2,
                critic_passes=1,
            )
            reasons.append("grounding_required")
            active_constraints.append("ground_response_in_mounted_knowledge")
        elif self._needs_quad_brain(normalized, character_context):
            route = HypervisorRoute.QUAD_BRAIN_PATH
            hemisphere_mode = "both"
            budget = HypervisorBudget(
                latency_ms=1200.0,
                retrieval_depth=3,
                candidate_count=4,
                critic_passes=1,
            )
            reasons.append("multi_brain_or_persona_workload")
            active_constraints.append("serialize_arbitration_after_parallel_dispatch")
        elif self._needs_deep_reasoning(normalized):
            route = HypervisorRoute.DEEP_REASONING_PATH
            hemisphere_mode = "both"
            budget = HypervisorBudget(
                latency_ms=1100.0,
                retrieval_depth=3,
                candidate_count=3,
                critic_passes=1,
            )
            reasons.append("decomposition_or_comparison_required")
            active_constraints.append("emit_traceable_reasoning_frame")
        else:
            route = HypervisorRoute.FAST_PATH
            hemisphere_mode = "auto"
            budget = HypervisorBudget(
                latency_ms=450.0,
                retrieval_depth=1,
                candidate_count=1,
                critic_passes=0,
            )
            reasons.append("low_complexity_fast_path")

        if max_tokens <= 256:
            active_constraints.append("compact_surface_response")

        return HypervisorDecision(
            trace_id=f"hv-{uuid.uuid4().hex[:12]}",
            route=route,
            hemisphere_mode=hemisphere_mode,
            budget=budget,
            reasons=reasons,
            constraints=active_constraints,
        )

    async def process_query(
        self,
        query: str,
        *,
        rag_context: str = "",
        character_context: dict[str, Any] | None = None,
        constraints: list[str] | None = None,
        max_tokens: int = 512,
    ) -> HypervisorResult:
        start = time.time()
        decision = self.plan(
            query,
            rag_context=rag_context,
            character_context=character_context,
            constraints=constraints,
            max_tokens=max_tokens,
        )
        bridge = self._get_bridge()
        guarded = await self._execution_guard.run(
            "chal://hypervisor/hemisphere_bridge",
            lambda: bridge.route_query(
                query,
                hemisphere=decision.hemisphere_mode,
                character_context=character_context,
                rag_context=rag_context,
                max_tokens=max_tokens,
            ),
            timeout_ms=decision.budget.latency_ms,
            metadata={
                "trace_id": decision.trace_id,
                "route": decision.route.value,
                "hemisphere_mode": decision.hemisphere_mode,
            },
        )
        bridge_result = self._normalize_guarded_bridge_result(guarded)

        response = str(bridge_result.get("response", ""))
        template_guard_result = self._template_guard.inspect(
            response,
            surface=self._template_surface(decision),
        )
        response = template_guard_result.text
        if template_guard_result.rewritten:
            bridge_result["response"] = response
        telemetry = {
            "schema": "synthesus.chal.hypervisor_trace.v1",
            "trace_id": decision.trace_id,
            "route": decision.route.value,
            "hemisphere_mode": decision.hemisphere_mode,
            "latency_ms": (time.time() - start) * 1000,
            "budget": decision.budget.to_dict(),
            "reasons": list(decision.reasons),
            "constraints": list(decision.constraints),
            "bridge_latency_ms": bridge_result.get("latency_ms", 0.0),
            "device_isolation": guarded.to_dict(),
            "budget_exhausted": guarded.status == "timeout",
            "degraded": not guarded.ok,
            "template_guard": template_guard_result.to_dict(),
        }
        if template_guard_result.rewritten:
            telemetry["degraded"] = True

        bridge_result.setdefault("hypervisor_trace", telemetry)
        return HypervisorResult(
            response=response,
            decision=decision,
            bridge_result=bridge_result,
            telemetry=telemetry,
        )

    def _normalize_guarded_bridge_result(
        self,
        guarded: DeviceExecutionResult,
    ) -> dict[str, Any]:
        if guarded.ok and isinstance(guarded.output, dict):
            result = dict(guarded.output)
            result.setdefault("latency_ms", guarded.latency_ms)
            return result
        if guarded.ok:
            return {
                "response": str(guarded.output or ""),
                "hemisphere_used": "unknown",
                "latency_ms": guarded.latency_ms,
                "device_status": guarded.status,
            }
        return {
            "response": "I could not complete that route within the current cognitive budget.",
            "hemisphere_used": "degraded",
            "latency_ms": guarded.latency_ms,
            "device_status": guarded.status,
            "error": guarded.error,
        }

    def _template_surface(self, decision: HypervisorDecision) -> TemplateSurface:
        constraints = " ".join(decision.constraints).lower()
        if decision.route == HypervisorRoute.SAFETY_PATH or "safety" in constraints:
            return TemplateSurface.SAFETY
        if "platform" in constraints:
            return TemplateSurface.PLATFORM
        if "identity" in constraints or "rights" in constraints:
            return TemplateSurface.IDENTITY_RIGHTS
        if "explicit_npc_script" in constraints:
            return TemplateSurface.EXPLICIT_NPC_SCRIPT
        return TemplateSurface.NORMAL

    def _get_bridge(self) -> Any:
        if self._bridge is None:
            if self._bridge_factory is not None:
                self._bridge = self._bridge_factory()
            else:
                try:
                    from core.hemisphere_bridge import HemisphereBridge
                except ModuleNotFoundError:  # pragma: no cover
                    from packages.core.hemisphere_bridge import HemisphereBridge

                self._bridge = HemisphereBridge(kernel_bin="/tmp/nonexistent-zo-kernel")
        return self._bridge

    def _is_safety_workload(self, query: str, constraints: list[str]) -> bool:
        safety_terms = (
            "suicide",
            "self harm",
            "kill myself",
            "abuse",
            "exploit",
            "password",
            "secret key",
            "bypass safety",
        )
        return any(term in query for term in safety_terms) or any(
            "safety" in item.lower() or "policy" in item.lower()
            for item in constraints
        )

    def _needs_grounding(self, query: str) -> bool:
        grounding_terms = (
            "source",
            "cite",
            "facts",
            "knowledge cloud",
            "kal",
            "kn",
            "parameter disk",
            "manifest",
        )
        return any(term in query for term in grounding_terms)

    def _needs_quad_brain(
        self,
        query: str,
        character_context: Mapping[str, Any] | None,
    ) -> bool:
        if character_context and (
            character_context.get("character_id")
            or character_context.get("persona")
            or character_context.get("npc")
        ):
            return True
        quad_terms = ("npc", "persona", "simulate", "dialogue", "character", "quad brain", "cgpu")
        return any(term in query for term in quad_terms)

    def _needs_deep_reasoning(self, query: str) -> bool:
        deep_terms = (
            "compare",
            "architecture",
            "design",
            "implement",
            "optimize",
            "why",
            "how should",
            "tradeoff",
            "plan",
        )
        return len(query.split()) >= 18 or any(term in query for term in deep_terms)
