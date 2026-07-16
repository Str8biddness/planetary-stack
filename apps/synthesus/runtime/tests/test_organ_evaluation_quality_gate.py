import hashlib
import json

from tools.evaluate_organs import (
    CHAL_ACCELERATOR_GENERATOR,
    OrganScorecard,
    SHARED_BACKBONE_SCHEMA,
    TraceRecord,
    assert_organ_replay_integrity,
    build_organ_replay_integrity_scorecard,
    build_organ_replay_records,
    _candidate_critic_coverage,
    _chal_accelerator_coverage,
    _replay_identity_coverage,
    evaluate_quality_gate,
)


def backbone_contract(domain="chat", organ="policy_prior", **overrides):
    contract = {
        "schema": SHARED_BACKBONE_SCHEMA,
        "contractVersion": "shared-organ-backbone-v1",
        "domain": domain,
        "organ": organ,
        "width": 12,
        "scopes": ["state", "action", "trajectory", "multifocus"],
        "device": f"chal://organs/{domain}/{organ}",
    }
    contract.update(overrides)
    contract["contractHash"] = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return contract


def scorecard(**overrides):
    defaults = {
        "domain": "chat",
        "organ": "policy_prior",
        "trace_count": 8,
        "model_path": "/tmp/chat_policy_prior.pkl",
        "model_exists": True,
        "train_metric": 0.9,
        "validation_metric": 0.8,
        "baseline_metric": 0.5,
        "metric_name": "accuracy",
        "scientific_consistency": 1.0,
        "replay_coverage": 1.0,
        "replay_identity_coverage": 1.0,
        "chal_accelerator_coverage": 1.0,
        "candidate_critic_coverage": 1.0,
        "consistency_warnings": [],
        "notes": [],
    }
    defaults.update(overrides)
    return OrganScorecard(**defaults)


def replay_record(**overrides):
    record = {
        "schema": "organ_training_replay.v1",
        "generator": CHAL_ACCELERATOR_GENERATOR,
        "seed": 950907,
        "scenarioId": "chat-0-policy-prior",
        "step": 1,
        "domain": "chat",
        "organ": "policy_prior",
        "phase": "planning",
        "device": "chal://organs/chat/policy_prior",
        "route": "organ_training_replay",
        "candidateRefs": [
            "chat.policy_prior.planning.candidate.0",
            "chat.policy_prior.planning.candidate.1",
        ],
        "selectedCandidateRef": "chat.policy_prior.planning.candidate.1",
        "accepted": True,
        "quality": 0.91,
        "backbone": backbone_contract(),
    }
    record.update(overrides)
    record["recordHash"] = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return record


def trace_record_with_replay(**overrides):
    base_record = {
        "domain": "chat",
        "phase": "planning",
        "organ": "policy_prior",
        "state_features": [0.1, 0.2],
        "action_features": [[0.3, 0.4]],
        "multi_focus_weights": [1.0],
        "trajectory_features": [0.5],
        "chosen_index": 1,
        "quality": 0.91,
        "outcome": {},
        "replay": {
            "generator": CHAL_ACCELERATOR_GENERATOR,
            "seed": 950907,
            "scenarioId": "chat-0-policy-prior",
            "step": 1,
            "simulatedTime": "2026-05-30T12:00:00.000Z",
            "record": replay_record(),
            "chal": {
                "frameId": "chal-organ-1",
                "parentFrameId": "chal-training-session-chat-0",
                "device": "chal://organs/chat/policy_prior",
                "role": "organ_accelerator",
                "route": "organ_training_replay",
                "outputRef": "chat.policy_prior.planning",
                "candidateRefs": [
                    "chat.policy_prior.planning.candidate.0",
                    "chat.policy_prior.planning.candidate.1",
                ],
                "selectedCandidateRef": "chat.policy_prior.planning.candidate.1",
                "criticFeedback": {
                    "source": "teacher_trace_outcome",
                    "feedbackRef": "chat.policy_prior.planning.critic_feedback",
                    "accepted": True,
                    "quality": 0.91,
                },
                "backbone": backbone_contract(),
            },
        },
    }
    base_record.update(overrides)
    return TraceRecord(**base_record)


def test_quality_gate_passes_complete_replayable_scorecards():
    result = evaluate_quality_gate(
        [
            scorecard(),
            scorecard(
                domain="gm",
                organ="attention",
                metric_name="mse",
                validation_metric=0.02,
                baseline_metric=0.05,
            ),
        ],
        min_replay_coverage=1.0,
        min_replay_identity_coverage=1.0,
        min_chal_accelerator_coverage=1.0,
        min_candidate_critic_coverage=1.0,
        min_scientific_consistency=1.0,
        fail_under_baseline=True,
        fail_missing_models=True,
    )

    assert result.passed is True
    assert result.failures == []


