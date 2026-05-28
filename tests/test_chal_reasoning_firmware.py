import asyncio

from core.hemisphere_bridge import HemisphereBridge
from core.generation.spine import GenerationSpine, SpineInput
from kernel.bridge import FallbackPPBRS
from reasoning.chal import build_ppbrs_firmware_signal
from tools.chal_conversation_compare import CASES, assert_chal_surfaces_are_clean, build_chal_rows, summarize


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
    assert "stored template" in out.final_text
    assert "commerce" not in out.final_text


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
    assert "stored template" in result["response"]
    assert "commerce" not in result["response"]
    assert (
        result["state_handoff"]["left_source"] == "python_fallback"
        or result["state_handoff"]["left_source"] == "cpp_kernel"
    )
    assert result["state_handoff"]["signals"][0]["payload"]["firmware_signal"]["trace_id"]


def test_dual_hemi_both_mode_synthesizes_realized_left_firmware():
    bridge = HemisphereBridge(
        kernel_bin="/tmp/nonexistent-zo-kernel",
        left_config={"routes": [{"pattern": "memory cache chal", "module": "chal_memory_controller", "priority": 2.0}]},
        right_handler=lambda prompt, context: {
            "response": "Right hemisphere candidate: CHAL should treat memory and cache as mounted cognitive hardware.",
            "confidence": 0.56,
        },
    )

    result = asyncio.run(
        bridge.route_query(
            "How should CHAL use memory cache hardware?",
            hemisphere="both",
            character_context={"character_id": "synth"},
        )
    )

    assert result["hemisphere_used"] == "both"
    assert result["left_response"]
    assert "hardware hierarchy" in result["left_response"]
    assert "chal_memory_controller" not in result["response"]
    assert result["right_response"]
    assert result["response"]
    assert "Handled:" not in result["response"]
    assert "[fallback]" not in result["response"]


def test_chal_comparison_harness_blocks_legacy_surface_signatures():
    rows = asyncio.run(build_chal_rows())
    assert_chal_surfaces_are_clean(rows)


def test_phase8_comparison_harness_covers_required_categories_and_scores():
    rows = asyncio.run(build_chal_rows())
    summary = summarize(rows)

    assert len(rows) == len(CASES)
    assert {
        "conversation_quality",
        "cross_domain_reasoning",
        "grounded_retrieval",
        "npc_persona_behavior",
        "business_bot_task",
        "safety",
    }.issubset(set(summary["categories"]))
    assert summary["synthesus5_template_leaks"] == 0
    assert summary["legacy_template_leaks"] == len(rows)
    assert summary["synthesus5_mean_score"] > summary["legacy_mean_score"]


def test_phase8_comparison_harness_exercises_non_grounded_routes():
    rows = asyncio.run(build_chal_rows())
    routes = {row["synthesus5"]["decision"]["route"] for row in rows}

    assert "grounded_path" in routes
    assert "quad_brain_path" in routes
    assert "safety_path" in routes
