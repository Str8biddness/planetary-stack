import asyncio

from core.chal.hypervisor import CognitiveHypervisor, HypervisorRoute


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