def test_quality_gate_fails_low_replay_and_consistency():
    result = evaluate_quality_gate(
        [scorecard(replay_coverage=0.5, scientific_consistency=0.75)],
        min_replay_coverage=0.95,
        min_scientific_consistency=0.9,
    )

    assert result.passed is False
    assert any("replay coverage" in failure for failure in result.failures)
    assert any("scientific consistency" in failure for failure in result.failures)


def test_quality_gate_fails_low_replay_identity():
    result = evaluate_quality_gate(
        [scorecard(replay_identity_coverage=0.75)],
        min_replay_identity_coverage=1.0,
    )

    assert result.passed is False
    assert any("replay identity coverage" in failure for failure in result.failures)


def test_quality_gate_fails_missing_chal_accelerator_metadata():
    result = evaluate_quality_gate(
        [scorecard(chal_accelerator_coverage=0.75)],
        min_chal_accelerator_coverage=1.0,
    )

    assert result.passed is False
    assert any("CHAL accelerator coverage" in failure for failure in result.failures)


def test_quality_gate_fails_missing_candidate_critic_metadata():
    result = evaluate_quality_gate(
        [scorecard(candidate_critic_coverage=0.75)],
        min_candidate_critic_coverage=1.0,
    )

    assert result.passed is False
    assert any("candidate/critic coverage" in failure for failure in result.failures)


def test_chal_accelerator_coverage_requires_matching_device_frame():
    base_record = {
        "domain": "chat",
        "phase": "planning",
        "organ": "policy_prior",
        "state_features": [],
        "action_features": [],
        "multi_focus_weights": [],
        "trajectory_features": [],
        "chosen_index": 0,
        "quality": 1.0,
        "outcome": {},
    }
    valid = TraceRecord(
        **base_record,
        replay={
            "generator": CHAL_ACCELERATOR_GENERATOR,
            "chal": {
                "frameId": "chal-organ-1",
                "parentFrameId": "chal-training-session-chat-0",
                "device": "chal://organs/chat/policy_prior",
                "role": "organ_accelerator",
                "route": "organ_training_replay",
                "outputRef": "chat.policy_prior.planning",
                "candidateRefs": [
                    "chat.policy_prior.planning.candidate.0",
                    "chat.policy_prior.planning.candidate.1",
                ],
                "selectedCandidateRef": "chat.policy_prior.planning.candidate.1",
                "criticFeedback": {
                    "source": "teacher_trace_outcome",
                    "feedbackRef": "chat.policy_prior.planning.critic_feedback",
                    "accepted": True,
                    "quality": 0.91,
                },
                "backbone": backbone_contract(),
            },
        },
    )
    invalid = TraceRecord(
        **base_record,
        replay={"generator": CHAL_ACCELERATOR_GENERATOR, "chal": {"device": "chal://organs/chat/attention"}},
    )

    assert _chal_accelerator_coverage([valid, invalid]) == 0.5


def test_candidate_critic_coverage_requires_selected_candidate_and_feedback():
    base_record = {
        "domain": "chat",
        "phase": "planning",
        "organ": "policy_prior",
        "state_features": [],
        "action_features": [],
        "multi_focus_weights": [],
        "trajectory_features": [],
        "chosen_index": 0,
        "quality": 1.0,
        "outcome": {},
    }
    valid = TraceRecord(
        **base_record,
        replay={
            "generator": CHAL_ACCELERATOR_GENERATOR,
            "chal": {
                "candidateRefs": [
                    "chat.policy_prior.planning.candidate.0",
                    "chat.policy_prior.planning.candidate.1",
                ],
                "selectedCandidateRef": "chat.policy_prior.planning.candidate.1",
                "criticFeedback": {
                    "source": "teacher_trace_outcome",
                    "feedbackRef": "chat.policy_prior.planning.critic_feedback",
                    "accepted": True,
                    "quality": 0.91,
                },
                "backbone": backbone_contract(),
            },
        },
    )
    invalid = TraceRecord(
        **base_record,
        replay={
            "generator": CHAL_ACCELERATOR_GENERATOR,
            "chal": {
                "candidateRefs": ["chat.policy_prior.planning.candidate.0"],
                "selectedCandidateRef": "chat.policy_prior.planning.candidate.9",
                "criticFeedback": {"source": "teacher_trace_outcome", "accepted": True, "quality": 0.91},
            },
        },
    )

    assert _candidate_critic_coverage([valid, invalid]) == 0.5


