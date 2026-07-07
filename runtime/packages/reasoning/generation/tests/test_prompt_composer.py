"""Tests for the per-turn PromptComposer: soft steering vs hard enforcement."""
from generation.prompt_composer import PromptComposer, BASE_IDENTITY


def test_bare_turn_is_lean_identity_only():
    r = PromptComposer().compose(query="hi")
    assert "Synthesus" in r.system_prompt
    assert not r.grounded
    # hard floor is always present; must_ground is NOT asserted with no retrieval
    assert r.enforcement == {"must_not_leak": True, "must_be_safe": True}
    assert r.approx_tokens < 90  # stays lean (identity ~70 tok; guard still catches real bloat)


def test_grounding_injects_context_and_hard_contract():
    g = [{"source": "auth.py", "text": "Sessions use JWT tokens in an httpOnly cookie."},
         {"source": "db.py", "text": "Postgres is the primary datastore."}]
    r = PromptComposer().compose(query="how are sessions handled?", grounding=g)
    assert r.grounded
    assert "[auth.py]" in r.system_prompt and "httpOnly cookie" in r.system_prompt
    assert r.enforcement["must_ground"] is True          # enforced downstream, not by the model
    assert r.enforcement["sources"] == ["auth.py", "db.py"]


def test_grounding_respects_char_budget():
    c = PromptComposer(grounding_char_budget=120)
    r = c.compose(query="q", grounding=[{"source": "x", "text": "Z" * 500}])
    assert r.system_prompt.count("Z") == 120           # truncated to budget, not the full 500


def test_persona_and_constraints_split_soft_and_hard():
    r = PromptComposer().compose(
        query="q",
        persona={"voice": "terse, technical"},
        constraints={"format": "bullet points", "max_words": 80},
    )
    # soft steering lives in the prompt
    assert "terse, technical" in r.system_prompt
    assert "bullet points" in r.system_prompt
    # the hard rule is ALSO mirrored into the enforcement contract
    assert r.enforcement["max_words"] == 80


def test_identity_is_the_synthesus_base():
    assert "Synthesus" in BASE_IDENTITY


def test_inline_grounding_false_enforces_without_duplicating_text():
    g = [{"source": "auth.py", "text": "Sessions use JWT tokens in an httpOnly cookie."}]
    r = PromptComposer().compose(query="q", grounding=g, inline_grounding=False)
    # the retrieved TEXT is not inlined (it lives in the user prompt), but...
    assert "httpOnly cookie" not in r.system_prompt
    assert "Knowledge context has been provided" in r.system_prompt   # discipline line
    assert r.enforcement["must_ground"] is True                        # ...the contract still holds
    assert r.enforcement["sources"] == ["auth.py"]
