import asyncio
import copy
import json

from core.hemisphere_bridge import HemisphereBridge
from core.generation.spine import GenerationSpine, SpineInput
from kernel.bridge import FallbackPPBRS
from reasoning.chal import (
    Checkpoint,
    CognitiveTask,
    ExecutionPlan,
    ModuleMessage,
    PPBRSFirmwareSignal,
    TelemetryRecord,
    build_ppbrs_firmware_signal,
)
from core.chal import frames as canonical_frames
from tools.chal_conversation_compare import (
    CASES,
    CONTINUITY_SEQUENCES,
    RegressionThresholds,
    assert_axis_improvements,
    assert_chal_surfaces_are_clean,
    assert_continuity_scorecard,
    assert_reference_scorecard,
    assert_regression_thresholds,
    assert_replay_integrity_scorecard,
    build_axis_improvement_scorecard,
    build_continuity_rows,
    build_continuity_scorecard,
    build_reference_scorecard,
    build_replay_integrity_scorecard,
    build_replay_records,
    build_chal_rows,
    flatten_continuity_rows,
    summarize,
)


def test_chal_frame_records_roundtrip_through_json():
    task = CognitiveTask.from_query(
        "How should PPBRS expose firmware state?",
        character_id="synth",
        domain="reasoning",
        budgets={"latency_ms": 25.0},
        constraints=["do_not_emit_ppbrs_template"],
        trace_id="trace-roundtrip",
    )
    plan = ExecutionPlan(
        plan_id="plan-roundtrip",
        task_id=task.task_id,
        stages=["classify", "handoff_to_generation"],
        route="ppbrs",
        budgets=task.budgets,
        constraints=task.constraints,
        trace_id=task.trace_id,
    )
    message = ModuleMessage(
        message_id="msg-roundtrip",
        trace_id=task.trace_id,
        source="ppbrs",
        target="generation_spine",
        kind="left_hemisphere_firmware_signal",
        payload={"template_context": "internal only"},
        confidence=0.81,
        constraints=task.constraints,
    )
    checkpoint = Checkpoint(
        checkpoint_id="ckpt-roundtrip",
        trace_id=task.trace_id,
        stage="ppbrs_route",
        state={"route": plan.route},
    )
    telemetry = TelemetryRecord(
        trace_id=task.trace_id,
        component="ppbrs",
        latency_ms=1.5,
        confidence=0.81,
        metadata={"route": plan.route},
    )

    encoded = json.dumps(
        {
            "task": task.to_dict(),
            "plan": plan.to_dict(),
            "message": message.to_dict(),
            "checkpoint": checkpoint.to_dict(),
            "telemetry": telemetry.to_dict(),
        },
        sort_keys=True,
    )
    decoded = json.loads(encoded)

    assert CognitiveTask.from_dict(decoded["task"]) == task
    assert ExecutionPlan.from_dict(decoded["plan"]) == plan
    assert ModuleMessage.from_dict(decoded["message"]) == message
    assert Checkpoint.from_dict(decoded["checkpoint"]) == checkpoint
    assert TelemetryRecord.from_dict(decoded["telemetry"]) == telemetry


def test_reasoning_chal_imports_share_canonical_core_frame_boundary():
    assert CognitiveTask is canonical_frames.CognitiveFrameTask
    assert ExecutionPlan is canonical_frames.CognitiveFrameExecutionPlan
    assert ModuleMessage is canonical_frames.CognitiveFrameMessage
    assert Checkpoint is canonical_frames.CognitiveFrameCheckpoint
    assert TelemetryRecord is canonical_frames.CognitiveFrameTelemetry
    assert PPBRSFirmwareSignal is canonical_frames.PPBRSFirmwareSignal
    assert build_ppbrs_firmware_signal is canonical_frames.build_ppbrs_firmware_signal


def test_ppbrs_firmware_signal_roundtrip_validates_trace_ids():
    signal = build_ppbrs_firmware_signal(
        query="Route this through PPBRS",
        module_used="reasoning",
        confidence=1.7,
        matched_pattern="route ppbrs",
    )

    parsed = PPBRSFirmwareSignal.from_dict(json.loads(json.dumps(signal)))

    assert parsed.confidence == 1.0
    assert parsed.to_dict() == signal
    assert parsed.trace_id == parsed.task.trace_id
    assert parsed.module_message.target == "generation_spine"

    drifted = copy.deepcopy(signal)
    drifted["module_message"]["trace_id"] = "trace-drifted"

    try:
        PPBRSFirmwareSignal.from_dict(drifted)
    except ValueError as exc:
        assert "trace IDs must match" in str(exc)
    else:
        raise AssertionError("trace-id drift must fail CHAL firmware deserialization")


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