def test_replay_identity_coverage_requires_matching_hash_and_compact_record():
    base_record = {
        "domain": "chat",
        "phase": "planning",
        "organ": "policy_prior",
        "state_features": [],
        "action_features": [],
        "multi_focus_weights": [],
        "trajectory_features": [],
        "chosen_index": 0,
        "quality": 1.0,
        "outcome": {},
    }
    valid = TraceRecord(
        **base_record,
        replay={
            "generator": CHAL_ACCELERATOR_GENERATOR,
            "record": replay_record(),
        },
    )
    tampered = TraceRecord(
        **base_record,
        replay={
            "generator": CHAL_ACCELERATOR_GENERATOR,
            "record": {
                **replay_record(),
                "selectedCandidateRef": "chat.policy_prior.planning.candidate.0",
            },
        },
    )

    assert _replay_identity_coverage([valid, tampered]) == 0.5


def test_build_organ_replay_records_preserves_compact_bounded_identity():
    compact_records = build_organ_replay_records([trace_record_with_replay()])

    assert len(compact_records) == 1
    record = compact_records[0]
    expected_hash = hashlib.sha256(
        json.dumps(
            {key: value for key, value in record.items() if key != "recordHash"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert record["schema"] == "synthesus.organ_replay_trace.v1"
    assert record["recordHash"] == expected_hash
    assert record["sourceRecordHash"] == replay_record()["recordHash"]
    assert record["device"] == "chal://organs/chat/policy_prior"
    assert record["selectedCandidateRef"] == "chat.policy_prior.planning.candidate.1"
    assert record["backbone"]["schema"] == SHARED_BACKBONE_SCHEMA
    assert record["backbone"]["domain"] == "chat"
    assert record["backbone"]["organ"] == "policy_prior"
    assert record["backbone"]["device"] == "chal://organs/chat/policy_prior"
    assert record["backbone"]["contractHash"] == backbone_contract()["contractHash"]
    assert "state_features" not in record
    assert "action_features" not in record
    assert "trajectory_features" not in record


def test_organ_replay_integrity_scorecard_rejects_tampered_compact_source():
    valid = trace_record_with_replay()
    tampered = trace_record_with_replay(
        replay={
            **trace_record_with_replay().replay,
            "record": {
                **replay_record(),
                "selectedCandidateRef": "chat.policy_prior.planning.candidate.0",
            },
        }
    )

    scorecard = build_organ_replay_integrity_scorecard([valid])
    assert scorecard.passed is True
    assert scorecard.total_chal_records == 1
    assert scorecard.stored_records == 1
    assert_organ_replay_integrity(scorecard)

    failed = build_organ_replay_integrity_scorecard([valid, tampered])
    assert failed.passed is False
    assert failed.total_chal_records == 2
    assert any("record hash mismatch" in failure for failure in failed.failures)


def test_organ_replay_integrity_scorecard_rejects_tampered_backbone_contract():
    tampered_contract = backbone_contract(width=16)
    tampered_contract["contractHash"] = "not-the-right-hash"
    tampered = trace_record_with_replay(
        replay={
            **trace_record_with_replay().replay,
            "record": replay_record(backbone=tampered_contract),
            "chal": {
                **trace_record_with_replay().replay["chal"],
                "backbone": tampered_contract,
            },
        }
    )

    failed = build_organ_replay_integrity_scorecard([tampered])

    assert failed.passed is False
    assert any("shared backbone" in failure for failure in failed.failures)


def test_organ_replay_integrity_scorecard_rejects_record_chal_candidate_drift():
    source = trace_record_with_replay()
    drifted = trace_record_with_replay(
        replay={
            **source.replay,
            "chal": {
                **source.replay["chal"],
                "selectedCandidateRef": "chat.policy_prior.planning.candidate.0",
                "criticFeedback": {
                    **source.replay["chal"]["criticFeedback"],
                    "accepted": False,
                },
            },
        }
    )

    failed = build_organ_replay_integrity_scorecard([drifted])

    assert failed.passed is False
    assert failed.stored_records == 0
    assert any("record/CHAL selected candidate mismatch" in failure for failure in failed.failures)


def test_quality_gate_compares_metric_direction_to_baseline():
    result = evaluate_quality_gate(
        [
            scorecard(
                domain="chat",
                organ="policy_prior",
                metric_name="accuracy",
                validation_metric=0.4,
                baseline_metric=0.6,
            ),
            scorecard(
                domain="gm",
                organ="attention",
                metric_name="mse",
                validation_metric=0.12,
                baseline_metric=0.04,
            ),
        ],
        fail_under_baseline=True,
    )

    assert result.passed is False
    assert len(result.failures) == 2
