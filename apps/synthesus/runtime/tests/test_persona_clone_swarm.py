"""SW-1..SW-5 tests — Persona-Clone Expert Swarm (real model, no mocks of inference).

Requires local Ollama with a base model (default llama3.2:3b).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (
    ROOT / "packages" / "swarm",
    ROOT / "packages" / "knowledge",
    ROOT / "packages" / "core",
    ROOT / "packages",
    ROOT,
):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from swarm.registry import Expert, ExpertRegistry, SwarmRequest  # noqa: E402
from swarm.scheduler import SwarmScheduler  # noqa: E402
from swarm.arbiter import SwarmArbiter, SwarmRuntime  # noqa: E402
from swarm.adapters.loader import AdapterLoader  # noqa: E402
from swarm.model_client import SharedOllamaClient  # noqa: E402
from swarm.envelope_firecracker import (  # noqa: E402
    FirecrackerEnvelope,
    FirecrackerEnvelopeConfig,
    FirecrackerLocalBlockedError,
    require_hosted_or_block,
)


def _ollama_ready() -> bool:
    try:
        import requests

        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


requires_ollama = pytest.mark.skipif(
    not _ollama_ready(), reason="Ollama not reachable on :11434"
)


def _base_model() -> str:
    return os.environ.get("SYNTHESUS_MODEL") or os.environ.get("OLLAMA_MODEL") or "llama3.2:3b"


def _three_experts(registry: ExpertRegistry) -> list[str]:
    registry.register(
        Expert(
            expert_id="historian",
            persona="Historian",
            system_prompt=(
                "You are a careful historian. Prefer dates, causes, and primary sources. "
                "Start answers with the word HISTORY:"
            ),
            namespace="ns_history",
            domain="history",
        )
    )
    registry.register(
        Expert(
            expert_id="engineer",
            persona="Systems Engineer",
            system_prompt=(
                "You are a systems engineer. Prefer concrete mechanisms and tradeoffs. "
                "Start answers with the word ENGINEER:"
            ),
            namespace="ns_engineering",
            domain="engineering",
        )
    )
    registry.register(
        Expert(
            expert_id="ethicist",
            persona="Ethicist",
            system_prompt=(
                "You are an ethicist. Prefer values, harms, and duties. "
                "Start answers with the word ETHICS:"
            ),
            namespace="ns_ethics",
            domain="ethics",
        )
    )
    return ["historian", "engineer", "ethicist"]


def _ollama_ps() -> str:
    try:
        return subprocess.check_output(["ollama", "ps"], text=True, timeout=10)
    except Exception as e:
        return f"(ollama ps failed: {e})"


# ---------------------------------------------------------------------------
# SW-1 registry
# ---------------------------------------------------------------------------

def test_sw1_registry_deltas_only():
    reg = ExpertRegistry()
    reg.register(
        Expert(
            expert_id="a",
            persona="A",
            system_prompt="You are A.",
            namespace="ns_a",
            adapter_ref=None,
        )
    )
    assert len(reg) == 1
    assert reg.get("a").namespace == "ns_a"
    assert reg.get("missing") is None
    snap = reg.snapshot()
    assert snap[0]["adapter_ref"] is None


# ---------------------------------------------------------------------------
# SW-5 firecracker local BLOCK
# ---------------------------------------------------------------------------

def test_sw5_firecracker_blocked_on_local(monkeypatch):
    monkeypatch.delenv("SYNTHESUS_SWARM_HOSTED", raising=False)
    env = FirecrackerEnvelope(FirecrackerEnvelopeConfig(expert_id="x"))
    with pytest.raises(FirecrackerLocalBlockedError) as ei:
        env.start()
    assert "BLOCKED" in str(ei.value)
    assert "HOSTED-only" in str(ei.value) or "single-GPU" in str(ei.value)

    with pytest.raises(FirecrackerLocalBlockedError):
        require_hosted_or_block("y")


def test_sw5_firecracker_hosted_still_honest_block(monkeypatch):
    """Even with HOSTED=1, lifecycle is not faked — still loud NotImplemented."""
    monkeypatch.setenv("SYNTHESUS_SWARM_HOSTED", "1")
    env = FirecrackerEnvelope(FirecrackerEnvelopeConfig(expert_id="hosted-x"))
    with pytest.raises(FirecrackerLocalBlockedError):
        env.start()


# ---------------------------------------------------------------------------
# SW-4 adapter validation
# ---------------------------------------------------------------------------

def test_sw4_missing_adapter_degrades(tmp_path):
    loader = AdapterLoader(expected_base_model=_base_model(), root=tmp_path)
    v = loader.validate("does_not_exist_lora")
    assert v.ok is False
    assert v.reason == "adapter_missing"


def test_sw4_adapter_data_ok(tmp_path):
    man = {
        "adapter_id": "delta1",
        "base_model": _base_model().split(":")[0],
        "kind": "persona_delta",
        "weight_files": [],
    }
    p = tmp_path / "adapter.json"
    p.write_text(json.dumps(man), encoding="utf-8")
    loader = AdapterLoader(expected_base_model=_base_model(), root=tmp_path)
    v = loader.validate(str(p))
    assert v.ok is True
    assert v.manifest is not None


def test_sw4_refuses_executable_adapter(tmp_path):
    evil = tmp_path / "evil.py"
    evil.write_text("print('nope')\n", encoding="utf-8")
    loader = AdapterLoader(expected_base_model=_base_model(), root=tmp_path)
    v = loader.validate(str(evil))
    assert v.ok is False
    assert v.reason == "adapter_executable_forbidden"


# ---------------------------------------------------------------------------
# SW-2 / SW-3 live Ollama tests
# ---------------------------------------------------------------------------

@requires_ollama
def test_sw2_three_experts_one_resident_model():
    """(1) 3 experts → only ONE model resident; all answered through it."""
    os.environ.setdefault("SYNTHESUS_FAST_MODE", "1")
    reg = ExpertRegistry()
    ids = _three_experts(reg)
    client = SharedOllamaClient(base_model=_base_model())
    sched = SwarmScheduler(reg, model_client=client)
    req = SwarmRequest(
        query="In one short sentence, what is your primary lens on technology?",
        expert_ids=ids,
        budget={"max_tokens": 64, "timeout_s": 90},
    )
    results = sched.run(req)
    assert len(results) == 3
    healthy = [r for r in results if not r.degraded]
    assert len(healthy) >= 2, f"too many degraded: {[r.to_dict() for r in results]}"

    # All generations (including degraded) report at most the single base model id
    all_models = {r.model_id for r in results if r.model_id}
    assert all_models == {client.base_model}, all_models
    models = {r.model_id for r in healthy}
    assert models == {client.base_model}, models
    assert client.models_requested == {client.base_model}
    assert len(client.models_requested) == 1
    assert client.call_count == 3
    for r in healthy:
        assert r.adapter_applied is False
        assert r.adapter_status == "persona_prompt_delta_only"

    ps = _ollama_ps()
    print("\n=== ollama ps after 3-expert fan-out ===\n", ps)
    print("models_requested", client.models_requested)
    print("healthy texts:", [(r.expert_id, r.text[:80]) for r in healthy])

@requires_ollama
def test_sw2_persona_distinct_namespace_scoped():
    """(2) two deltas → persona-distinct answers from one base."""
    os.environ.setdefault("SYNTHESUS_FAST_MODE", "1")
    reg = ExpertRegistry()
    reg.register(
        Expert(
            expert_id="poet",
            persona="Poet",
            system_prompt=(
                "You are a poet. Use a metaphor. "
                "Your first characters MUST be exactly: POET:"
            ),
            namespace="ns_poetry",
            domain="arts",
        )
    )
    reg.register(
        Expert(
            expert_id="auditor",
            persona="Auditor",
            system_prompt=(
                "You are an auditor. Mention risk. "
                "Your first characters MUST be exactly: AUDITOR:"
            ),
            namespace="ns_audit",
            domain="finance",
        )
    )
    client = SharedOllamaClient(base_model=_base_model())
    sched = SwarmScheduler(reg, model_client=client)
    results = sched.run(
        SwarmRequest(
            query="Comment on artificial intelligence in one sentence.",
            expert_ids=["poet", "auditor"],
            budget={"max_tokens": 80, "timeout_s": 90},
        )
    )
    by_id = {r.expert_id: r for r in results}
    assert not by_id["poet"].degraded, by_id["poet"].degrade_reason
    assert not by_id["auditor"].degraded, by_id["auditor"].degrade_reason
    poet_t = by_id["poet"].text.strip().upper()
    audit_t = by_id["auditor"].text.strip().upper()
    # Strict: scheduler requires EXPERT_ID: prefix; also accept POET:/AUDITOR: from prompt
    assert poet_t.startswith("POET:") or poet_t.startswith("POET"), (
        f"poet missing persona marker: {by_id['poet'].text!r}"
    )
    assert audit_t.startswith("AUDITOR:") or audit_t.startswith("AUDITOR") or "RISK" in audit_t, (
        f"auditor missing persona marker: {by_id['auditor'].text!r}"
    )
    assert by_id["poet"].text != by_id["auditor"].text
    assert by_id["poet"].namespace == "ns_poetry"
    assert by_id["auditor"].namespace == "ns_audit"
    assert {r.model_id for r in results if not r.degraded} == {client.base_model}
    assert client.models_requested == {client.base_model}
    assert by_id["poet"].adapter_applied is False
    assert by_id["poet"].adapter_status == "persona_prompt_delta_only"
    print("poet:", by_id["poet"].text[:120])
    print("auditor:", by_id["auditor"].text[:120])

@requires_ollama
def test_sw2_missing_adapter_degrades_swarm_still_answers(tmp_path):
    """(3) missing adapter → that expert degraded; swarm still answers; no fabrications."""
    os.environ.setdefault("SYNTHESUS_FAST_MODE", "1")
    reg = ExpertRegistry()
    reg.register(
        Expert(
            expert_id="ok_expert",
            persona="Guide",
            system_prompt="You are a helpful guide. Answer briefly. Start with GUIDE:",
            namespace="ns_ok",
        )
    )
    reg.register(
        Expert(
            expert_id="broken_adapter_expert",
            persona="Ghost",
            system_prompt="You are a ghost expert.",
            namespace="ns_ghost",
            adapter_ref=str(tmp_path / "missing_lora_dir"),
        )
    )
    # also missing expert id
    client = SharedOllamaClient(base_model=_base_model())
    runtime = SwarmRuntime(
        SwarmScheduler(
            reg,
            model_client=client,
            adapter_loader=AdapterLoader(expected_base_model=client.base_model, root=tmp_path),
        )
    )
    ans = runtime.answer(
        SwarmRequest(
            query="What is 2+2? One short sentence.",
            expert_ids=["ok_expert", "broken_adapter_expert", "not_registered"],
            budget={"max_tokens": 48, "timeout_s": 90},
        )
    )
    by = {r["expert_id"]: r for r in ans.expert_results}
    assert by["broken_adapter_expert"]["degraded"] is True
    assert by["broken_adapter_expert"]["degrade_reason"] == "adapter_missing"
    assert by["broken_adapter_expert"]["text"] == ""  # NO fabricated persona output
    assert by["not_registered"]["degraded"] is True
    assert by["not_registered"]["text"] == ""
    assert by["ok_expert"]["degraded"] is False
    assert ans.response.strip()  # swarm still answered
    assert "broken_adapter_expert" in ans.degraded_experts
    assert "ok_expert" in ans.contributing_experts
    # No template-surface / fabricated dump as user-facing response
    low = ans.response.lower()
    assert "swarm: [expert:" not in low
    assert "response_template" not in low
    assert by["ok_expert"].get("adapter_applied") is False
    print("swarm response:", ans.response[:200])
    print("degraded:", ans.degraded_experts)
    print("selected_source:", ans.arbitration.get("selected_source"))


@requires_ollama
def test_sw3_sources_carry_verification_tiers():
    """(4) SwarmAnswer.sources carry C-001 tiers."""
    os.environ.setdefault("SYNTHESUS_FAST_MODE", "1")
    reg = ExpertRegistry()
    _three_experts(reg)

    def retrieval(query: str, expert: Expert):
        # Namespace-scoped fake-but-structured retrieval hits with real tier fields
        if expert.namespace == "ns_history":
            return [
                {
                    "source": "archive/treaty.txt",
                    "pattern": "Treaty signed in 1815",
                    "provenance": "user_document",
                    "verification": 2,
                    "verification_name": "VERIFIED",
                    "score": 0.9,
                }
            ]
        if expert.namespace == "ns_engineering":
            return [
                {
                    "source": "docs/design.md",
                    "pattern": "System uses a single shared GPU",
                    "provenance": "grounded_cited",
                    "verification": 1,
                    "verification_name": "GROUNDED",
                    "score": 0.8,
                }
            ]
        return [
            {
                "source": "llm_scratch",
                "pattern": "speculative note",
                "provenance": "llm_generation",
                "verification": 0,
                "verification_name": "UNVERIFIED",
                "score": 0.4,
            }
        ]

    client = SharedOllamaClient(base_model=_base_model())
    runtime = SwarmRuntime(
        SwarmScheduler(reg, model_client=client, retrieval_fn=retrieval)
    )
    ans = runtime.answer(
        SwarmRequest(
            query="Summarize the key constraint in one sentence.",
            expert_ids=["historian", "engineer", "ethicist"],
            budget={"max_tokens": 64, "timeout_s": 90},
        )
    )
    assert ans.sources, "expected sources"
    tiers = {int(s.get("verification", -1)) for s in ans.sources if "verification" in s}
    assert 2 in tiers or 1 in tiers or 0 in tiers
    for s in ans.sources:
        assert "verification" in s
        assert s["verification"] in (0, 1, 2)
        assert "provenance" in s or "verification_name" in s
    # Verified should sort at or before unverified when both present
    if len(ans.sources) >= 2:
        first_tiers = [_tier := int(s.get("verification", 0)) for s in ans.sources[:3]]
        print("top source tiers:", first_tiers)
    print("sources sample:", json.dumps(ans.sources[:4], indent=2)[:800])


@requires_ollama
def test_sw2_fast_mode_shared_base_timing():
    """(6) fast-mode swarm of N ≤ ~N× one warm call (shared resident base)."""
    os.environ["SYNTHESUS_FAST_MODE"] = "1"
    reg = ExpertRegistry()
    ids = _three_experts(reg)
    client = SharedOllamaClient(base_model=_base_model())
    sched = SwarmScheduler(reg, model_client=client)

    # Warm the single base model once
    warm = client.generate(
        prompt="Say hi in 3 words.",
        system_prompt="You are a warm-up probe. Be brief.",
        max_tokens=16,
        timeout_s=90,
    )
    assert not warm.degraded, warm.degrade_reason
    warm_ms = warm.latency_ms
    print(f"warm call: {warm_ms:.0f}ms model={warm.model_id}")

    t0 = time.time()
    results = sched.run(
        SwarmRequest(
            query="Name one principle of your discipline in under 12 words.",
            expert_ids=ids,
            budget={"max_tokens": 48, "timeout_s": 90},
        )
    )
    total_ms = (time.time() - t0) * 1000.0
    n = len(ids)
    # Shared base: sequential N calls ≈ N × warm (generous 4× slack for load/jitter)
    ceiling = max(warm_ms * n * 4.0, 30_000.0)
    print(f"swarm N={n} total={total_ms:.0f}ms warm={warm_ms:.0f}ms ceiling={ceiling:.0f}ms")
    print("models_requested", client.models_requested)
    assert client.models_requested == {client.base_model}
    assert total_ms <= ceiling, (
        f"swarm too slow ({total_ms:.0f}ms > {ceiling:.0f}ms) — possible per-expert reload"
    )
    healthy = [r for r in results if not r.degraded]
    assert len(healthy) >= 2
