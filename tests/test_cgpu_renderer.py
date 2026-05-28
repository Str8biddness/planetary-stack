from reasoning.generation import CGPUFrame, CGPURenderer, GenerationTrace, ResponsePlan
from reasoning.generation.surface_realizer import RealizationResult


def _plan(**overrides):
    values = {
        "intent": "inform",
        "style": "direct",
        "safety_level": 0.3,
        "target_length": 64,
        "key_points": ["CHAL keeps truth in grounded state"],
        "required_phrases": ["safety arbitration"],
        "forbidden_phrases": [],
        "domain": "general",
    }
    values.update(overrides)
    return ResponsePlan(**values)


def test_cgpu_frame_renders_multiple_grounded_candidates_with_trace():
    frame = CGPUFrame.create(
        query="Explain CGPU rendering",
        plan=_plan(),
        grounded_state={"facts": ["CHAL keeps truth in grounded state"]},
        candidate_count=3,
        critic_passes=1,
        constraints=["ground_response_in_mounted_knowledge"],
        provenance=[{"source": "kc://rom/cgpu"}],
    )

    output = CGPURenderer().render(frame)

    assert output.device == "chal://cgpu/render"
    assert output.kind == "candidate_set"
    assert len(output.candidates) == 3
    assert output.selected_text
    assert "CHAL keeps truth in grounded state" in output.selected_text
    assert "safety arbitration" in output.selected_text
    assert output.trace["grounding_required"] is True
    assert output.trace["safety_arbitration_required"] is True
    assert output.trace["provenance"] == [{"source": "kc://rom/cgpu"}]


def test_cgpu_persona_mode_renders_character_candidate():
    frame = CGPUFrame.create(
        query="Reply as an NPC",
        plan=_plan(style="npc", domain="gm_dialogue"),
        grounded_state={"facts": ["The gate is sealed until dawn"]},
        mode="npc",
        persona={"name": "Archivist", "stance": "cautious"},
        candidate_count=2,
    )

    output = CGPURenderer().render(frame)

    assert output.selected_text.startswith("Archivist")
    assert "The gate is sealed until dawn" in output.selected_text


def test_cgpu_business_mode_renders_concise_action_surface():
    frame = CGPUFrame.create(
        query="What should the operator do?",
        plan=_plan(key_points=["Restart only the isolated worker"], required_phrases=["confirm first"]),
        grounded_state={"facts": ["Restart only the isolated worker"]},
        mode="business_bot",
        candidate_count=2,
    )

    output = CGPURenderer().render(frame)

    assert output.selected_text.startswith(("Direct answer:", "Recommended next step:"))
    assert "Restart only the isolated worker" in output.selected_text
    assert "confirm first" in output.selected_text


def test_cgpu_critic_rewrites_missing_required_content():
    class IncompleteRealizer:
        def realize(self, request):
            return RealizationResult(
                text="CGPU renders candidates",
                trace=GenerationTrace(text="CGPU renders candidates"),
            )

    frame = CGPUFrame.create(
        query="Explain the contract",
        plan=_plan(
            key_points=[],
            required_phrases=["critic feedback loop"],
        ),
        grounded_state={"facts": ["CGPU renders candidates"]},
        candidate_count=1,
        critic_passes=1,
    )

    output = CGPURenderer(realizer=IncompleteRealizer()).render(frame)
    candidate = output.candidates[0]

    assert candidate.rewrite_count == 1
    assert candidate.accepted is True
    assert "critic feedback loop" in candidate.text


def test_cgpu_blocks_forbidden_candidate_and_does_not_select_it():
    frame = CGPUFrame.create(
        query="Render unsafe text",
        plan=_plan(
            key_points=[],
            required_phrases=[],
            forbidden_phrases=["leak secret"],
        ),
        grounded_state={"facts": ["leak secret"]},
        candidate_count=1,
        critic_passes=1,
    )

    output = CGPURenderer().render(frame)

    assert output.selected_candidate_id is None
    assert output.selected_text == ""
    assert output.candidates[0].blocked is True
    assert "no_candidate_passed_critic" in output.warnings
