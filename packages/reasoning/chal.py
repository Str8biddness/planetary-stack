"""CHAL reasoning contracts for bounded cognitive firmware.

These records are deliberately small and JSON-shaped. PPBRS and retrieval code
can emit them without owning final wording; the generation spine can consume the
same payloads as bounded inputs for realization, critique, telemetry, and replay.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


def _trace_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class CognitiveTask:
    """A schedulable CHAL reasoning workload."""

    task_id: str
    query: str
    character_id: str = ""
    domain: str = "general"
    intent: str = "inform"
    budgets: dict[str, float] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    trace_id: str = field(default_factory=lambda: _trace_id("task"))
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_query(
        cls,
        query: str,
        *,
        character_id: str = "",
        domain: str = "general",
        intent: str = "inform",
        budgets: dict[str, float] | None = None,
        constraints: list[str] | None = None,
        trace_id: str | None = None,
    ) -> "CognitiveTask":
        return cls(
            task_id=_trace_id("task"),
            query=query,
            character_id=character_id,
            domain=domain,
            intent=intent,
            budgets=dict(budgets or {}),
            constraints=list(constraints or []),
            trace_id=trace_id or _trace_id("trace"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionPlan:
    """A bounded plan emitted before module execution."""

    plan_id: str
    task_id: str
    stages: list[str]
    route: str
    budgets: dict[str, float] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModuleMessage:
    """Typed message passed across CHAL cognitive fabric."""

    message_id: str
    trace_id: str
    source: str
    target: str
    kind: str
    payload: dict[str, Any]
    confidence: float = 0.0
    constraints: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Checkpoint:
    """Replayable reasoning checkpoint."""

    checkpoint_id: str
    trace_id: str
    stage: str
    state: dict[str, Any]
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TelemetryRecord:
    """Latency, confidence, and routing metadata for CHAL inspection."""

    trace_id: str
    component: str
    latency_ms: float = 0.0
    confidence: float = 0.0
    cache_hit: bool = False
    fallback_used: bool = False
    template_leakage_risk: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_ppbrs_firmware_signal(
    *,
    query: str,
    module_used: str,
    confidence: float,
    character_id: str = "",
    source: str = "ppbrs",
    matched_pattern: str = "",
    rag_context: str = "",
    latency_ms: float = 0.0,
    fallback_used: bool = False,
) -> dict[str, Any]:
    """Create a left-hemisphere firmware signal from PPBRS routing output."""

    constraints = [
        "generation_spine_owns_final_wording",
        "do_not_emit_ppbrs_template",
        "preserve_safety_policy_responses",
    ]
    if rag_context:
        constraints.append("ground_surface_text_in_rag_context")

    task = CognitiveTask.from_query(
        query,
        character_id=character_id,
        constraints=constraints,
        budgets={"latency_ms": max(latency_ms, 0.0), "confidence_floor": 0.3},
    )
    plan = ExecutionPlan(
        plan_id=_trace_id("plan"),
        task_id=task.task_id,
        stages=["classify", "route", "constrain", "handoff_to_generation"],
        route=module_used or "unrouted",
        budgets=dict(task.budgets),
        constraints=list(constraints),
        trace_id=task.trace_id,
    )
    message = ModuleMessage(
        message_id=_trace_id("msg"),
        trace_id=task.trace_id,
        source=source,
        target="generation_spine",
        kind="left_hemisphere_firmware_signal",
        payload={
            "query": query,
            "module_used": module_used,
            "matched_pattern": matched_pattern,
            "rag_context_present": bool(rag_context),
        },
        confidence=max(0.0, min(1.0, confidence)),
        constraints=list(constraints),
    )
    checkpoint = Checkpoint(
        checkpoint_id=_trace_id("ckpt"),
        trace_id=task.trace_id,
        stage="ppbrs_route",
        state={
            "module_used": module_used,
            "matched_pattern": matched_pattern,
            "confidence": max(0.0, min(1.0, confidence)),
            "fallback_used": fallback_used,
        },
    )
    telemetry = TelemetryRecord(
        trace_id=task.trace_id,
        component=source,
        latency_ms=latency_ms,
        confidence=max(0.0, min(1.0, confidence)),
        fallback_used=fallback_used,
        template_leakage_risk=0.0,
        metadata={"module_used": module_used, "matched_pattern": matched_pattern},
    )

    return {
        "schema": "synthesus.chal.reasoning_firmware.v1",
        "task": task.to_dict(),
        "execution_plan": plan.to_dict(),
        "module_message": message.to_dict(),
        "checkpoint": checkpoint.to_dict(),
        "telemetry": telemetry.to_dict(),
        "confidence": max(0.0, min(1.0, confidence)),
        "constraints": list(constraints),
        "trace_id": task.trace_id,
    }
