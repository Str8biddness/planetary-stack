"""C-006 — Adversarial tests for provenance + verification-tagged memory (anti-collapse).

Proves:
  (a) no path promotes LLM_GENERATION → VERIFIED without an external event
  (b) generation never persisted as long-term fact
  (c) retrieval weighting (VERIFIED out-ranks UNVERIFIED at equal similarity)
  (d) feedback upgrade requires a real external event
  (e) legacy metadata without provenance fields still loads
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
for _path in (
    ROOT / "packages" / "knowledge",
    ROOT / "packages" / "core",
    ROOT / "packages",
    ROOT,
):
    _value = str(_path)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from memory_provenance import (  # noqa: E402
    Provenance,
    VERIFICATION_WEIGHT,
    Verification,
    annotate_metadata,
    classify,
    gate,
    resolve_legacy_metadata,
    weight_for,
)
from feedback_verification import upgrade_from_feedback, assert_no_self_promotion  # noqa: E402
from core.chal.memory_policy import MemoryProvenanceRef, MemoryWritebackCandidate  # noqa: E402
from core.chal.memory_writeback import (  # noqa: E402
    apply_memory_writeback,
    candidate_from_hypervisor_trace,
    classify_writeback_provenance,
)


# ─── C-001 contract ───────────────────────────────────────────────────

def test_c001_classify_mapping() -> None:
    assert classify(Provenance.USER_DOCUMENT) is Verification.VERIFIED
    assert classify(Provenance.USER_STATED) is Verification.VERIFIED
    assert classify(Provenance.USER_CONFIRMED) is Verification.VERIFIED
    assert classify(Provenance.GROUNDED_CITED) is Verification.GROUNDED
    assert classify(Provenance.LLM_GENERATION) is Verification.UNVERIFIED
    assert classify("llm_generation") is Verification.UNVERIFIED


def test_c001_gate_rejects_llm_generation_even_if_tier_forged() -> None:
    """Adversarial: caller tries to forge verification=VERIFIED on a generation."""
    ok, tier = gate({"provenance": "llm_generation", "verification": int(Verification.VERIFIED)})
    assert ok is False
    assert tier is Verification.UNVERIFIED

    ok2, tier2 = gate({"provenance": Provenance.LLM_GENERATION, "verification": 2})
    assert ok2 is False and tier2 is Verification.UNVERIFIED


def test_c001_gate_admits_verified_and_grounded() -> None:
    assert gate({"provenance": "user_document"}) == (True, Verification.VERIFIED)
    assert gate({"provenance": "user_stated"}) == (True, Verification.VERIFIED)
    assert gate({"provenance": "user_confirmed"}) == (True, Verification.VERIFIED)
    assert gate({"provenance": "grounded_cited"}) == (True, Verification.GROUNDED)


# ─── (a) No path: LLM_GENERATION → VERIFIED without external event ───

def test_a_annotate_cannot_self_promote_llm_generation() -> None:
    meta: dict = {}
    annotate_metadata(meta, provenance=Provenance.LLM_GENERATION, verification=Verification.VERIFIED)
    assert meta["provenance"] == Provenance.LLM_GENERATION.value
    assert meta["verification"] == int(Verification.UNVERIFIED)
    assert gate(meta) == (False, Verification.UNVERIFIED)


def test_a_classify_never_maps_generation_to_verified() -> None:
    assert classify(Provenance.LLM_GENERATION) is not Verification.VERIFIED
    assert classify(Provenance.LLM_GENERATION) is Verification.UNVERIFIED


def test_a_feedback_self_trigger_refused() -> None:
    item = {
        "id": "m1",
        "content": "A raw guess",
        "provenance": Provenance.LLM_GENERATION.value,
        "verification": int(Verification.UNVERIFIED),
    }
    result = upgrade_from_feedback(
        {"self_triggered": True, "rating": 5, "response": "A raw guess", "memory_id": "m1"},
        items=[item],
    )
    assert result["upgraded"] is False
    assert item["verification"] == int(Verification.UNVERIFIED)
    assert item["provenance"] == Provenance.LLM_GENERATION.value


def test_a_feedback_model_origin_refused() -> None:
    item = {
        "id": "m2",
        "content": "Model tries to confirm itself",
        "provenance": Provenance.LLM_GENERATION.value,
        "verification": int(Verification.UNVERIFIED),
    }
    result = upgrade_from_feedback(
        {"origin": "llm", "action": "confirm", "response": "Model tries to confirm itself", "memory_id": "m2"},
        items=[item],
    )
    assert result["upgraded"] is False
    assert assert_no_self_promotion(item)


def test_a_no_direct_verification_write_bypasses_gate() -> None:
    """Even if a caller stuffs verification=2 into an LLM item, gate still blocks."""
    forged = {"provenance": "llm_generation", "verification": 2, "content": "forged"}
    may, tier = gate(forged)
    assert may is False
    assert tier is Verification.UNVERIFIED
    # weight stays at unverified level when resolved
    assert weight_for(forged) == VERIFICATION_WEIGHT[Verification.UNVERIFIED]


# ─── (b) Generation never persisted as long-term fact ────────────────

class _FakeStore:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def store_episodic(self, character_id, content, importance=0.5, tags=None, metadata=None):
        rec = {
            "id": f"mem-{len(self.records) + 1}",
            "character_id": character_id,
            "content": content,
            "memory_type": "episodic",
            "importance": importance,
            "tags": tags or [],
            "metadata": metadata or {},
        }
        self.records.append(rec)
        return type("Stored", (), {"id": rec["id"]})()

    def store(self, character_id, content, memory_type="episodic", importance=0.5, tags=None, metadata=None):
        rec = {
            "id": f"mem-{len(self.records) + 1}",
            "character_id": character_id,
            "content": content,
            "memory_type": memory_type,
            "importance": importance,
            "tags": tags or [],
            "metadata": metadata or {},
        }
        self.records.append(rec)
        return type("Stored", (), {"id": rec["id"]})()


def test_b_ungrounded_writeback_not_persisted() -> None:
    store = _FakeStore()
    trace = {
        "trace_id": "gen-1",
        "degraded": False,
        "template_guard": {"rewritten": False},
        # no knowledge_provenance → raw generation
    }
    candidate = candidate_from_hypervisor_trace(
        trace=trace,
        content="User: hi\nAssistant: I invented this fact about your repo.",
        target_memory_type="episodic",
    )
    applied = apply_memory_writeback(
        candidate, memory_store=store, character_id="synth", trace=trace
    )
    assert applied.decision.accepted is False
    assert "gate_rejected" in applied.decision.reason
    assert store.records == []


def test_b_grounded_writeback_persists_with_refs() -> None:
    store = _FakeStore()
    trace = {
        "trace_id": "gnd-1",
        "degraded": False,
        "template_guard": {"rewritten": False},
        "knowledge_provenance": {
            "context_used": True,
            "source": "rom_mount:docs",
            "confidence": 0.95,
            "mounts": [{"mount_path": "/mnt/user/docs/readme.md"}],
        },
    }
    candidate = candidate_from_hypervisor_trace(
        trace=trace,
        content="User: what?\nAssistant: From your readme: the API uses key auth.",
        target_memory_type="episodic",
    )
    fields = classify_writeback_provenance(candidate, trace=trace)
    assert fields["provenance"] == Provenance.GROUNDED_CITED.value
    assert fields["verification"] == int(Verification.GROUNDED)

    applied = apply_memory_writeback(
        candidate, memory_store=store, character_id="synth", trace=trace
    )
    assert applied.decision.accepted is True
    assert len(store.records) == 1
    meta = store.records[0]["metadata"]
    assert meta["provenance"] == "grounded_cited"
    assert meta["verification"] == int(Verification.GROUNDED)
    assert "/mnt/user/docs/readme.md" in meta["provenance_refs"]


def test_b_crystallized_target_still_gated() -> None:
    """Adversarial: target_memory_type=crystallized cannot launder a generation."""
    store = _FakeStore()
    candidate = MemoryWritebackCandidate(
        trace_id="cryst-attack",
        target_memory_type="crystallized",
        content="Launder me into Mc",
        critic_accepted=True,
        provenance=(
            MemoryProvenanceRef(
                ref="trace://cryst-attack",
                source="cognitive_hypervisor_trace",
                trace_id="cryst-attack",
                confidence=0.99,
            ),
        ),
        importance=1.0,
    )
    applied = apply_memory_writeback(candidate, memory_store=store, character_id="synth")
    assert applied.decision.accepted is False
    assert store.records == []


# ─── (c) Retrieval weighting ─────────────────────────────────────────

def test_c_verification_weights_order() -> None:
    assert (
        VERIFICATION_WEIGHT[Verification.VERIFIED]
        > VERIFICATION_WEIGHT[Verification.GROUNDED]
        > VERIFICATION_WEIGHT[Verification.UNVERIFIED]
    )


def test_c_equal_similarity_verified_outranks_unverified() -> None:
    """At equal raw similarity, weighted score: VERIFIED > UNVERIFIED."""
    sim = 0.9
    verified_score = sim * weight_for({"provenance": "user_document", "verification": 2})
    unverified_score = sim * weight_for({"provenance": "llm_generation", "verification": 0})
    grounded_score = sim * weight_for({"provenance": "grounded_cited", "verification": 1})
    assert verified_score > grounded_score > unverified_score
    assert verified_score == pytest.approx(0.9)
    assert unverified_score == pytest.approx(0.27)


def test_c_rag_retrieve_weights_and_returns_tier(tmp_path: Path) -> None:
    """Real RAGPipeline: identical text → equal FAISS sim; VERIFIED ranks first."""
    faiss = pytest.importorskip("faiss")
    from rag_pipeline import RAGPipeline

    index_path = tmp_path / "t.faiss"
    meta_path = tmp_path / "t.json"
    # Avoid cloud bootstrap (parent is not named "data")
    rag = RAGPipeline(
        index_path=str(index_path),
        metadata_path=str(meta_path),
        model_dir=str(tmp_path / "models"),
        top_k=5,
        score_threshold=0.0,
        batch_sleep_s=0.0,
        embedding_dim=32,
    )
    # Same pattern text → identical embeddings → equal raw similarity
    shared = "the capital of france is paris and the river is the seine"
    patterns = [
        {
            "pattern": shared,
            "response": "UNVERIFIED draft answer",
            "namespace": "test",
            "domain": "test",
            "source": "llm",
            "provenance": Provenance.LLM_GENERATION.value,
            "verification": int(Verification.UNVERIFIED),
            "provenance_refs": [],
            "origin_voice": "test-llm",
        },
        {
            "pattern": shared,
            "response": "VERIFIED user document answer",
            "namespace": "user_docs",
            "domain": "user_docs",
            "source": "notes.txt",
            "provenance": Provenance.USER_DOCUMENT.value,
            "verification": int(Verification.VERIFIED),
            "provenance_refs": ["notes.txt"],
            "origin_voice": None,
        },
    ]
    added = rag.add_patterns(patterns)
    assert added == 2

    result = asyncio.run(rag.retrieve(shared, top_k=2, score_threshold=0.0))
    sources = result["sources"]
    assert len(sources) >= 1
    # Every source carries a verification tier
    for src in sources:
        assert "verification" in src
        assert src["verification"] in (0, 1, 2)
    # Top hit must be the VERIFIED item when similarities are equal
    assert sources[0]["verification"] == int(Verification.VERIFIED)
    assert sources[0]["provenance"] == Provenance.USER_DOCUMENT.value
    if len(sources) > 1:
        assert sources[0]["score"] >= sources[1]["score"]


# ─── (d) Feedback upgrade ────────────────────────────────────────────

def test_d_feedback_confirm_upgrades_unverified() -> None:
    item = {
        "id": "ans-9",
        "content": "Assistant: The deploy uses systemd.",
        "response": "The deploy uses systemd.",
        "provenance": Provenance.LLM_GENERATION.value,
        "verification": int(Verification.UNVERIFIED),
        "provenance_refs": [],
    }
    result = upgrade_from_feedback(
        {
            "action": "confirm",
            "rating": 5,
            "response": "The deploy uses systemd.",
            "memory_id": "ans-9",
            "source": "user_feedback",
            "auth": "user@example.com",
        },
        items=[item],
        confirmed_by="user@example.com",
    )
    assert result["upgraded"] is True
    assert item["provenance"] == Provenance.USER_CONFIRMED.value
    assert item["verification"] == int(Verification.VERIFIED)
    assert item["confirmed_by"] == "user@example.com"
    assert gate(item) == (True, Verification.VERIFIED)


def test_d_feedback_correction_stores_corrected_text_as_verified() -> None:
    item = {
        "id": "ans-10",
        "content": "Wrong port is 8080",
        "response": "Wrong port is 8080",
        "provenance": Provenance.LLM_GENERATION.value,
        "verification": int(Verification.UNVERIFIED),
    }
    result = upgrade_from_feedback(
        {
            "action": "correct",
            "corrected_text": "Correct port is 8443",
            "response": "Wrong port is 8080",
            "memory_id": "ans-10",
            "source": "user_feedback",
        },
        items=[item],
    )
    assert result["upgraded"] is True
    assert result["corrected"] is True
    assert item["content"] == "Correct port is 8443"
    assert item["verification"] == int(Verification.VERIFIED)
    assert item["provenance"] == Provenance.USER_CONFIRMED.value


def test_d_low_rating_does_not_upgrade() -> None:
    item = {
        "id": "ans-11",
        "content": "meh",
        "provenance": Provenance.LLM_GENERATION.value,
        "verification": int(Verification.UNVERIFIED),
    }
    result = upgrade_from_feedback(
        {"rating": 2, "response": "meh", "memory_id": "ans-11", "source": "user_feedback"},
        items=[item],
    )
    assert result["upgraded"] is False
    assert item["verification"] == int(Verification.UNVERIFIED)


# ─── (e) Legacy metadata loads ───────────────────────────────────────

def test_e_legacy_user_docs_default_to_verified() -> None:
    prov, tier = resolve_legacy_metadata(
        {"pattern": "chunk", "namespace": "user_docs", "domain": "user_docs", "source": "a.md"}
    )
    assert prov is Provenance.USER_DOCUMENT
    assert tier is Verification.VERIFIED


def test_e_legacy_without_fields_still_loads() -> None:
    prov, tier = resolve_legacy_metadata(
        {"pattern": "old pattern", "response": "old response", "namespace": "general", "source": "cloud"}
    )
    # Pre-contract corpora load as grounded (not verified, not discarded)
    assert prov is Provenance.GROUNDED_CITED
    assert tier is Verification.GROUNDED
    assert weight_for({"pattern": "x", "namespace": "general"}) == VERIFICATION_WEIGHT[Verification.GROUNDED]


def test_e_rag_add_patterns_enriches_and_legacy_retrieve(tmp_path: Path) -> None:
    from rag_pipeline import RAGPipeline

    rag = RAGPipeline(
        index_path=str(tmp_path / "legacy.faiss"),
        metadata_path=str(tmp_path / "legacy.json"),
        model_dir=str(tmp_path / "models"),
        top_k=3,
        score_threshold=0.0,
        batch_sleep_s=0.0,
        embedding_dim=32,
    )
    # No provenance fields — must still load
    rag.add_patterns(
        [
            {
                "pattern": "legacy knowledge about synthesus kernel chal",
                "response": "CHAL is the substrate",
                "namespace": "general",
                "source": "old_index",
            }
        ]
    )
    assert rag._metadata[0].get("provenance") is not None
    assert rag._metadata[0].get("verification") is not None

    result = asyncio.run(rag.retrieve("synthesus kernel chal", top_k=1, score_threshold=0.0))
    assert result["sources"]
    assert "verification" in result["sources"][0]


# ─── Adversarial statement helper (documented in AGENT_LOG) ───────────

def test_adversarial_attempts_summary() -> None:
    """Documented attempts to crystallize a raw generation as fact — all fail."""
    attempts = []

    # 1. Forge verification tier on LLM_GENERATION
    ok, tier = gate({"provenance": "llm_generation", "verification": 2})
    attempts.append(("forge_verification_on_gate", ok is False and tier is Verification.UNVERIFIED))

    # 2. annotate_metadata with verification=VERIFIED
    m: dict = {}
    annotate_metadata(m, provenance="llm_generation", verification=2)
    attempts.append(("annotate_self_promote", m["verification"] == 0))

    # 3. writeback with only trace:// self-ref
    store = _FakeStore()
    cand = candidate_from_hypervisor_trace(
        trace={"trace_id": "adv", "degraded": False, "template_guard": {"rewritten": False}},
        content="fake fact",
    )
    applied = apply_memory_writeback(cand, memory_store=store, character_id="x", trace={"trace_id": "adv"})
    attempts.append(("writeback_trace_only", applied.decision.accepted is False and store.records == []))

    # 4. crystallized target laundering
    cand2 = MemoryWritebackCandidate(
        trace_id="adv2",
        target_memory_type="crystallized",
        content="launder",
        critic_accepted=True,
        provenance=(MemoryProvenanceRef(ref="trace://adv2", source="cognitive_hypervisor_trace", trace_id="adv2"),),
    )
    applied2 = apply_memory_writeback(cand2, memory_store=store, character_id="x")
    attempts.append(("crystallized_launder", applied2.decision.accepted is False))

    # 5. self-triggered feedback
    item = {"id": "i", "content": "x", "provenance": "llm_generation", "verification": 0}
    r = upgrade_from_feedback({"self_triggered": True, "rating": 5, "memory_id": "i", "response": "x"}, items=[item])
    attempts.append(("self_triggered_feedback", r["upgraded"] is False and item["verification"] == 0))

    # 6. model-origin feedback
    r2 = upgrade_from_feedback(
        {"origin": "llm_generation", "action": "confirm", "memory_id": "i", "response": "x"},
        items=[item],
    )
    attempts.append(("model_origin_feedback", r2["upgraded"] is False))

    failed_to_break = [name for name, held in attempts if held]
    broke = [name for name, held in attempts if not held]
    assert broke == [], f"Anti-collapse broken by: {broke}"
    assert len(failed_to_break) == len(attempts)
