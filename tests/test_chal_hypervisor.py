import asyncio
import time
from dataclasses import dataclass

from core.chal.hypervisor import CognitiveHypervisor, HypervisorRoute
from core.chal.quad_brain import QuadBrainArbitration, QuadBrainRole


class StubBridge:
    def __init__(self):
        self.calls = []

    async def route_query(self, query, hemisphere="auto", character_context=None, rag_context="", max_tokens=512):
        self.calls.append(
            {
                "query": query,
                "hemisphere": hemisphere,
                "character_context": character_context,
                "rag_context": rag_context,
                "max_tokens": max_tokens,
            }
        )
        return {
            "response": f"routed through {hemisphere}",
            "hemisphere_used": hemisphere,
            "latency_ms": 1.25,
        }


class SlowBridge:
    async def route_query(self, *args, **kwargs):
        await asyncio.sleep(0.6)
        return {"response": "too late", "latency_ms": 600.0}


class FaultBridge:
    async def route_query(self, *args, **kwargs):
        raise RuntimeError("device bus fault")


class LegacyTemplateBridge:
    async def route_query(self, *args, **kwargs):
        return {
            "response": "[module] Handled: legacy_ppbrs. Use response_template.",
            "hemisphere_used": "left",
            "latency_ms": 0.5,
        }


class SafetyTemplateBridge:
    async def route_query(self, *args, **kwargs):
        return {
            "response": "[module] Handled: safety_boundary. Rotate the credential.",
            "hemisphere_used": "both",
            "latency_ms": 0.5,
        }


class BlockingBridge:
    def route_query(self, *args, **kwargs):
        time.sleep(0.6)
        return {"response": "too late", "latency_ms": 600.0}


class PersonaBridge:
    async def route_query(self, query, hemisphere="auto", character_context=None, rag_context="", max_tokens=512):
        return {
            "response": "The gate is sealed until dawn.",
            "hemisphere_used": hemisphere,
            "latency_ms": 1.0,
            "arbitration": {"agreement_score": 0.7, "winner": "right"},
        }


class FakeKnowledgeController:
    def query(self, text):
        from core.chal.interfaces import TelemetryRecord

        return (
            f"mounted fact for {text}",
            TelemetryRecord(
                operation_id="kc_lookup",
                latency_ms=2.5,
                cache_hit=False,
                confidence=0.91,
                source="rom_mount:kc_knowledge_cloud_world_lore_json",
                metadata={
                    "hot_context": False,
                    "mounts": [
                        {
                            "mount_path": "/mnt/rom/world_lore",
                            "mount_type": "ROM",
                            "partition_id": "kc_knowledge_cloud_world_lore_json",
                            "namespace": "game_lore",
                            "artifact": {
                                "relative_path": "knowledge_cloud/world_lore.json",
                                "actual_sha256": "abc123",
                                "actual_size": 128,
                                "integrity_ok": True,
                            },
                        }
                    ],
                },
            ),
        )


class FakeReranker:
    def rerank(self, query, chunks, top_k=10):
        ranked = sorted(
            enumerate(chunks),
            key=lambda item: (0 if "manifest" in item[1].lower() else 1, item[0]),
        )
        return [
            {
                "chunk": chunk,
                "score": 1.0 if rank == 1 else 0.25,
                "rank": rank,
                "index": index,
            }
            for rank, (index, chunk) in enumerate(ranked[:top_k], start=1)
        ]


@dataclass
class FakeVerificationStatus:
    value: str


@dataclass
class FakeVerificationIssue:
    issue_id: str
    severity: int
    category: str
    description: str
    suggestion: str = ""


@dataclass
class FakeVerificationResult:
    status: FakeVerificationStatus
    score: float
    issues: list[FakeVerificationIssue]
    metadata: dict


class FakeAnswerVerifier:
    def verify(self, answer, query, context=None, revision_count=0):
        if context and "mounted fact" not in answer:
            return FakeVerificationResult(
                status=FakeVerificationStatus("needs_revision"),
                score=0.42,
                issues=[
                    FakeVerificationIssue(
                        issue_id="grounding_low",
                        severity=2,
                        category="factual",
                        description="Answer drifted from mounted context",
                        suggestion="Rewrite against the selected CHAL grounding chunk",
                    )
                ],
                metadata={"overlap": 0.11},
            )
        return FakeVerificationResult(
            status=FakeVerificationStatus("passed"),
            score=0.91,
            issues=[],
            metadata={"overlap": 0.8 if context else None},
        )


