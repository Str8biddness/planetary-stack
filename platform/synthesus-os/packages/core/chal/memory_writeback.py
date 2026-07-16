"""Apply admitted CHAL memory writeback candidates to runtime memory sinks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .memory_policy import (
    MemoryProvenanceRef,
    MemoryWritebackCandidate,
    MemoryWritebackDecision,
    decide_memory_writeback,
)


@dataclass(frozen=True)
class AppliedMemoryWriteback:
    decision: MemoryWritebackDecision
    stored_memory_id: str | None = None
    target_memory_type: str | None = None
    conscious_state_updated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision"] = self.decision.to_dict()
        return payload


def _candidate_metadata(candidate: MemoryWritebackCandidate) -> dict[str, Any]:
    return {
        "schema": "synthesus.chal.memory_writeback.v1",
        "trace_id": candidate.trace_id,
        "target_memory_type": candidate.target_memory_type,
        "ttl_seconds": candidate.ttl_seconds,
        "importance": candidate.importance,
        "created_at": candidate.created_at,
        "provenance": [item.to_dict() for item in candidate.provenance],
    }


def _store_memory(
    memory_store: Any,
    *,
    character_id: str,
    memory_type: str,
    content: str,
    importance: float,
    tags: list[str],
    metadata: dict[str, Any],
) -> Any:
    store_method = getattr(memory_store, f"store_{memory_type}", None)
    if callable(store_method):
        return store_method(
            character_id,
            content,
            importance=importance,
            tags=tags,
            metadata=metadata,
        )
    return memory_store.store(
        character_id,
        content,
        memory_type,
        importance,
        tags,
        metadata,
    )


def _memory_id(stored: Any) -> str | None:
    if stored is None:
        return None
    if isinstance(stored, str):
        return stored
    return getattr(stored, "id", None)


def apply_memory_writeback(
    candidate: MemoryWritebackCandidate,
    *,
    memory_store: Any,
    character_id: str,
    conscious_state: Any | None = None,
) -> AppliedMemoryWriteback:
    decision = decide_memory_writeback(candidate)
    if not decision.accepted:
        return AppliedMemoryWriteback(
            decision=decision,
            target_memory_type=candidate.target_memory_type,
        )

    metadata = _candidate_metadata(candidate)
    memory_type = candidate.target_memory_type
    tags = ["chal_writeback", f"trace:{candidate.trace_id}"]
    conscious_state_updated = False

    if memory_type == "crystallized":
        tags.append("crystallized")
        crystallized = getattr(conscious_state, "crystallized", None)
        if crystallized is not None:
            refs = getattr(crystallized, "semantic_knowledge_refs", None)
            if isinstance(refs, list):
                refs.append(f"trace://{candidate.trace_id}")
            facts = getattr(crystallized, "facts", None)
            if isinstance(facts, dict):
                facts[candidate.content] = True
            conscious_state_updated = True
        memory_type = "semantic"
        metadata["crystallized_staging"] = True

    stored = _store_memory(
        memory_store,
        character_id=character_id,
        memory_type=memory_type,
        content=candidate.content,
        importance=candidate.importance,
        tags=tags,
        metadata=metadata,
    )
    stored_id = _memory_id(stored)
    enriched_decision = MemoryWritebackDecision(
        accepted=True,
        reason=decision.reason,
        target_mount=decision.target_mount,
        metadata={
            **decision.metadata,
            "character_id": character_id,
            "stored_memory_id": stored_id,
            "stored_memory_type": memory_type,
            "conscious_state_updated": conscious_state_updated,
        },
    )
    return AppliedMemoryWriteback(
        decision=enriched_decision,
        stored_memory_id=stored_id,
        target_memory_type=candidate.target_memory_type,
        conscious_state_updated=conscious_state_updated,
        metadata=metadata,
    )


def candidate_from_hypervisor_trace(
    *,
    trace: dict[str, Any],
    content: str,
    target_memory_type: str = "episodic",
    importance: float = 0.5,
    ttl_seconds: int | None = None,
) -> MemoryWritebackCandidate:
    trace_id = str(trace.get("trace_id") or "")
    template_guard = trace.get("template_guard") if isinstance(trace.get("template_guard"), dict) else {}
    degraded = bool(trace.get("degraded"))
    critic_accepted = not degraded and not bool(template_guard.get("rewritten"))
    provenance = _provenance_from_trace(trace, trace_id)

    return MemoryWritebackCandidate(
        trace_id=trace_id,
        target_memory_type=target_memory_type,
        content=content,
        critic_accepted=critic_accepted,
        provenance=tuple(provenance),
        importance=importance,
        ttl_seconds=ttl_seconds,
    )


def _provenance_from_trace(trace: dict[str, Any], trace_id: str) -> list[MemoryProvenanceRef]:
    refs: list[MemoryProvenanceRef] = []
    knowledge = trace.get("knowledge_provenance")
    if isinstance(knowledge, dict) and knowledge.get("context_used"):
        mounts = knowledge.get("mounts")
        if isinstance(mounts, list) and mounts:
            for index, mount in enumerate(mounts):
                if not isinstance(mount, dict):
                    continue
                refs.append(
                    MemoryProvenanceRef(
                        ref=str(mount.get("mount_path") or f"chal://knowledge/{index}"),
                        source=str(knowledge.get("source") or "knowledge_provenance"),
                        trace_id=trace_id,
                        confidence=float(knowledge.get("confidence", 1.0)),
                        metadata={"mount": mount},
                    )
                )
        else:
            refs.append(
                MemoryProvenanceRef(
                    ref=str(knowledge.get("operation_id") or "chal://knowledge/provided_context"),
                    source=str(knowledge.get("source") or "knowledge_provenance"),
                    trace_id=trace_id,
                    confidence=float(knowledge.get("confidence", 1.0)),
                    metadata={k: v for k, v in knowledge.items() if k != "mounts"},
                )
            )

    if not refs and trace_id:
        refs.append(
            MemoryProvenanceRef(
                ref=f"trace://{trace_id}",
                source="cognitive_hypervisor_trace",
                trace_id=trace_id,
                confidence=0.75,
                metadata={
                    "route": trace.get("route"),
                    "hemisphere_mode": trace.get("hemisphere_mode"),
                },
            )
        )
    return refs


__all__ = [
    "AppliedMemoryWriteback",
    "apply_memory_writeback",
    "candidate_from_hypervisor_trace",
]
