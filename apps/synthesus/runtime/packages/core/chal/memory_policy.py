"""CHAL memory/cache tier policy and writeback admission contracts."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class MemoryTier(str, Enum):
    L1_TURN_CACHE = "L1_TURN_CACHE"
    L2_SESSION_CACHE = "L2_SESSION_CACHE"
    L3_PROJECT_USER_CACHE = "L3_PROJECT_USER_CACHE"
    L4_KNOWLEDGE_CLOUD_CACHE = "L4_KNOWLEDGE_CLOUD_CACHE"


@dataclass(frozen=True)
class MemoryTierPolicy:
    tier: MemoryTier
    mount_path: str
    ttl_seconds: int | None
    provenance_required: bool
    writable: bool
    source_controlled: bool = False
    description: str = ""

    @property
    def expires(self) -> bool:
        return self.ttl_seconds is not None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tier"] = self.tier.value
        return payload


@dataclass(frozen=True)
class MemoryProvenanceRef:
    ref: str
    source: str
    trace_id: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.ref:
            raise ValueError("memory provenance ref is required")
        if not self.source:
            raise ValueError("memory provenance source is required")
        if not self.trace_id:
            raise ValueError("memory provenance trace_id is required")
        object.__setattr__(self, "confidence", max(0.0, min(1.0, float(self.confidence))))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryWritebackCandidate:
    trace_id: str
    target_memory_type: str
    content: str
    critic_accepted: bool
    provenance: tuple[MemoryProvenanceRef, ...]
    importance: float = 0.5
    ttl_seconds: int | None = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.target_memory_type not in {"episodic", "semantic", "procedural", "working", "crystallized"}:
            raise ValueError(f"unsupported memory writeback target: {self.target_memory_type}")
        if not self.trace_id:
            raise ValueError("memory writeback trace_id is required")
        if not self.content.strip():
            raise ValueError("memory writeback content is required")
        object.__setattr__(self, "importance", max(0.0, min(1.0, float(self.importance))))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["provenance"] = [item.to_dict() for item in self.provenance]
        return payload


@dataclass(frozen=True)
class MemoryWritebackDecision:
    accepted: bool
    reason: str
    target_mount: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_MEMORY_TIER_POLICIES: dict[MemoryTier, MemoryTierPolicy] = {
    MemoryTier.L1_TURN_CACHE: MemoryTierPolicy(
        tier=MemoryTier.L1_TURN_CACHE,
        mount_path="/mnt/cache/turn",
        ttl_seconds=15 * 60,
        provenance_required=False,
        writable=True,
        description="volatile current-turn reasoning and retrieval scratch",
    ),
    MemoryTier.L2_SESSION_CACHE: MemoryTierPolicy(
        tier=MemoryTier.L2_SESSION_CACHE,
        mount_path="/mnt/cache/session",
        ttl_seconds=6 * 60 * 60,
        provenance_required=True,
        writable=True,
        description="volatile session-local facts, summaries, and hot retrievals",
    ),
    MemoryTier.L3_PROJECT_USER_CACHE: MemoryTierPolicy(
        tier=MemoryTier.L3_PROJECT_USER_CACHE,
        mount_path="/mnt/cache/project_user",
        ttl_seconds=30 * 24 * 60 * 60,
        provenance_required=True,
        writable=True,
        description="durable project/user cache requiring traceable provenance",
    ),
    MemoryTier.L4_KNOWLEDGE_CLOUD_CACHE: MemoryTierPolicy(
        tier=MemoryTier.L4_KNOWLEDGE_CLOUD_CACHE,
        mount_path="/mnt/cache/hot_context",
        ttl_seconds=None,
        provenance_required=True,
        writable=False,
        description="manifest-backed Knowledge Cloud hot-context cache seed boundary",
    ),
}


def get_memory_tier_policy(tier: MemoryTier | str) -> MemoryTierPolicy:
    key = tier if isinstance(tier, MemoryTier) else MemoryTier(str(tier))
    return DEFAULT_MEMORY_TIER_POLICIES[key]


def memory_tier_policy_manifest() -> dict[str, dict[str, Any]]:
    return {tier.value: policy.to_dict() for tier, policy in DEFAULT_MEMORY_TIER_POLICIES.items()}


def decide_memory_writeback(candidate: MemoryWritebackCandidate) -> MemoryWritebackDecision:
    if not candidate.critic_accepted:
        return MemoryWritebackDecision(
            accepted=False,
            reason="critic_rejected",
            target_mount="/mnt/mem/writeback",
            metadata={"trace_id": candidate.trace_id},
        )
    if not candidate.provenance:
        return MemoryWritebackDecision(
            accepted=False,
            reason="missing_provenance",
            target_mount="/mnt/mem/writeback",
            metadata={"trace_id": candidate.trace_id},
        )

    low_confidence = [item.ref for item in candidate.provenance if item.confidence < 0.5]
    if low_confidence:
        return MemoryWritebackDecision(
            accepted=False,
            reason="low_provenance_confidence",
            target_mount="/mnt/mem/writeback",
            metadata={"trace_id": candidate.trace_id, "low_confidence_refs": low_confidence},
        )

    return MemoryWritebackDecision(
        accepted=True,
        reason="critic_and_provenance_validated",
        target_mount="/mnt/mem/writeback",
        metadata={
            "trace_id": candidate.trace_id,
            "target_memory_type": candidate.target_memory_type,
            "provenance_refs": [item.ref for item in candidate.provenance],
            "ttl_seconds": candidate.ttl_seconds,
            "importance": candidate.importance,
        },
    )


__all__ = [
    "DEFAULT_MEMORY_TIER_POLICIES",
    "MemoryProvenanceRef",
    "MemoryTier",
    "MemoryTierPolicy",
    "MemoryWritebackCandidate",
    "MemoryWritebackDecision",
    "decide_memory_writeback",
    "get_memory_tier_policy",
    "memory_tier_policy_manifest",
]