class FailingAnswerVerifier:
    def verify(self, answer, query, context=None, revision_count=0):
        return FakeVerificationResult(
            status=FakeVerificationStatus("failed"),
            score=0.18,
            issues=[
                FakeVerificationIssue(
                    issue_id="surface_unverified",
                    severity=3,
                    category="quality",
                    description="Surface could not be verified within the active critic budget",
                    suggestion="Route through a critic rewrite pass before final emission",
                )
            ],
            metadata={"overlap": 0.0},
        )


def _quad_brain_quality_score(text, trace):
    score = 0
    if "The gate is sealed until dawn." in text:
        score += 1
    if text.startswith("Archivist"):
        score += 1
    if trace and trace["state_contract"]["serialized_arbitration"] is True:
        score += 1
    if trace and trace["state_contract"]["parallel_brain_spawn"] is False:
        score += 1
    if "[module]" not in text and "response_template" not in text:
        score += 1
    return score


def test_hypervisor_plans_grounded_path_for_knowledge_cloud_workload():
    hypervisor = CognitiveHypervisor()
    decision = hypervisor.plan("Check the Knowledge Cloud manifest integrity")

    assert decision.route == HypervisorRoute.GROUNDED_PATH
    assert decision.hemisphere_mode == "auto"
    assert decision.budget.retrieval_depth >= 4
    assert "ground_response_in_mounted_knowledge" in decision.constraints


def test_hypervisor_plans_quad_brain_path_for_npc_context():
    hypervisor = CognitiveHypervisor()
    decision = hypervisor.plan(
        "Render this dialogue response",
        character_context={"character_id": "merchant"},
    )

    assert decision.route == HypervisorRoute.QUAD_BRAIN_PATH
    assert decision.hemisphere_mode == "both"
    assert decision.budget.candidate_count >= 4


def test_business_bot_preset_routes_to_concise_quad_brain_cgpu_surface():
    bridge = StubBridge()
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: bridge)

    result = asyncio.run(
        hypervisor.process_query(
            "Tell the operator the next step",
            runtime_preset="business_bot",
        )
    )

    quad_trace = result.telemetry["quad_brain"]
    cgpu_output = quad_trace["outputs"][2]

    assert result.decision.route == HypervisorRoute.QUAD_BRAIN_PATH
    assert result.decision.hemisphere_mode == "auto"
    assert result.telemetry["runtime_preset"] == "business_bot"
    assert "business_bot_preset" in result.telemetry["reasons"]
    assert cgpu_output["content"]["trace"]["mode"] == "business_bot"
    assert result.response.startswith(("Direct answer:", "Recommended next step:"))
    assert "response_template" not in result.response


def test_hypervisor_quad_brain_path_serializes_four_brain_arbitration():
    bridge = StubBridge()
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: bridge)

    result = asyncio.run(
        hypervisor.process_query(
            "Render this dialogue response",
            character_context={"character_id": "merchant", "stance": "guarded"},
        )
    )

    quad_trace = result.telemetry["quad_brain"]
    roles = [output["role"] for output in quad_trace["outputs"]]

    assert result.decision.route == HypervisorRoute.QUAD_BRAIN_PATH
    assert bridge.calls == [
        {
            "query": "Render this dialogue response",
            "hemisphere": "both",
            "character_context": {"character_id": "merchant", "stance": "guarded"},
            "rag_context": "",
            "max_tokens": 512,
        }
    ]
    assert roles == [role.value for role in QuadBrainRole]
    assert quad_trace["serial_order"] == [role.value for role in QuadBrainRole]
    assert quad_trace["state_contract"]["serialized_arbitration"] is True
    assert quad_trace["state_contract"]["parallel_brain_spawn"] is False
    assert quad_trace["state_contract"]["required_roles"] == [role.value for role in QuadBrainRole]
    assert quad_trace["state_contract"]["critic_input_ref"] == "cgpu.selected_candidate"
    assert quad_trace["state_contract"]["final_output_ref"] == "critic.selected_response"
    assert quad_trace["state_contract"]["final_output_owner"] == "critic_metacognition"
    assert quad_trace["state_contract"]["integrity"]["status"] == "passed"
    assert quad_trace["selected_source"] == "critic_metacognition"
    assert "routed through both" in result.response
    assert result.bridge_result["quad_brain_arbitration"]["trace_id"] == result.decision.trace_id


