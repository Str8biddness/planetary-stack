import asyncio

from core.hemisphere_bridge import HemisphereBridge
from core.generation.spine import GenerationSpine, SpineInput
from kernel.bridge import FallbackPPBRS
from reasoning.chal import build_ppbrs_firmware_signal


def test_ppbrs_fallback_emits_chal_firmware_not_surface_text():
    ppbrs = FallbackPPBRS()
    ppbrs.add_route("buy sell trade", "commerce")

    result = ppbrs.route("I want to buy supplies")
    signal = result.metadata["chal_firmware_signal"]

    assert result.response == ""
    assert result.metadata["user_facing"] is False
    assert signal["schema"] == "synthesus.chal.reasoning_firmware.v1"
    assert signal["module_message"]["target"] == "generation_spine"
    assert signal["module_message"]["kind"] == "left_hemisphere_firmware_signal"
    assert signal["execution_plan"]["stages"][-1] == "handoff_to_generation"
    assert "generation_spine_owns_final_wording" in signal["constraints"]


def test_generation_spine_realizes_firmware_without_legacy_template_signature():
    signal = build_ppbrs_firmware_signal(
        query="I want to buy supplies",
        module_used="commerce",
        confidence=0.82,
        matched_pattern="buy sell trade",
    )
    out = GenerationSpine().generate(
        SpineInput(
            query="I want to buy supplies",
            source_module="ppbrs_firmware",
            source_confidence=0.82,
            firmware_signals=[signal],
        )
    )

    assert out.final_text
    assert "Handled:" not in out.final_text
    assert "[fallback]" not in out.final_text
    assert "commerce" in out.final_text


def test_dual_hemi_auto_routes_left_firmware_through_generation_spine():
    bridge = HemisphereBridge(
        kernel_bin="/tmp/nonexistent-zo-kernel",
        left_config={"routes": [{"pattern": "buy sell trade", "module": "commerce", "priority": 2.0}]},
        right_handler=lambda prompt, context: {
            "response": "Right hemisphere narrative candidate.",
            "confidence": 0.2,
        },
    )

    result = asyncio.run(
        bridge.route_query(
            "I want to buy supplies",
            hemisphere="auto",
            character_context={"character_id": "merchant"},
        )
    )

    assert result["hemisphere_used"] == "left"
    assert "Handled:" not in result["response"]
    assert "[fallback]" not in result["response"]
    assert "commerce" in result["response"]
    assert (
        result["state_handoff"]["left_source"] == "python_fallback"
        or result["state_handoff"]["left_source"] == "cpp_kernel"
    )
    assert result["state_handoff"]["signals"][0]["payload"]["firmware_signal"]["trace_id"]
