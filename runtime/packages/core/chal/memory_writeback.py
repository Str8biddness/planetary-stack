"""Apply admitted CHAL memory writeback candidates to runtime memory sinks.

C-003: crystallization gate — raw LLM generations are never written to long-term
Mc as facts. Grounded+cited answers persist as GROUNDED with provenance_refs.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .memory_policy import (
    MemoryProvenanceRef,
    MemoryWritebackCandidate,
    MemoryWritebackDecision,
    decide_memory_writeback,
)

try:
    from memory_provenance import (
        Provenance,
        Verification,
        annotate_metadata,
        classify,
        gate,
    )
except ImportError:  # package-style import
    from knowledge.memory_provenance import (  # type: ignore
        Provenance,
        Verification,
        annotate_metadata,
        classify,
        gate,
    )

logger = logging.getLogger(__name__)


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


def _chal_refs_to_provenance_refs(candidate: MemoryWritebackCandidate) -> list[str]:
    refs: list[str] = []
    for item in candidate.provenance:
        ref = str(item.ref or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _is_grounded_cited_trace(trace: dict[str, Any] | None, candidate: MemoryWritebackCandidate) -> bool:
    """True only when the candidate is grounded against real external sources.

    A bare trace:// self-ref is NOT grounding — that would let raw generations
    crystallize (anti-collapse failure).
    """
    if isinstance(trace, dict):
        knowledge = trace.get("knowledge_provenance")
        if isinstance(knowledge, dict) and knowledge.get("context_used"):
            mounts = knowledge.get("mounts")
            if isinstance(mounts, list) and any(isinstance(m, dict) for m in mounts):
                return True
            # context_used with an operation/source id still counts as cited grounding
            if knowledge.get("operation_id") or knowledge.get("source"):
                return True

    # Candidate-level: require at least one non-synthetic external ref.
    for item in candidate.provenance:
        ref = str(item.ref or "")
        source = str(item.source or "")
        if ref.startswith("trace://") and source == "cognitive_hypervisor_trace":
            continue
        if ref and not ref.startswith("trace://"):
            return True
        if source and source not in {"cognitive_hypervisor_trace", "llm", "llm_generation"}:
            # knowledge_provenance without mounts still external
            if "knowledge" in source or source.startswith("rom_mount") or source.startswith("user"):
                return True
    return False


def classify_writeback_provenance(
    candidate: MemoryWritebackCandidate,
    *,
    trace: dict[str, Any] | None = None,
    origin_voice: str | None = None,
) -> dict[str, Any]:
    """Classify a writeback candidate into C-001 provenance fields.

    grounded+cited → GROUNDED_CITED / GROUNDED with provenance_refs
    else → LLM_GENERATION / UNVERIFIED (session-only; gate will reject)
    """
    if _is_grounded_cited_trace(trace, candidate):
        prov = Provenance.GROUNDED_CITED
    else:
        prov = Provenance.LLM_GENERATION

    tier = classify(prov)
    item: dict[str, Any] = {}
    annotate_metadata(
        item,
        provenance=prov,
        provenance_refs=_chal_refs_to_provenance_refs(candidate),
        origin_voice=origin_voice,
        created_ts=float(candidate.created_at or time.time()),
        verification=tier,
    )
    return item


def _candidate_metadata(
    candidate: MemoryWritebackCandidate,
    *,
    provenance_fields: dict[str, Any],
) -> dict[str, Any]:
    """Build stored metadata: C-001 fields + CHAL writeback audit trail.

    Note: C-001 uses `provenance` as a str enum value. The prior CHAL list of
    MemoryProvenanceRef dicts is preserved under `chal_provenance` so audit
    detail is not lost, and source ids live in `provenance_refs`.
    """
    return {
        "schema": "synthesus.chal.memory_writeback.v1",
        "trace_id": candidate.trace_id,
        "target_memory_type": candidate.target_memory_type,
        "ttl_seconds": candidate.ttl_seconds,
        "importance": candidate.importance,
        "created_at": candidate.created_at,
        # C-001 fields (authoritative for anti-collapse)
        "provenance": provenance_fields.get("provenance"),
        "verification": provenance_fields.get("verification"),
        "provenance_refs": list(provenance_fields.get("provenance_refs") or []),
        "origin_voice": provenance_fields.get("origin_voice"),
        "created_ts": provenance_fields.get("created_ts"),
        "confirmed_ts": provenance_fields.get("confirmed_ts"),
        "confirmed_by": provenance_fields.get("confirmed_by"),
        # CHAL audit trail (legacy list shape for debugging)
        "chal_provenance": [item.to_dict() for item in candidate.provenance],
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
    trace: dict[str, Any] | None = None,
    origin_voice: str | None = None,
) -> AppliedMemoryWriteback:
    """Apply writeback only if CHAL policy admits AND C-001 gate allows crystallization.

    Raw LLM generations (LLM_GENERATION / UNVERIFIED) are NOT persisted as
    long-term facts. They return a rejected decision with an explicit reason.
    """
    decision = decide_memory_writeback(candidate)
    if not decision.accepted:
        return AppliedMemoryWriteback(
            decision=decision,
            target_memory_type=candidate.target_memory_type,
        )

    provenance_fields = classify_writeback_provenance(
        candidate,
        trace=trace,
        origin_voice=origin_voice,
    )
    may_crystallize, tier = gate(provenance_fields)

    if not may_crystallize:
        # Session-only: do not write to long-term Mc. Degrade loudly.
        logger.info(
            "memory_writeback DEGRADED/session-only: gate rejected provenance=%s tier=%s trace_id=%s",
            provenance_fields.get("provenance"),
            tier.name,
            candidate.trace_id,
        )
        rejected = MemoryWritebackDecision(
            accepted=False,
            reason="gate_rejected_llm_generation_or_unverified",
            target_mount="/mnt/mem/writeback",
            metadata={
                "trace_id": candidate.trace_id,
                "provenance": provenance_fields.get("provenance"),
                "verification": int(tier),
                "session_only": True,
                "anti_collapse": True,
            },
        )
        return AppliedMemoryWriteback(
            decision=rejected,
            target_memory_type=candidate.target_memory_type,
            metadata={
                **provenance_fields,
                "session_only": True,
                "stored": False,
            },
        )

    metadata = _candidate_metadata(candidate, provenance_fields=provenance_fields)
    memory_type = candidate.target_memory_type
    tags = ["chal_writeback", f"trace:{candidate.trace_id}", f"verification:{int(tier)}"]
    conscious_state_updated = False

    if memory_type == "crystallized":
        # Crystallized path still requires gate-pass (already enforced above).
        tags.append("crystallized")
        crystallized = getattr(conscious_state, "crystallized", None) if conscious_state is not None else None
        if crystallized is not None:
            refs = getattr(crystallized, "semantic_knowledge_refs", None)
            if isinstance(refs, list):
                refs.append(f"trace://{candidate.trace_id}")
                for pref in metadata.get("provenance_refs") or []:
                    if pref not in refs:
                        refs.append(pref)
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
            "provenance": metadata.get("provenance"),
            "verification": metadata.get("verification"),
            "provenance_refs": metadata.get("provenance_refs"),
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
        # Synthetic self-ref only — NOT external grounding. Gate will classify
        # this candidate as LLM_GENERATION and refuse long-term crystallization.
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
    "classify_writeback_provenance",
]