def test_quad_brain_trace_records_serial_state_transitions():
    bridge = PersonaBridge()
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: bridge)

    result = asyncio.run(
        hypervisor.process_query(
            "Render Archivist dialogue about the sealed gate",
            character_context={"character_id": "Archivist", "stance": "cautious"},
        )
    )

    quad_trace = result.telemetry["quad_brain"]
    transitions = quad_trace["state_contract"]["state_transitions"]

    assert [transition["role"] for transition in transitions] == [role.value for role in QuadBrainRole]
    assert transitions[0]["input_refs"] == ["query", "rag_context", "hemisphere_bridge.response"]
    assert transitions[0]["output_refs"] == ["knowledge.facts", "knowledge.provenance"]
    assert transitions[1]["input_refs"] == ["hypervisor.decision", "knowledge.facts", "constraints"]
    assert transitions[2]["device"] == "chal://cgpu/render"
    assert transitions[3]["output_refs"] == ["critic.selected_response", "critic.template_guard"]

    for output, transition in zip(quad_trace["outputs"], transitions):
        assert output["trace"]["state_transition"] == transition

    cgpu_output = quad_trace["outputs"][2]
    critic_output = quad_trace["outputs"][3]
    selected_candidate_id = cgpu_output["content"]["selected_candidate_id"]

    assert selected_candidate_id
    assert quad_trace["state_contract"]["critic_reviewed_candidate_id"] == selected_candidate_id
    assert critic_output["content"]["selected_candidate_id"] == selected_candidate_id
    assert critic_output["content"]["reviewed_candidate_ref"] == "cgpu.selected_candidate"
    assert critic_output["trace"]["input_refs"] == ["cgpu.selected_candidate", "template_surface"]
    assert critic_output["trace"]["reviewed_candidate_id"] == selected_candidate_id

    integrity = quad_trace["state_contract"]["integrity"]
    assert integrity["status"] == "passed"
    assert integrity["selected_candidate_id"] == selected_candidate_id
    assert integrity["reviewed_candidate_id"] == selected_candidate_id
    assert integrity["checks"] == {
        "roles_complete": True,
        "serial_order_valid": True,
        "transitions_complete": True,
        "output_transition_mirrors": True,
        "critic_handoff_valid": True,
        "final_output_owned_by_critic": True,
    }


def test_quad_brain_trace_emits_compact_replay_record_without_response_text():
    bridge = PersonaBridge()
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: bridge)

    result = asyncio.run(
        hypervisor.process_query(
            "Render Archivist dialogue about the sealed gate",
            character_context={"character_id": "Archivist", "stance": "cautious"},
        )
    )

    replay = result.telemetry["quad_brain_replay"]
    state_contract = replay["state_contract"]

    assert replay == result.bridge_result["quad_brain_replay"]
    assert replay["schema"] == "synthesus.chal.quad_brain_replay.v1"
    assert replay["trace_id"] == result.decision.trace_id
    assert replay["prompt_ref"] == "hypervisor.query"
    assert replay["serial_order"] == [role.value for role in QuadBrainRole]
    assert replay["output_roles"] == [role.value for role in QuadBrainRole]
    assert replay["output_devices"]["knowledge_grounding"] == "chal://knowledge/grounding"
    assert state_contract["serialized_arbitration"] is True
    assert state_contract["parallel_brain_spawn"] is False
    assert state_contract["final_output_owner"] == "critic_metacognition"
    assert state_contract["integrity"]["status"] == "passed"
    assert replay["selected_response_chars"] == len(result.response)
    assert len(replay["selected_response_sha256"]) == 64
    assert len(replay["record_hash"]) == 64
    assert replay["record_hash"] == QuadBrainArbitration.replay_record_hash(replay)
    assert "selected_response" not in replay
    assert result.response not in str(replay)

    tampered = dict(replay)
    tampered["selected_response_chars"] += 1
    assert tampered["record_hash"] != QuadBrainArbitration.replay_record_hash(tampered)


