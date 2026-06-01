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
        quad_brain_orchestrator: Any | None = None,
        knowledge_controller: Any | None = None,
    ):
        self._bridge_factory = bridge_factory
        self._bridge: Any | None = None
        self._execution_guard = execution_guard or AIVMExecutionGuard()
        self._template_guard = template_guard or TemplateLeakageGuard()
        self._quad_brain_orchestrator = quad_brain_orchestrator
        self._knowledge_controller = knowledge_controller

    def plan(
        self,
        query: str,
        *,
        rag_context: str = "",
        character_context: Mapping[str, Any] | None = None,
        constraints: list[str] | None = None,
        runtime_preset: str | None = None,
        max_tokens: int = 512,
    ) -> HypervisorDecision:
        normalized = query.lower()
        active_constraints = list(constraints or [])
        preset = self._normalize_runtime_preset(runtime_preset)
        if preset:
            active_constraints.append(f"runtime_preset:{preset}")
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
        elif preset == "business_bot":
            route = HypervisorRoute.QUAD_BRAIN_PATH
            hemisphere_mode = "auto"
            budget = HypervisorBudget(
                latency_ms=800.0,
                retrieval_depth=2,
                candidate_count=2,
                critic_passes=1,
            )
            reasons.append("business_bot_preset")
            active_constraints.extend(
                [
                    "business_bot_concise_action_surface",
                    "compact_surface_response",
                    "serialize_arbitration_after_parallel_dispatch",
                ]
            )
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
        runtime_preset: str | None = None,
        max_tokens: int = 512,
    ) -> HypervisorResult:
        start = time.time()
        preset = self._normalize_runtime_preset(runtime_preset)
        decision = self.plan(
            query,
            rag_context=rag_context,
            character_context=character_context,
            constraints=constraints,
            runtime_preset=preset,
            max_tokens=max_tokens,
        )
        effective_rag_context = rag_context
        knowledge_provenance = None
        if decision.route == HypervisorRoute.GROUNDED_PATH:
            effective_rag_context, knowledge_provenance = self._resolve_grounding_context(
                query=query,
                trace_id=decision.trace_id,
                rag_context=rag_context,
            )
        bridge = self._get_bridge()
        guarded = await self._execution_guard.run(
            "chal://hypervisor/hemisphere_bridge",
            lambda: bridge.route_query(
                query,
                hemisphere=decision.hemisphere_mode,
                character_context=character_context,
                rag_context=effective_rag_context,
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
        quad_brain_arbitration = None
        if guarded.ok and decision.route == HypervisorRoute.QUAD_BRAIN_PATH:
            quad_brain_arbitration = self._get_quad_brain_orchestrator().arbitrate(
                query=query,
                decision=decision,
                bridge_result=bridge_result,
                rag_context=effective_rag_context,
                character_context=character_context,
                constraints=constraints or [],
                runtime_preset=preset,
                max_tokens=max_tokens,
                surface=self._template_surface(decision),
            )
            bridge_result["quad_brain_arbitration"] = quad_brain_arbitration.to_dict()
            response = quad_brain_arbitration.selected_response
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
            "runtime_preset": preset,
            "bridge_latency_ms": bridge_result.get("latency_ms", 0.0),
            "device_isolation": guarded.to_dict(),
            "budget_exhausted": guarded.status == "timeout",
            "degraded": not guarded.ok,
            "template_guard": template_guard_result.to_dict(),
            "quad_brain": quad_brain_arbitration.to_dict() if quad_brain_arbitration else None,
            "knowledge_provenance": knowledge_provenance,
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

    def _get_quad_brain_orchestrator(self) -> Any:
        if self._quad_brain_orchestrator is None:
            try:
                from core.chal.quad_brain import QuadBrainOrchestrator
            except ModuleNotFoundError:  # pragma: no cover
                from packages.core.chal.quad_brain import QuadBrainOrchestrator

            self._quad_brain_orchestrator = QuadBrainOrchestrator(
                template_guard=self._template_guard,
            )
        return self._quad_brain_orchestrator

    def _get_knowledge_controller(self) -> Any:
        if self._knowledge_controller is None:
            try:
                from knowledge.kal_adapter import CHALMemoryController
            except ModuleNotFoundError:  # pragma: no cover
                from packages.knowledge.kal_adapter import CHALMemoryController

            self._knowledge_controller = CHALMemoryController()
        return self._knowledge_controller

    def _resolve_grounding_context(
        self,
        *,
        query: str,
        trace_id: str,
        rag_context: str,
    ) -> tuple[str, dict[str, Any]]:
        if rag_context.strip():
            return rag_context, {
                "schema": "synthesus.chal.knowledge_provenance.v1",
                "trace_id": trace_id,
                "source": "provided_rag_context",
                "context_used": True,
                "mounted_context_used": False,
                "cache_hit": False,
                "confidence": 1.0,
                "latency_ms": 0.0,
                "mounts": [],
                "hot_context": False,
            }

        try:
            context, telemetry = self._get_knowledge_controller().query(query)
        except Exception as exc:
            return "", {
                "schema": "synthesus.chal.knowledge_provenance.v1",
                "trace_id": trace_id,
                "source": "knowledge_controller_unavailable",
                "context_used": False,
                "mounted_context_used": False,
                "cache_hit": False,
                "confidence": 0.0,
                "latency_ms": 0.0,
                "mounts": [],
                "hot_context": False,
                "error": str(exc),
            }

        metadata = dict(getattr(telemetry, "metadata", {}) or {})
        mounts = list(metadata.get("mounts", []))
        context_used = bool(context) and getattr(telemetry, "confidence", 0.0) > 0.0
        mounted_context_used = context_used and bool(mounts)
        return (context or "") if mounted_context_used else "", {
            "schema": "synthesus.chal.knowledge_provenance.v1",
            "trace_id": trace_id,
            "operation_id": getattr(telemetry, "operation_id", ""),
            "source": getattr(telemetry, "source", ""),
            "context_used": context_used,
            "mounted_context_used": mounted_context_used,
            "cache_hit": bool(getattr(telemetry, "cache_hit", False)),
            "confidence": getattr(telemetry, "confidence", 0.0),
            "latency_ms": getattr(telemetry, "latency_ms", 0.0),
            "mounts": mounts,
            "hot_context": bool(metadata.get("hot_context", False)),
        }

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

    def _normalize_runtime_preset(self, runtime_preset: str | None) -> str | None:
        if runtime_preset is None:
            return None
        value = runtime_preset.strip().lower().replace("-", "_")
        if value in {"", "none", "default"}:
            return None
        if value in {"business", "business_bot", "businessbot"}:
            return "business_bot"
        return value
