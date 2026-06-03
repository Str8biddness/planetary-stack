from __future__ import annotations

import pytest

from core.chal.memory_policy import (
    DEFAULT_MEMORY_TIER_POLICIES,
    MemoryProvenanceRef,
    MemoryTier,
    MemoryWritebackCandidate,
    decide_memory_writeback,
    get_memory_tier_policy,
    memory_tier_policy_manifest,
)
from core.chal.memory_writeback import apply_memory_writeback, candidate_from_hypervisor_trace
from core.conscious_state import ConsciousState


class FakeMemoryStore:
    def __init__(self) -> None:
        self.records = []

    def store(self, character_id, content, memory_type="episodic", importance=0.5, tags=None, metadata=None):
        record = {
            "id": f"mem-{len(self.records) + 1}",
            "character_id": character_id,
            "content": content,
            "memory_type": memory_type,
            "importance": importance,
            "tags": tags or [],
            "metadata": metadata or {},
        }
        self.records.append(record)
        return type("StoredMemory", (), {"id": record["id"]})()

    def store_episodic(self, character_id, content, importance=0.5, tags=None, metadata=None):
        return self.store(character_id, content, "episodic", importance, tags, metadata)

    def store_semantic(self, character_id, content, importance=0.7, tags=None, metadata=None):
        return self.store(character_id, content, "semantic", importance, tags, metadata)


def test_memory_tier_policy_defines_l1_to_l4_cache_contracts() -> None:
    manifest = memory_tier_policy_manifest()

    assert set(manifest) == {tier.value for tier in MemoryTier}
    assert manifest["L1_TURN_CACHE"]["mount_path"] == "/mnt/cache/turn"
    assert manifest["L1_TURN_CACHE"]["ttl_seconds"] == 900
    assert manifest["L1_TURN_CACHE"]["provenance_required"] is False
    assert manifest["L2_SESSION_CACHE"]["ttl_seconds"] == 21600
    assert manifest["L2_SESSION_CACHE"]["provenance_required"] is True
    assert manifest["L3_PROJECT_USER_CACHE"]["ttl_seconds"] == 2592000
    assert manifest["L3_PROJECT_USER_CACHE"]["provenance_required"] is True
    assert manifest["L4_KNOWLEDGE_CLOUD_CACHE"]["mount_path"] == "/mnt/cache/hot_context"
    assert manifest["L4_KNOWLEDGE_CLOUD_CACHE"]["ttl_seconds"] is None
    assert manifest["L4_KNOWLEDGE_CLOUD_CACHE"]["writable"] is False
    assert all(policy.source_controlled is False for policy in DEFAULT_MEMORY_TIER_POLICIES.values())


def test_get_memory_tier_policy_accepts_string_or_enum() -> None:
    assert get_memory_tier_policy(MemoryTier.L2_SESSION_CACHE).mount_path == "/mnt/cache/session"
    assert get_memory_tier_policy("L3_PROJECT_USER_CACHE").mount_path == "/mnt/cache/project_user"


def test_writeback_requires_critic_acceptance() -> None:
    candidate = MemoryWritebackCandidate(
        trace_id="trace-1",
        target_memory_type="episodic",
        content="User confirmed the project uses CHAL memory policy gates.",
        critic_accepted=False,
        provenance=(
            MemoryProvenanceRef(ref="trace://critic/1", source="critic", trace_id="trace-1"),
        ),
    )

    decision = decide_memory_writeback(candidate)

    assert decision.accepted is False
    assert decision.reason == "critic_rejected"
    assert decision.target_mount == "/mnt/mem/writeback"


def test_writeback_requires_provenance() -> None:
    candidate = MemoryWritebackCandidate(
        trace_id="trace-2",
        target_memory_type="semantic",
        content="Knowledge Cloud cache seed uses manifest-backed provenance.",
        critic_accepted=True,
        provenance=(),
    )

    decision = decide_memory_writeback(candidate)

    assert decision.accepted is False
    assert decision.reason == "missing_provenance"


def test_writeback_accepts_critic_validated_provenance() -> None:
    candidate = MemoryWritebackCandidate(
        trace_id="trace-3",
        target_memory_type="crystallized",
        content="The L4 cache seed is read-only and provenance-required.",
        critic_accepted=True,
        provenance=(
            MemoryProvenanceRef(
                ref="kc://manifests/integrity/faiss_metadata",
                source="knowledge_cloud",
                trace_id="trace-3",
                confidence=0.94,
                metadata={"mount": "/mnt/provenance/faiss_metadata"},
            ),
        ),
        importance=0.8,
        ttl_seconds=None,
    )

    decision = decide_memory_writeback(candidate)

    assert decision.accepted is True
    assert decision.reason == "critic_and_provenance_validated"
    assert decision.metadata["target_memory_type"] == "crystallized"
    assert decision.metadata["provenance_refs"] == ["kc://manifests/integrity/faiss_metadata"]