def test_quad_brain_dispatch_preserves_grounding_and_improves_persona_surface_over_dual_hemi():
    bridge = PersonaBridge()
    legacy_dual_hemi = asyncio.run(
        bridge.route_query(
            "Render Archivist dialogue about the sealed gate",
            hemisphere="both",
            character_context={"character_id": "Archivist", "stance": "cautious"},
        )
    )
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: bridge)

    result = asyncio.run(
        hypervisor.process_query(
            "Render Archivist dialogue about the sealed gate",
            character_context={"character_id": "Archivist", "stance": "cautious"},
        )
    )

    quad_trace = result.telemetry["quad_brain"]
    legacy_score = _quad_brain_quality_score(legacy_dual_hemi["response"], None)
    quad_score = _quad_brain_quality_score(result.response, quad_trace)

    assert result.decision.route == HypervisorRoute.QUAD_BRAIN_PATH
    assert legacy_dual_hemi["hemisphere_used"] == "both"
    assert "The gate is sealed until dawn." in result.response
    assert result.response.startswith("Archivist")
    assert quad_score > legacy_score
    assert quad_trace["outputs"][0]["content"]["facts"] == ["The gate is sealed until dawn."]
    assert quad_trace["outputs"][2]["content"]["selected_text"] == result.response
    assert result.telemetry["template_guard"]["allowed"] is True


def test_hypervisor_dispatches_with_trace_and_budget_metadata():
    bridge = StubBridge()
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: bridge)

    result = asyncio.run(
        hypervisor.process_query(
            "Compare CHAL memory and cache architecture",
            max_tokens=256,
        )
    )

    assert result.response == "routed through both"
    assert result.decision.route == HypervisorRoute.DEEP_REASONING_PATH
    assert bridge.calls[0]["hemisphere"] == "both"
    assert result.telemetry["schema"] == "synthesus.chal.hypervisor_trace.v1"
    assert result.telemetry["budget"]["candidate_count"] == 3
    assert "compact_surface_response" in result.telemetry["constraints"]
    assert result.bridge_result["hypervisor_trace"]["trace_id"] == result.decision.trace_id
    assert result.telemetry["device_isolation"]["status"] == "ok"
    assert result.telemetry["budget_exhausted"] is False


def test_grounded_hypervisor_trace_includes_knowledge_mount_provenance():
    bridge = StubBridge()
    hypervisor = CognitiveHypervisor(
        bridge_factory=lambda: bridge,
        knowledge_controller=FakeKnowledgeController(),
    )

    result = asyncio.run(hypervisor.process_query("Check the Knowledge Cloud manifest"))

    provenance = result.telemetry["knowledge_provenance"]
    assert result.decision.route == HypervisorRoute.GROUNDED_PATH
    assert bridge.calls[0]["rag_context"] == "mounted fact for Check the Knowledge Cloud manifest"
    assert provenance["schema"] == "synthesus.chal.knowledge_provenance.v1"
    assert provenance["trace_id"] == result.decision.trace_id
    assert provenance["operation_id"] == "kc_lookup"
    assert provenance["mounted_context_used"] is True
    assert provenance["source"] == "rom_mount:kc_knowledge_cloud_world_lore_json"
    assert provenance["mounts"][0]["mount_path"] == "/mnt/rom/world_lore"
    assert provenance["mounts"][0]["artifact"]["integrity_ok"] is True