def test_generation_spine_fallback_is_labeled_degraded_state_without_legacy_signature():
    out = GenerationSpine(models_dir="/tmp/nonexistent-synthesus-models").generate(
        SpineInput(
            query="Explain memory cache hierarchy",
            domain="general",
            source_module="generation_spine_test",
        )
    )

    assert out.final_text
    assert "Generation is in a degraded state" in out.final_text
    assert "[fallback]" not in out.final_text
    assert "response_template" not in out.final_text
    assert out.degraded_state is not None
    assert out.degraded_state["surface"] == "degraded_state"
    assert out.degraded_state["reason"] == "primary_generation_unavailable"
    assert out.degraded_state["legacy_template_signature_present"] is False


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
    assert summary["synthesus5_p95_latency_ms"] >= summary["synthesus5_mean_latency_ms"]
    assert summary["synthesus5_max_latency_ms"] >= summary["synthesus5_p95_latency_ms"]
    assert "grounded_path" in summary["synthesus5_route_latency"]


def test_phase8_comparison_harness_exercises_non_grounded_routes():
    rows = asyncio.run(build_chal_rows())
    routes = {row["synthesus5"]["decision"]["route"] for row in rows}

    assert "grounded_path" in routes
    assert "quad_brain_path" in routes
    assert "safety_path" in routes


def test_phase8_comparison_harness_exercises_business_bot_preset():
    rows = asyncio.run(build_chal_rows())
    business_row = next(row for row in rows if row["case_id"] == "business_bot_task")

    assert business_row["runtime_preset"] == "business_bot"
    assert business_row["synthesus5"]["telemetry"]["runtime_preset"] == "business_bot"
    assert "business_bot_preset" in business_row["synthesus5"]["decision"]["reasons"]
    quad_brain = business_row["synthesus5"]["telemetry"]["quad_brain"]
    cgpu_output = next(output for output in quad_brain["outputs"] if output["role"] == "cgpu_rendering")
    assert cgpu_output["content"]["candidates"][0]["mode"] == "business_bot"
    assert quad_brain["state_contract"]["final_output_ref"] == "critic.selected_response"


def test_phase8_comparison_harness_builds_replay_trace_records():
    rows = asyncio.run(build_chal_rows())
    continuity_rows = asyncio.run(build_continuity_rows())
    continuity_flat_rows = flatten_continuity_rows(continuity_rows)
    records = build_replay_records(rows + continuity_flat_rows)

    assert len(records) == len(rows) + len(continuity_flat_rows)
    assert {record["schema"] for record in records} == {"synthesus.phase8.replay_trace.v1"}
    assert all(record["trace_id"] for record in records)
    assert all("response" not in record["legacy"] for record in records)
    assert all("response" not in record["synthesus5"] for record in records)
    assert all(record["record_hash"] for record in records)
    assert all(record["legacy"]["response_sha256"] for record in records)
    assert all(record["synthesus5"]["response_sha256"] for record in records)
    assert all(record["legacy"]["response_chars"] > 0 for record in records)
    assert all(record["synthesus5"]["response_chars"] > 0 for record in records)
    business_record = next(record for record in records if record["case_id"] == "business_bot_task")
    assert business_record["runtime_preset"] == "business_bot"
    assert business_record["route"] == "quad_brain_path"
    continuity_record = next(record for record in records if record["case_id"] == "business_bot_followup_turn2")
    assert continuity_record["runtime_preset"] == "business_bot"
    assert continuity_record["route"] == "quad_brain_path"


def test_phase8_comparison_harness_builds_replay_integrity_scorecard():
    rows = asyncio.run(build_chal_rows())
    continuity_rows = asyncio.run(build_continuity_rows())
    continuity_flat_rows = flatten_continuity_rows(continuity_rows)
    records = build_replay_records(rows + continuity_flat_rows)
    scorecard = build_replay_integrity_scorecard(records)

    assert scorecard["schema"] == "synthesus.phase8.replay_integrity_scorecard.v1"
    assert scorecard["summary"]["record_count"] == len(records)
    assert scorecard["summary"]["failed_records"] == 0
    assert scorecard["summary"]["records_with_synthesus5_response_hash"] == len(records)
    assert_replay_integrity_scorecard(scorecard)


def test_phase8_replay_integrity_scorecard_reports_tampering():
    rows = asyncio.run(build_chal_rows())
    records = build_replay_records(rows)
    records[0]["synthesus5"]["overall_score"] = 0.0
    scorecard = build_replay_integrity_scorecard(records)

    try:
        assert_replay_integrity_scorecard(scorecard)
    except AssertionError as exc:
        assert f"{records[0]['case_id']} failed record_hash" in str(exc)
    else:
        raise AssertionError("replay integrity gate must fail when a record is tampered")


def test_phase8_comparison_harness_builds_reference_scorecard():
    rows = asyncio.run(build_chal_rows())
    scorecard = build_reference_scorecard(rows)

    assert scorecard["schema"] == "synthesus.phase8.reference_scorecard.v1"
    assert scorecard["summary"]["case_count"] == len(rows)
    assert scorecard["summary"]["failed_cases"] == 0
    assert scorecard["summary"]["passed_cases"] == len(rows)
    assert_reference_scorecard(scorecard)

    business_case = next(case for case in scorecard["cases"] if case["case_id"] == "business_bot_task")
    assert business_case["expected_route"] == "quad_brain_path"
    assert business_case["runtime_preset"] == "business_bot"
    assert set(business_case["quad_brain_roles"]) == {
        "knowledge_grounding",
        "executive_reasoning",
        "cgpu_rendering",
        "critic_metacognition",
    }


