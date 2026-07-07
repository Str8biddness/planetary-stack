from cognitive import cognitive_engine
from cognitive.cognitive_engine import CognitiveEngine


class _NoopPatternEngine:
    def __init__(self, *args, **kwargs):
        pass

    async def generate_response(self, *args, **kwargs):
        return None


def _engine(monkeypatch, escalation_threshold: float = 0.55) -> CognitiveEngine:
    monkeypatch.setattr(cognitive_engine, "PatternEngine", _NoopPatternEngine)
    engine = CognitiveEngine(
        character_id="synth",
        bio={"name": "Synth", "role": "guard"},
        patterns={
            "synthetic_patterns": [],
            "generic_patterns": [],
            "fallback": "I am Synth. Could you rephrase?",
        },
    )
    engine.gate.threshold = escalation_threshold
    return engine


def test_cognitive_engine_labels_character_fallback_as_explicit_npc_script(monkeypatch):
    result = _engine(monkeypatch, escalation_threshold=1.1).process_query("player-1", "zxqv orbital accounting")

    surface = result["debug"]["template_surface"]

    assert result["source"] == "fallback"
    assert result["response"] == "I am Synth. Could you rephrase?"
    assert surface["surface"] == "explicit_npc_script"
    assert surface["boundary"] == "cognitive_engine_fallback"
    assert surface["source"] == "character_fallback"
    assert surface["user_facing"] is True
    assert surface["legacy_template_signature_present"] is False


def test_cognitive_engine_labels_escalation_stall_as_explicit_npc_script(monkeypatch):
    result = _engine(monkeypatch).process_query(
        "player-1",
        "why would a desperate hypothetical city collapse immediately if trade failed",
        thinking_layer_available=False,
    )

    surface = result["debug"]["template_surface"]

    assert result["source"] == "fallback"
    assert result["escalation"]["should_escalate"] is True
    assert surface["surface"] == "explicit_npc_script"
    assert surface["boundary"] == "cognitive_engine_fallback"
    assert surface["source"] == "escalation_stall"
    assert surface["user_facing"] is True
    assert surface["legacy_template_signature_present"] is False