def test_grounded_hypervisor_reranks_context_before_bridge_dispatch():
    bridge = StubBridge()
    hypervisor = CognitiveHypervisor(
        bridge_factory=lambda: bridge,
        context_reranker=FakeReranker(),
    )

    result = asyncio.run(
        hypervisor.process_query(
            "Check the Knowledge Cloud manifest",
            rag_context="unrelated weather note\n\nmanifest integrity record",
        )
    )

    reranker_trace = result.telemetry["grounding_reranker"]

    assert bridge.calls[0]["rag_context"] == "manifest integrity record\n\nunrelated weather note"
    assert reranker_trace["schema"] == "synthesus.chal.grounding_reranker.v1"
    assert reranker_trace["device"] == "chal://reasoning/reranker"
    assert reranker_trace["status"] == "ok"
    assert reranker_trace["input_chunks"] == 2
    assert reranker_trace["selected_indices"] == [1, 0]
    assert "manifest integrity record" not in str(reranker_trace["scores"])
    assert reranker_trace["budget"] == {
        "retrieval_depth": 4,
        "input_chunks": 2,
        "selected_chunks": 2,
        "selection_truncated": False,
        "budget_exhausted": False,
    }
    assert reranker_trace["final_language_owner"] == "hemisphere_bridge_or_cgpu"


def test_grounded_reranker_trace_marks_retrieval_budget_truncation():
    bridge = StubBridge()
    hypervisor = CognitiveHypervisor(
        bridge_factory=lambda: bridge,
        context_reranker=FakeReranker(),
    )

    result = asyncio.run(
        hypervisor.process_query(
            "Check the Knowledge Cloud manifest",
            rag_context=(
                "chunk 0\n\nmanifest chunk 1\n\nchunk 2\n\n"
                "manifest chunk 3\n\nchunk 4"
            ),
        )
    )

    reranker_trace = result.telemetry["grounding_reranker"]

    assert result.decision.budget.retrieval_depth == 4
    assert reranker_trace["selected_chunks"] == 4
    assert reranker_trace["input_chunks"] == 5
    assert reranker_trace["budget"]["retrieval_depth"] == 4
    assert reranker_trace["budget"]["selection_truncated"] is True
    assert reranker_trace["budget"]["budget_exhausted"] is True
    assert len(bridge.calls[0]["rag_context"].split("\n\n")) == 4


def test_hypervisor_verifier_marks_revision_need_as_critic_budget_signal():
    bridge = StubBridge()
    hypervisor = CognitiveHypervisor(
        bridge_factory=lambda: bridge,
        answer_verifier=FakeAnswerVerifier(),
    )

    result = asyncio.run(
        hypervisor.process_query(
            "Check the Knowledge Cloud manifest",
            rag_context="mounted fact: manifest hash is valid",
        )
    )

    quality = result.telemetry["reasoning_quality"]

    assert quality["schema"] == "synthesus.chal.reasoning_quality.v1"
    assert quality["device"] == "chal://critic/verifier"
    assert quality["status"] == "needs_revision"
    assert quality["score"] == 0.42
    assert quality["context_chunks"] == 1
    assert quality["critic_passes_budgeted"] == 1
    assert quality["critic_revision_required"] is True
    assert quality["budget"] == {
        "critic_passes": 1,
        "revision_passes_required": 1,
        "revision_passes_available": 1,
        "revision_budget_exhausted": False,
    }
    assert quality["firmware_boundary"] == "verifier_signal_only"
    assert quality["final_language_owner"] == "generation_spine_or_cgpu_critic"
    assert quality["issues"][0]["issue_id"] == "grounding_low"
    assert result.response == "routed through auto"


def test_fast_path_verifier_marks_exhausted_revision_budget_without_owning_language():
    bridge = StubBridge()
    hypervisor = CognitiveHypervisor(
        bridge_factory=lambda: bridge,
        answer_verifier=FailingAnswerVerifier(),
    )

    result = asyncio.run(hypervisor.process_query("simple ping"))

    quality = result.telemetry["reasoning_quality"]

    assert result.decision.route == HypervisorRoute.FAST_PATH
    assert result.decision.budget.critic_passes == 0
    assert quality["status"] == "failed"
    assert quality["critic_revision_required"] is False
    assert quality["budget"] == {
        "critic_passes": 0,
        "revision_passes_required": 1,
        "revision_passes_available": 0,
        "revision_budget_exhausted": True,
    }
    assert quality["firmware_boundary"] == "verifier_signal_only"
    assert quality["final_language_owner"] == "generation_spine_or_cgpu_critic"
    assert result.response == "routed through auto"