def test_writeback_rejects_low_confidence_provenance() -> None:
    candidate = MemoryWritebackCandidate(
        trace_id="trace-4",
        target_memory_type="working",
        content="Speculative scratch item",
        critic_accepted=True,
        provenance=(
            MemoryProvenanceRef(ref="trace://weak/1", source="candidate", trace_id="trace-4", confidence=0.49),
        ),
    )

    decision = decide_memory_writeback(candidate)

    assert decision.accepted is False
    assert decision.reason == "low_provenance_confidence"
    assert decision.metadata["low_confidence_refs"] == ["trace://weak/1"]


def test_writeback_candidate_validates_target_type() -> None:
    with pytest.raises(ValueError):
        MemoryWritebackCandidate(
            trace_id="trace-5",
            target_memory_type="unsupported",
            content="invalid",
            critic_accepted=True,
            provenance=(),
        )


def test_apply_memory_writeback_persists_accepted_episodic_candidate() -> None:
    store = FakeMemoryStore()
    candidate = MemoryWritebackCandidate(
        trace_id="trace-6",
        target_memory_type="episodic",
        content="User confirmed CHAL writeback should preserve provenance.",
        critic_accepted=True,
        provenance=(
            MemoryProvenanceRef(ref="trace://critic/6", source="critic", trace_id="trace-6", confidence=0.9),
        ),
        importance=0.65,
    )

    applied = apply_memory_writeback(candidate, memory_store=store, character_id="synth")

    assert applied.decision.accepted is True
    assert applied.stored_memory_id == "mem-1"
    assert store.records[0]["memory_type"] == "episodic"
    assert store.records[0]["metadata"]["schema"] == "synthesus.chal.memory_writeback.v1"
    assert store.records[0]["metadata"]["trace_id"] == "trace-6"
    assert store.records[0]["metadata"]["provenance"][0]["ref"] == "trace://critic/6"
    assert "chal_writeback" in store.records[0]["tags"]


def test_apply_memory_writeback_stages_crystallized_candidate_and_updates_state() -> None:
    store = FakeMemoryStore()
    state = ConsciousState()
    candidate = MemoryWritebackCandidate(
        trace_id="trace-7",
        target_memory_type="crystallized",
        content="CHAL memory writeback requires critic and provenance admission.",
        critic_accepted=True,
        provenance=(
            MemoryProvenanceRef(ref="kc://policy/writeback", source="knowledge_cloud", trace_id="trace-7"),
        ),
        importance=0.9,
    )

    applied = apply_memory_writeback(
        candidate,
        memory_store=store,
        character_id="synth",
        conscious_state=state,
    )

    assert applied.decision.accepted is True
    assert applied.target_memory_type == "crystallized"
    assert applied.conscious_state_updated is True
    assert store.records[0]["memory_type"] == "semantic"
    assert store.records[0]["metadata"]["crystallized_staging"] is True
    assert "crystallized" in store.records[0]["tags"]
    assert "trace://trace-7" in state.crystallized.semantic_knowledge_refs
    assert state.crystallized.facts["CHAL memory writeback requires critic and provenance admission."] is True


def test_candidate_from_hypervisor_trace_uses_knowledge_provenance_and_template_guard() -> None:
    trace = {
        "trace_id": "hv-123",
        "route": "grounded_path",
        "hemisphere_mode": "auto",
        "degraded": False,
        "template_guard": {"rewritten": False},
        "knowledge_provenance": {
            "context_used": True,
            "source": "rom_mount:world_lore",
            "confidence": 0.91,
            "mounts": [{"mount_path": "/mnt/rom/world_lore", "partition_id": "world_lore"}],
        },
    }

    candidate = candidate_from_hypervisor_trace(
        trace=trace,
        content="The world lore mount supplied the response grounding.",
        target_memory_type="semantic",
    )

    assert candidate.trace_id == "hv-123"
    assert candidate.critic_accepted is True
    assert candidate.provenance[0].ref == "/mnt/rom/world_lore"
    assert candidate.provenance[0].source == "rom_mount:world_lore"


def test_candidate_from_hypervisor_trace_rejects_degraded_or_rewritten_trace() -> None:
    trace = {
        "trace_id": "hv-456",
        "route": "fast_path",
        "hemisphere_mode": "auto",
        "degraded": True,
        "template_guard": {"rewritten": True},
    }

    candidate = candidate_from_hypervisor_trace(
        trace=trace,
        content="Do not write quarantined output.",
        target_memory_type="episodic",
    )
    decision = decide_memory_writeback(candidate)

    assert candidate.critic_accepted is False
    assert decision.accepted is False
    assert decision.reason == "critic_rejected"
