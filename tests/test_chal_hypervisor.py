import asyncio
import time

from core.chal.hypervisor import CognitiveHypervisor, HypervisorRoute
from core.chal.quad_brain import QuadBrainRole


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
    assert quad_trace["selected_source"] == "critic_metacognition"
    assert "routed through both" in result.response
    assert result.bridge_result["quad_brain_arbitration"]["trace_id"] == result.decision.trace_id


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
    assert result.response


def test_hypervisor_degrades_on_blocking_sync_device_timeout():
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: BlockingBridge())

    result = asyncio.run(hypervisor.process_query("simple ping"))

    assert result.bridge_result["device_status"] == "timeout"
    assert result.telemetry["budget_exhausted"] is True


def test_hypervisor_degrades_on_device_fault():
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: FaultBridge())

    result = asyncio.run(hypervisor.process_query("simple ping"))

    assert result.bridge_result["device_status"] == "fault"
    assert "device bus fault" in result.bridge_result["error"]
    assert result.telemetry["device_isolation"]["status"] == "fault"
    assert result.telemetry["budget_exhausted"] is False
    assert result.telemetry["degraded"] is True


def test_hypervisor_quarantines_normal_path_legacy_template_surface():
    hypervisor = CognitiveHypervisor(bridge_factory=lambda: LegacyTemplateBridge())

    result = asyncio.run(hypervisor.process_query("simple ping"))

    assert "[module]" not in result.response
    assert "response_template" not in result.response
    assert result.telemetry["template_guard"]["allowed"] is False
    assert result.telemetry["template_guard"]["rewritten"] is True
    assert result.telemetry["template_guard"]["surface"] == "normal"
    assert result.telemetry["degraded"] is True


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