def test_hypervisor_routes_safety_constraints_to_safety_path():
    hypervisor = CognitiveHypervisor()
    decision = hypervisor.plan(
        "Explain what to do with a leaked password",
        constraints=["safety_policy_required"],
    )

    assert decision.route == HypervisorRoute.SAFETY_PATH
    assert decision.hemisphere_mode == "both"
    assert decision.budget.critic_passes == 2
    assert "critic_must_validate_before_emit" in decision.constraints


def test_hypervisor_degrades_on_device_timeout():
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: SlowBridge())

    result = asyncio.run(
        hypervisor.process_query(
            "simple ping",
        )
    )

    assert result.bridge_result["device_status"] == "timeout"
    assert result.telemetry["device_isolation"]["status"] == "timeout"
    assert result.telemetry["budget_exhausted"] is True
    assert result.telemetry["degraded"] is True
    degraded_state = result.telemetry["degraded_state"]
    assert degraded_state["schema"] == "synthesus.chal.degraded_state.v1"
    assert degraded_state["trace_id"] == result.decision.trace_id
    assert degraded_state["reason"] == "budget_exhausted"
    assert degraded_state["route"] == "fast_path"
    assert degraded_state["device"] == "chal://hypervisor/hemisphere_bridge"
    assert degraded_state["normal_assistant_path"] is False
    assert degraded_state["legacy_template_leakage_allowed"] is False
    assert result.response == degraded_state["message"]
    assert "[fallback]" not in result.response
    assert "response_template" not in result.response


def test_hypervisor_degrades_on_blocking_sync_device_timeout():
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: BlockingBridge())

    result = asyncio.run(hypervisor.process_query("simple ping"))

    assert result.bridge_result["device_status"] == "timeout"
    assert result.telemetry["budget_exhausted"] is True
    assert result.telemetry["degraded_state"]["reason"] == "budget_exhausted"
    assert result.bridge_result["degraded_state"] == result.telemetry["degraded_state"]


def test_hypervisor_degrades_on_device_fault():
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: FaultBridge())

    result = asyncio.run(hypervisor.process_query("simple ping"))

    assert result.bridge_result["device_status"] == "fault"
    assert "device bus fault" in result.bridge_result["error"]
    assert result.telemetry["device_isolation"]["status"] == "fault"
    assert result.telemetry["budget_exhausted"] is False
    assert result.telemetry["degraded"] is True
    degraded_state = result.telemetry["degraded_state"]
    assert degraded_state["schema"] == "synthesus.chal.degraded_state.v1"
    assert degraded_state["reason"] == "device_fault"
    assert degraded_state["device_status"] == "fault"
    assert degraded_state["error"] == "device bus fault"
    assert result.response == degraded_state["message"]
    assert "Handled:" not in result.response


def test_hypervisor_quarantines_normal_path_legacy_template_surface():
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: LegacyTemplateBridge())

    result = asyncio.run(hypervisor.process_query("simple ping"))

    assert "[module]" not in result.response
    assert "response_template" not in result.response
    assert result.telemetry["template_guard"]["allowed"] is False
    assert result.telemetry["template_guard"]["rewritten"] is True
    assert result.telemetry["template_guard"]["surface"] == "normal"
    assert result.telemetry["degraded"] is True
    degraded_state = result.telemetry["degraded_state"]
    assert degraded_state["reason"] == "legacy_template_quarantine"
    assert degraded_state["device"] == "chal://critic/template_guard"
    assert degraded_state["matched_signatures"] == ["[module]", "response_template", "Handled:"]
    assert degraded_state["legacy_template_leakage_allowed"] is False


def test_hypervisor_labels_safety_template_exception_without_normal_quarantine():
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: SafetyTemplateBridge())

    result = asyncio.run(
        hypervisor.process_query(
            "A user pasted a leaked password",
            constraints=["safety_policy_required"],
        )
    )

    assert "[module] Handled:" in result.response
    assert result.telemetry["template_guard"]["allowed"] is True
    assert result.telemetry["template_guard"]["rewritten"] is False
    assert result.telemetry["template_guard"]["surface"] == "safety"
