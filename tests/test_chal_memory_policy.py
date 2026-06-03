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