def test_phase8_reference_scorecard_reports_failed_checks():
    rows = asyncio.run(build_chal_rows())
    scorecard = build_reference_scorecard(rows)
    scorecard["cases"][0]["checks"]["route"] = False
    scorecard["cases"][0]["passed"] = False

    try:
        assert_reference_scorecard(scorecard)
    except AssertionError as exc:
        assert f"{scorecard['cases'][0]['case_id']} failed route" in str(exc)
    else:
        raise AssertionError("reference scorecard gate must fail when a case check fails")


def test_phase8_comparison_harness_builds_axis_improvement_scorecard():
    rows = asyncio.run(build_chal_rows())
    scorecard = build_axis_improvement_scorecard(rows)

    assert scorecard["schema"] == "synthesus.phase8.axis_improvement_scorecard.v1"
    assert scorecard["summary"]["case_count"] == len(rows)
    assert scorecard["summary"]["cases_with_template_improvement"] == len(rows)
    assert scorecard["summary"]["cases_with_grounding_regression"] == 0
    assert scorecard["summary"]["cases_with_naturalness_regression"] == 0
    assert scorecard["summary"]["cases_with_safety_regression"] == 0
    assert_axis_improvements(scorecard)

    business_case = next(case for case in scorecard["cases"] if case["case_id"] == "business_bot_task")
    assert business_case["axis_deltas"]["template_leakage"] == 1.0
    assert business_case["axis_deltas"]["naturalness"] > 0


def test_phase8_axis_improvement_scorecard_reports_case_regressions():
    rows = asyncio.run(build_chal_rows())
    scorecard = build_axis_improvement_scorecard(rows)
    scorecard["cases"][0]["axis_deltas"]["grounding"] = -0.25

    try:
        assert_axis_improvements(scorecard)
    except AssertionError as exc:
        assert f"{scorecard['cases'][0]['case_id']} regressed grounding" in str(exc)
    else:
        raise AssertionError("axis improvement gate must fail when a case regresses")


def test_phase8_comparison_harness_builds_continuity_scorecard():
    continuity_rows = asyncio.run(build_continuity_rows())
    flat_rows = flatten_continuity_rows(continuity_rows)
    scorecard = build_continuity_scorecard(continuity_rows)

    assert len(continuity_rows) == len(CONTINUITY_SEQUENCES)
    assert len(flat_rows) == sum(len(sequence.turns) for sequence in CONTINUITY_SEQUENCES)
    assert scorecard["schema"] == "synthesus.phase8.continuity_scorecard.v1"
    assert scorecard["summary"]["sequence_count"] == len(CONTINUITY_SEQUENCES)
    assert scorecard["summary"]["turn_count"] == len(flat_rows)
    assert scorecard["summary"]["failed_sequences"] == 0
    assert scorecard["summary"]["synthesus5_template_leaks"] == 0
    assert_continuity_scorecard(scorecard)

    sequence_ids = {case["sequence_id"] for case in scorecard["cases"]}
    assert {
        "npc_persona_continuity",
        "business_bot_followup",
        "safety_secret_followup",
    }.issubset(sequence_ids)

    business_case = next(case for case in scorecard["cases"] if case["sequence_id"] == "business_bot_followup")
    assert business_case["observed_final_route"] == "quad_brain_path"
    assert business_case["runtime_preset"] == "business_bot"
    assert business_case["continuity_term_coverage"] >= 0.66
    assert set(business_case["quad_brain_roles"]) == {
        "knowledge_grounding",
        "executive_reasoning",
        "cgpu_rendering",
        "critic_metacognition",
    }


def test_phase8_continuity_scorecard_reports_sequence_failures():
    continuity_rows = asyncio.run(build_continuity_rows())
    scorecard = build_continuity_scorecard(continuity_rows)
    scorecard["cases"][0]["checks"]["continuity_term_coverage"] = False
    scorecard["cases"][0]["passed"] = False

    try:
        assert_continuity_scorecard(scorecard)
    except AssertionError as exc:
        assert f"{scorecard['cases'][0]['sequence_id']} failed continuity_term_coverage" in str(exc)
    else:
        raise AssertionError("continuity scorecard gate must fail when a sequence check fails")


def test_phase8_comparison_harness_enforces_latency_regression_thresholds():
    rows = asyncio.run(build_chal_rows())
    summary = summarize(rows)

    assert_regression_thresholds(
        summary,
        RegressionThresholds(
            max_mean_latency_ms=1000.0,
            max_p95_latency_ms=1500.0,
            min_score_delta=0.1,
        ),
    )

    try:
        assert_regression_thresholds(
            summary,
            RegressionThresholds(max_mean_latency_ms=0.0),
        )
    except AssertionError as exc:
        assert "mean latency" in str(exc)
    else:
        raise AssertionError("latency regression threshold must fail when set below observed runtime")
