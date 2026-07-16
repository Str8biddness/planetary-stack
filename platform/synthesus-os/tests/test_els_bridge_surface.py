import json
from pathlib import Path

from els_bridge import ELSBridge


def test_els_candidate_export_is_non_user_facing_writeback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    patterns_path = tmp_path / "candidate_patterns.json"
    bridge = ELSBridge(
        db_path=str(tmp_path / "interactions.db"),
        patterns_path=str(patterns_path),
    )

    bridge.capture(
        character_id="atlas",
        user_input="How should Atlas greet a returning scholar?",
        character_response="Welcome back, scholar.",
        outcome_success=True,
    )

    exported = json.loads(patterns_path.read_text())
    surface = exported[0]["template_surface"]

    assert surface["surface"] == "writeback_candidate"
    assert surface["boundary"] == "els_candidate_writeback"
    assert surface["user_facing"] is False
    assert surface["legacy_template_signature_present"] is False


def test_els_integrated_pattern_carries_writeback_boundary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bridge = ELSBridge(
        db_path=str(tmp_path / "interactions.db"),
        patterns_path=str(tmp_path / "candidate_patterns.json"),
    )

    added = bridge.integrate_patterns(
        character_id="atlas",
        approved=[
            {
                "id": "candidate-1",
                "trigger": "returning scholar",
                "response_template": "Welcome back, scholar.",
                "score": 0.8,
            }
        ],
    )

    assert added == 1
    patterns = json.loads(Path("data/patterns.json").read_text())
    surface = patterns[0]["metadata"]["template_surface"]

    assert surface["boundary"] == "els_candidate_writeback"
    assert surface["user_facing"] is False
