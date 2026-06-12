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
        answer_verifier: Any | None = None,
        context_reranker: Any | None = None,
        trace_recorder: Any | None = None,
    ):
        self._bridge_factory = bridge_factory
        self._bridge: Any | None = None
        self._execution_guard = execution_guard or AIVMExecutionGuard()
        self._template_guard = template_guard or TemplateLeakageGuard()
        self._quad_brain_orchestrator = quad_brain_orchestrator
        self._knowledge_controller = knowledge_controller
        self._answer_verifier = answer_verifier
        self._context_reranker = context_reranker
        self._trace_recorder = trace_recorder

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
        effective_rag_context, reranker_trace = self._rerank_grounding_context(
            query=query,
            trace_id=decision.trace_id,
            rag_context=effective_rag_context,
            top_k=decision.budget.retrieval_depth,
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
        bridge_result = self._normalize_guarded_bridge_result(
            guarded,
            decision=decision,
        )

        response = str(bridge_result.get("response", ""))
        quad_brain_arbitration = None
        quad_brain_replay = None
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
            quad_brain_replay = quad_brain_arbitration.to_replay_record(
                prompt_ref="hypervisor.query",
                runtime_preset=preset,
            )
            bridge_result["quad_brain_replay"] = quad_brain_replay
            response = quad_brain_arbitration.selected_response
        template_guard_result = self._template_guard.inspect(
            response,
            surface=self._template_surface(decision),
        )
        response = template_guard_result.text
        if template_guard_result.rewritten:
            bridge_result["response"] = response
            bridge_result.setdefault(
                "degraded_state",
                self._template_quarantine_degraded_state(
                    decision=decision,
                    template_guard_result=template_guard_result,
                ),
            )
        verifier_trace = self._verify_surface_response(
            query=query,
            response=response,
            trace_id=decision.trace_id,
            rag_context=effective_rag_context,
            decision=decision,
        )
        reasoning_revision = self._apply_bounded_reasoning_revision(
            query=query,
            response=response,
            trace_id=decision.trace_id,
            rag_context=effective_rag_context,
            decision=decision,
            verifier_trace=verifier_trace,
            runtime_preset=preset,
        )
        if reasoning_revision.get("status") == "revised":
            response = str(reasoning_revision["selected_text"])
            bridge_result["response"] = response
            bridge_result["reasoning_revision"] = reasoning_revision
            verifier_trace = self._verify_surface_response(
                query=query,
                response=response,
                trace_id=decision.trace_id,
                rag_context=effective_rag_context,
                decision=decision,
            )
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
            "degraded_state": bridge_result.get("degraded_state"),
            "template_guard": template_guard_result.to_dict(),
            "reasoning_quality": verifier_trace,
            "reasoning_revision": reasoning_revision,
            "grounding_reranker": reranker_trace,
            "quad_brain": quad_brain_arbitration.to_dict() if quad_brain_arbitration else None,
            "quad_brain_replay": quad_brain_replay,
            "quad_brain_trace_storage": self._record_quad_brain_replay(
                decision=decision,
                replay_record=quad_brain_replay,
                runtime_preset=preset,
            ),
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

    def _record_quad_brain_replay(
        self,
        *,
        decision: HypervisorDecision,
        replay_record: Mapping[str, Any] | None,
        runtime_preset: str | None,
    ) -> dict[str, Any]:
        storage_trace = {
            "schema": "synthesus.chal.quad_brain_trace_storage.v1",
            "trace_id": decision.trace_id,
            "route": decision.route.value,
            "runtime_preset": runtime_preset,
            "device": "chal://telemetry/quad_brain_replay_store",
            "status": "skipped",
            "stored": False,
            "raw_prompt_stored": False,
            "raw_response_stored": False,
            "record_hash": None,
            "reason": "no_quad_brain_replay_record",
        }
        if replay_record is None:
            return storage_trace
        storage_trace["record_hash"] = replay_record.get("record_hash")
        if self._trace_recorder is None:
            storage_trace["reason"] = "trace_recorder_unmounted"
            return storage_trace

        storage_record = {
            "schema": "synthesus.chal.quad_brain_trace_storage_record.v1",
            "trace_id": decision.trace_id,
            "route": decision.route.value,
            "runtime_preset": runtime_preset,
            "record_hash": replay_record.get("record_hash"),
            "quad_brain_replay": dict(replay_record),
            "raw_prompt_stored": False,
            "raw_response_stored": False,
        }
        try:
            if hasattr(self._trace_recorder, "record"):
                result = self._trace_recorder.record(storage_record)
            else:
                result = self._trace_recorder(storage_record)
        except Exception as exc:
            storage_trace.update(
                {
                    "status": "fault",
                    "reason": "trace_recorder_fault",
                    "error": str(exc),
                }
            )
            return storage_trace

        if isinstance(result, Mapping):
            storage_trace["recorder_result"] = dict(result)
        storage_trace.update(
            {
                "status": "stored",
                "stored": True,
                "reason": "quad_brain_replay_recorded",
            }
        )
        return storage_trace

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

    def _get_answer_verifier(self) -> Any:
        if self._answer_verifier is None:
            try:
                from reasoning.verifier import AnswerVerifier
            except ModuleNotFoundError:  # pragma: no cover
                from packages.reasoning.verifier import AnswerVerifier

            self._answer_verifier = AnswerVerifier()
        return self._answer_verifier

    def _get_context_reranker(self) -> Any:
        if self._context_reranker is None:
            try:
                from reasoning.reranker import CrossEncoderReranker
            except ModuleNotFoundError:  # pragma: no cover
                from packages.reasoning.reranker import CrossEncoderReranker

            self._context_reranker = CrossEncoderReranker()
        return self._context_reranker

    def _split_grounding_context(self, rag_context: str) -> list[str]:
        chunks = [chunk.strip() for chunk in rag_context.split("\n\n") if chunk.strip()]
        return chunks or ([rag_context.strip()] if rag_context.strip() else [])

    def _rerank_grounding_context(
        self,
        *,
        query: str,
        trace_id: str,
        rag_context: str,
        top_k: int,
    ) -> tuple[str, dict[str, Any] | None]:
        chunks = self._split_grounding_context(rag_context)
        if not chunks:
            return rag_context, None

        try:
            ranked = self._get_context_reranker().rerank(
                query,
                chunks,
                top_k=max(1, top_k),
            )
        except Exception as exc:
            return rag_context, {
                "schema": "synthesus.chal.grounding_reranker.v1",
                "trace_id": trace_id,
                "device": "chal://reasoning/reranker",
                "status": "fault",
                "budget": {
                    "retrieval_depth": max(1, top_k),
                    "input_chunks": len(chunks),
                    "selected_chunks": len(chunks),
                    "selection_truncated": False,
                    "budget_exhausted": False,
                },
                "input_chunks": len(chunks),
                "selected_chunks": len(chunks),
                "selected_indices": list(range(len(chunks))),
                "scores": [],
                "final_language_owner": "hemisphere_bridge_or_cgpu",
                "error": str(exc),
            }

        selected_chunks = [str(item.get("chunk", "")) for item in ranked if item.get("chunk")]
        if not selected_chunks:
            selected_chunks = chunks
        selection_truncated = len(chunks) > len(selected_chunks)
        return "\n\n".join(selected_chunks), {
            "schema": "synthesus.chal.grounding_reranker.v1",
            "trace_id": trace_id,
            "device": "chal://reasoning/reranker",
            "status": "ok",
            "budget": {
                "retrieval_depth": max(1, top_k),
                "input_chunks": len(chunks),
                "selected_chunks": len(selected_chunks),
                "selection_truncated": selection_truncated,
                "budget_exhausted": selection_truncated,
            },
            "input_chunks": len(chunks),
            "selected_chunks": len(selected_chunks),
            "selected_indices": [int(item.get("index", -1)) for item in ranked],
            "scores": [float(item.get("score", 0.0)) for item in ranked],
            "final_language_owner": "hemisphere_bridge_or_cgpu",
        }

    def _verify_surface_response(
        self,
        *,
        query: str,
        response: str,
        trace_id: str,
        rag_context: str,
        decision: HypervisorDecision,
    ) -> dict[str, Any]:
        context = self._split_grounding_context(rag_context)
        try:
            result = self._get_answer_verifier().verify(
                response,
                query,
                context=context or None,
            )
        except Exception as exc:
            return {
                "schema": "synthesus.chal.reasoning_quality.v1",
                "trace_id": trace_id,
                "device": "chal://critic/verifier",
                "status": "fault",
                "score": 0.0,
                "issues": [],
                "context_chunks": len(context),
                "critic_passes_budgeted": decision.budget.critic_passes,
                "critic_revision_required": False,
                "budget": {
                    "critic_passes": decision.budget.critic_passes,
                    "revision_passes_required": 0,
                    "revision_passes_available": decision.budget.critic_passes,
                    "revision_budget_exhausted": False,
                },
                "firmware_boundary": "verifier_signal_only",
                "final_language_owner": "generation_spine_or_cgpu_critic",
                "error": str(exc),
            }

        status = getattr(result.status, "value", str(result.status))
        issues = [
            {
                "issue_id": issue.issue_id,
                "severity": issue.severity,
                "category": issue.category,
                "description": issue.description,
                "suggestion": issue.suggestion,
            }
            for issue in getattr(result, "issues", [])
        ]
        revision_required = status in {"failed", "needs_revision", "uncertain"}
        revision_passes_required = 1 if revision_required else 0
        revision_passes_available = max(0, decision.budget.critic_passes)
        revision_budget_exhausted = (
            revision_required and revision_passes_available < revision_passes_required
        )
        revision_route_hint = self._build_revision_route_hint(
            decision=decision,
            trace_id=trace_id,
            verifier_status=status,
            issues=issues,
            revision_required=revision_required,
            revision_passes_required=revision_passes_required,
            revision_passes_available=revision_passes_available,
            revision_budget_exhausted=revision_budget_exhausted,
        )
        return {
            "schema": "synthesus.chal.reasoning_quality.v1",
            "trace_id": trace_id,
            "device": "chal://critic/verifier",
            "status": status,
            "score": float(getattr(result, "score", 0.0)),
            "issues": issues,
            "metadata": dict(getattr(result, "metadata", {}) or {}),
            "context_chunks": len(context),
            "critic_passes_budgeted": decision.budget.critic_passes,
            "critic_revision_required": revision_required and decision.budget.critic_passes > 0,
            "budget": {
                "critic_passes": decision.budget.critic_passes,
                "revision_passes_required": revision_passes_required,
                "revision_passes_available": revision_passes_available,
                "revision_budget_exhausted": revision_budget_exhausted,
            },
            "revision_route_hint": revision_route_hint,
            "firmware_boundary": "verifier_signal_only",
            "final_language_owner": "generation_spine_or_cgpu_critic",
        }

    def _build_revision_route_hint(
        self,
        *,
        decision: HypervisorDecision,
        trace_id: str,
        verifier_status: str,
        issues: list[dict[str, Any]],
        revision_required: bool,
        revision_passes_required: int,
        revision_passes_available: int,
        revision_budget_exhausted: bool,
    ) -> dict[str, Any] | None:
        if not revision_required:
            return None

        if revision_budget_exhausted:
            recommended_route = (
                HypervisorRoute.QUAD_BRAIN_PATH.value
                if decision.route != HypervisorRoute.QUAD_BRAIN_PATH
                else decision.route.value
            )
            reason = "critic_budget_exhausted"
        else:
            recommended_route = decision.route.value
            reason = "active_route_has_critic_budget"

        return {
            "schema": "synthesus.chal.reasoning_revision_route_hint.v1",
            "trace_id": trace_id,
            "device": "chal://hypervisor/route_planner",
            "required": True,
            "reason": reason,
            "verifier_status": verifier_status,
            "current_route": decision.route.value,
            "recommended_route": recommended_route,
            "budget_delta": {
                "critic_passes": max(0, revision_passes_required - revision_passes_available),
                "candidate_count": 1 if revision_budget_exhausted else 0,
            },
            "issue_ids": [str(issue.get("issue_id", "")) for issue in issues if issue.get("issue_id")],
            "firmware_boundary": "scheduler_hint_only",
            "final_language_owner": "generation_spine_or_cgpu_critic",
            "verifier_may_emit_final_language": False,
        }

    def _apply_bounded_reasoning_revision(
        self,
        *,
        query: str,
        response: str,
        trace_id: str,
        rag_context: str,
        decision: HypervisorDecision,
        verifier_trace: Mapping[str, Any],
        runtime_preset: str | None,
    ) -> dict[str, Any]:
        route_hint = verifier_trace.get("revision_route_hint")
        base_trace = {
            "schema": "synthesus.chal.reasoning_revision.v1",
            "trace_id": trace_id,
            "device": "chal://cgpu/revision_render",
            "status": "skipped",
            "route": decision.route.value,
            "source_verifier_status": verifier_trace.get("status"),
            "source_issue_ids": [
                str(issue.get("issue_id", ""))
                for issue in verifier_trace.get("issues", [])
                if issue.get("issue_id")
            ],
            "route_hint": dict(route_hint) if isinstance(route_hint, Mapping) else None,
            "verifier_may_emit_final_language": False,
            "reranker_may_emit_final_language": False,
            "final_language_owner": "generation_spine_or_cgpu_critic",
            "selected_text": None,
        }
        if not isinstance(route_hint, Mapping) or not route_hint.get("required"):
            base_trace["reason"] = "no_revision_requested"
            return base_trace

        budget = verifier_trace.get("budget", {})
        if budget.get("revision_budget_exhausted") or decision.budget.critic_passes <= 0:
            base_trace["reason"] = "revision_budget_exhausted"
            return base_trace

        context_chunks = self._split_grounding_context(rag_context)
        if not context_chunks:
            base_trace["reason"] = "no_grounding_context_for_bounded_revision"
            return base_trace

        try:
            try:
                from reasoning.generation import CGPUFrame, CGPURenderer, ResponsePlan
            except ModuleNotFoundError:  # pragma: no cover
                from packages.reasoning.generation import CGPUFrame, CGPURenderer, ResponsePlan

            issue_suggestions = [
                str(issue.get("suggestion", "")).strip()
                for issue in verifier_trace.get("issues", [])
                if str(issue.get("suggestion", "")).strip()
            ]
            plan = ResponsePlan(
                intent="revise",
                style="direct",
                safety_level=0.4,
                target_length=min(96, max(32, len(response.split()) + 24)),
                key_points=context_chunks[: max(1, min(3, decision.budget.retrieval_depth))],
                required_phrases=[],
                forbidden_phrases=[],
                domain="business" if runtime_preset == "business_bot" else "general",
            )
            frame = CGPUFrame.create(
                query=query,
                plan=plan,
                trace_id=trace_id,
                grounded_state={"facts": context_chunks},
                mode="business_bot" if runtime_preset == "business_bot" else "general",
                candidate_count=max(1, decision.budget.candidate_count),
                critic_passes=max(1, decision.budget.critic_passes),
                constraints=[
                    *decision.constraints,
                    "verifier_revision_hint_consumed",
                    "verifier_may_emit_final_language:false",
                    "reranker_may_emit_final_language:false",
                ],
                provenance=[
                    {
                        "source": "hypervisor.effective_rag_context",
                        "chunk_index": index,
                    }
                    for index, _chunk in enumerate(context_chunks)
                ],
            )
            output = CGPURenderer().render(frame)
        except Exception as exc:
            base_trace.update(
                {
                    "status": "fault",
                    "reason": "cgpu_revision_fault",
                    "error": str(exc),
                }
            )
            return base_trace

        selected_text = output.selected_text
        if not selected_text:
            base_trace.update(
                {
                    "status": "blocked",
                    "reason": "no_revision_candidate_passed_critic",
                    "cgpu_output": output.to_dict(),
                    "issue_suggestions": issue_suggestions,
                }
            )
            return base_trace

        base_trace.update(
            {
                "status": "revised",
                "reason": "revision_route_hint_consumed",
                "selected_text": selected_text,
                "selected_candidate_id": output.selected_candidate_id,
                "candidate_count": len(output.candidates),
                "critic_passes_used": output.cost.get("critic_passes"),
                "cgpu_output": output.to_dict(),
                "issue_suggestions": issue_suggestions,
                "final_language_owner": "cgpu_critic_arbitration",
            }
        )
        return base_trace

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
        *,
        decision: HypervisorDecision,
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
        degraded_state = self._device_degraded_state(
            guarded=guarded,
            decision=decision,
        )
        return {
            "response": degraded_state["message"],
            "hemisphere_used": "degraded",
            "latency_ms": guarded.latency_ms,
            "device_status": guarded.status,
            "error": guarded.error,
            "degraded_state": degraded_state,
        }

    def _device_degraded_state(
        self,
        *,
        guarded: DeviceExecutionResult,
        decision: HypervisorDecision,
    ) -> dict[str, Any]:
        reason = "budget_exhausted" if guarded.status == "timeout" else "device_fault"
        message = (
            "The CHAL route could not complete within the current cognitive budget, "
            "so Synthesus held the response in an explicit degraded state."
            if reason == "budget_exhausted"
            else
            "The CHAL route hit a cognitive device fault, so Synthesus held the response "
            "in an explicit degraded state."
        )
        return {
            "schema": "synthesus.chal.degraded_state.v1",
            "trace_id": decision.trace_id,
            "reason": reason,
            "route": decision.route.value,
            "device": "chal://hypervisor/hemisphere_bridge",
            "device_status": guarded.status,
            "budget_exhausted": guarded.status == "timeout",
            "normal_assistant_path": False,
            "legacy_template_leakage_allowed": False,
            "message": message,
            "error": guarded.error,
        }

    def _template_quarantine_degraded_state(
        self,
        *,
        decision: HypervisorDecision,
        template_guard_result: Any,
    ) -> dict[str, Any]:
        return {
            "schema": "synthesus.chal.degraded_state.v1",
            "trace_id": decision.trace_id,
            "reason": "legacy_template_quarantine",
            "route": decision.route.value,
            "device": "chal://critic/template_guard",
            "device_status": "quarantined",
            "budget_exhausted": False,
            "normal_assistant_path": False,
            "legacy_template_leakage_allowed": False,
            "message": template_guard_result.text,
            "matched_signatures": list(template_guard_result.matched_signatures),
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
