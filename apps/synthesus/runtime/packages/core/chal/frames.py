"""Canonical CHAL frame contracts for bounded cognitive firmware.

These records are JSON-shaped and deliberately module-neutral. Reasoning,
knowledge, core, and future CHAL devices should exchange these frames instead
of defining local copies of task, plan, message, checkpoint, telemetry, or
firmware-signal records.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from typing import Any


def make_trace_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def require_mapping(data: dict[str, Any], record_name: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise TypeError(f"{record_name} payload must be a mapping")
    return data


def coerce_dataclass(cls: type, data: dict[str, Any]) -> Any:
    payload = require_mapping(data, cls.__name__)
    allowed = {item.name for item in fields(cls)}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{cls.__name__} payload has unknown fields: {', '.join(unknown)}")
    return cls(**{name: payload[name] for name in allowed if name in payload})


@dataclass(frozen=True)
class CognitiveFrameTask:
    """A schedulable CHAL reasoning workload."""

    task_id: str
    query: str
    character_id: str = ""
    domain: str = "general"
    intent: str = "inform"
    budgets: dict[str, float] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    trace_id: str = field(default_factory=lambda: make_trace_id("task"))
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
    ) -> "CognitiveFrameTask":
        return cls(
            task_id=make_trace_id("task"),
            query=query,
            character_id=character_id,
            domain=domain,
            intent=intent,
            budgets=dict(budgets or {}),
            constraints=list(constraints or []),
            trace_id=trace_id or make_trace_id("trace"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CognitiveFrameTask":
        return coerce_dataclass(cls, data)


@dataclass(frozen=True)
class CognitiveFrameExecutionPlan:
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CognitiveFrameExecutionPlan":
        return coerce_dataclass(cls, data)


@dataclass(frozen=True)
class CognitiveFrameMessage:
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CognitiveFrameMessage":
        return coerce_dataclass(cls, data)


@dataclass(frozen=True)
class CognitiveFrameCheckpoint:
    """Replayable reasoning checkpoint."""

    checkpoint_id: str
    trace_id: str
    stage: str
    state: dict[str, Any]
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CognitiveFrameCheckpoint":
        return coerce_dataclass(cls, data)


@dataclass(frozen=True)
class CognitiveFrameTelemetry:
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CognitiveFrameTelemetry":
        return coerce_dataclass(cls, data)


@dataclass(frozen=True)
class PPBRSFirmwareSignal:
    """Parsed CHAL firmware signal emitted by PPBRS."""

    task: CognitiveFrameTask
    execution_plan: CognitiveFrameExecutionPlan
    module_message: CognitiveFrameMessage
    checkpoint: CognitiveFrameCheckpoint
    telemetry: CognitiveFrameTelemetry
    confidence: float
    constraints: list[str]
    trace_id: str
    schema: str = "synthesus.chal.reasoning_firmware.v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "task": self.task.to_dict(),
            "execution_plan": self.execution_plan.to_dict(),
            "module_message": self.module_message.to_dict(),
            "checkpoint": self.checkpoint.to_dict(),
            "telemetry": self.telemetry.to_dict(),
            "confidence": self.confidence,
            "constraints": list(self.constraints),
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PPBRSFirmwareSignal":
        payload = require_mapping(data, cls.__name__)
        schema = payload.get("schema")
        if schema != "synthesus.chal.reasoning_firmware.v1":
            raise ValueError(f"unsupported PPBRS firmware schema: {schema!r}")

        task = CognitiveFrameTask.from_dict(payload["task"])
        trace_id_value = str(payload["trace_id"])
        nested_trace_ids = {
            task.trace_id,
            str(payload["execution_plan"].get("trace_id")),
            str(payload["module_message"].get("trace_id")),
            str(payload["checkpoint"].get("trace_id")),
            str(payload["telemetry"].get("trace_id")),
        }
        if nested_trace_ids != {trace_id_value}:
            raise ValueError("PPBRS firmware signal trace IDs must match")

        return cls(
            schema=schema,
            task=task,
            execution_plan=CognitiveFrameExecutionPlan.from_dict(payload["execution_plan"]),
            module_message=CognitiveFrameMessage.from_dict(payload["module_message"]),
            checkpoint=CognitiveFrameCheckpoint.from_dict(payload["checkpoint"]),
            telemetry=CognitiveFrameTelemetry.from_dict(payload["telemetry"]),
            confidence=max(0.0, min(1.0, float(payload["confidence"]))),
            constraints=list(payload.get("constraints", [])),
            trace_id=trace_id_value,
        )


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

    task = CognitiveFrameTask.from_query(
        query,
        character_id=character_id,
        constraints=constraints,
        budgets={"latency_ms": max(latency_ms, 0.0), "confidence_floor": 0.3},
    )
    plan = CognitiveFrameExecutionPlan(
        plan_id=make_trace_id("plan"),
        task_id=task.task_id,
        stages=["classify", "route", "constrain", "handoff_to_generation"],
        route=module_used or "unrouted",
        budgets=dict(task.budgets),
        constraints=list(constraints),
        trace_id=task.trace_id,
    )
    message = CognitiveFrameMessage(
        message_id=make_trace_id("msg"),
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
    checkpoint = CognitiveFrameCheckpoint(
        checkpoint_id=make_trace_id("ckpt"),
        trace_id=task.trace_id,
        stage="ppbrs_route",
        state={
            "module_used": module_used,
            "matched_pattern": matched_pattern,
            "confidence": max(0.0, min(1.0, confidence)),
            "fallback_used": fallback_used,
        },
    )
    telemetry = CognitiveFrameTelemetry(
        trace_id=task.trace_id,
        component=source,
        latency_ms=latency_ms,
        confidence=max(0.0, min(1.0, confidence)),
        fallback_used=fallback_used,
        template_leakage_risk=0.0,
        metadata={"module_used": module_used, "matched_pattern": matched_pattern},
    )

    return PPBRSFirmwareSignal(
        task=task,
        execution_plan=plan,
        module_message=message,
        checkpoint=checkpoint,
        telemetry=telemetry,
        confidence=max(0.0, min(1.0, confidence)),
        constraints=list(constraints),
        trace_id=task.trace_id,
    ).to_dict()


CognitiveTask = CognitiveFrameTask
ExecutionPlan = CognitiveFrameExecutionPlan
ModuleMessage = CognitiveFrameMessage
Checkpoint = CognitiveFrameCheckpoint
TelemetryRecord = CognitiveFrameTelemetry


__all__ = [
    "Checkpoint",
    "CognitiveFrameCheckpoint",
    "CognitiveFrameExecutionPlan",
    "CognitiveFrameMessage",
    "CognitiveFrameTask",
    "CognitiveFrameTelemetry",
    "CognitiveTask",
    "ExecutionPlan",
    "ModuleMessage",
    "PPBRSFirmwareSignal",
    "TelemetryRecord",
    "build_ppbrs_firmware_signal",
    "coerce_dataclass",
    "require_mapping",
    "make_trace_id",
]
