from tools.evaluate_organs import OrganScorecard, TraceRecord, _chal_accelerator_coverage, evaluate_quality_gate


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
        "chal_accelerator_coverage": 1.0,
        "consistency_warnings": [],
        "notes": [],
    }
    defaults.update(overrides)
    return OrganScorecard(**defaults)


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
        min_chal_accelerator_coverage=1.0,
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


def test_quality_gate_fails_missing_chal_accelerator_metadata():
    result = evaluate_quality_gate(
        [scorecard(chal_accelerator_coverage=0.75)],
        min_chal_accelerator_coverage=1.0,
    )

    assert result.passed is False
    assert any("CHAL accelerator coverage" in failure for failure in result.failures)


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
            "generator": "organ-triad-replay-v2",
            "chal": {
                "frameId": "chal-organ-1",
                "parentFrameId": "chal-training-session-chat-0",
                "device": "chal://organs/chat/policy_prior",
                "role": "organ_accelerator",
                "route": "organ_training_replay",
                "outputRef": "chat.policy_prior.planning",
            }
        },
    )
    invalid = TraceRecord(
        **base_record,
        replay={"generator": "organ-triad-replay-v2", "chal": {"device": "chal://organs/chat/attention"}},
    )

    assert _chal_accelerator_coverage([valid, invalid]) == 0.5


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
