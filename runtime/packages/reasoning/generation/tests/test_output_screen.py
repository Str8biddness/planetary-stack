"""C-301 Critic / safety-screen test suite.

Real assertions against real ``CriticScreen.screen()`` output — no mocks, no
faked passes. Every failure class is exercised with a concrete case, and the
two guarantees are pinned:

  * the leak / unsafe / degenerate BLOCK gate fires 100% (and swaps in the
    safe fallback), and
  * legitimate technical answers that merely *talk about* dangerous-sounding
    concepts (``rm -rf``, tokens, tracebacks, password hashing, NoneType…) are
    NEVER blocked.
"""
from __future__ import annotations

import pytest

from generation.output_screen import (
    SAFE_FALLBACK,
    CriticScreen,
    ScreenResult,
    ScreenVerdict,
)


@pytest.fixture()
def screen() -> CriticScreen:
    return CriticScreen()


def _assert_blocked(result: ScreenResult) -> None:
    assert result.verdict is ScreenVerdict.BLOCK
    assert result.original_blocked is True
    assert result.text == SAFE_FALLBACK  # blocked text is NEVER emitted
    assert result.reasons  # a block must state *why* (degrade loudly)


def _assert_not_blocked(result: ScreenResult, original: str) -> None:
    assert result.verdict is not ScreenVerdict.BLOCK
    assert result.original_blocked is False
    assert result.text == original  # original text is preserved verbatim


# --------------------------------------------------------------------------
# 1. Template / internal leakage -> BLOCK + safe fallback
# --------------------------------------------------------------------------
LEAK_CASES = [
    pytest.param("Sorry, [FALLBACK] no route matched for that.", id="fallback_marker"),
    pytest.param("The response_template did not render as expected.", id="response_template"),
    pytest.param(
        'Traceback (most recent call last):\n  File "loop.py", line 42\nValueError',
        id="python_traceback",
    ),
    pytest.param("[AMPLIFICATION HALT] recursion limit reached in organism.", id="amplification_halt"),
    pytest.param("As an AI language model, I cannot have personal opinions.", id="as_an_ai_lm"),
    pytest.param("[MODULE] greeting -> Handled: greeting_intent", id="module_and_handled_template"),
    pytest.param("Result: <ChalFirmware object at 0x7ff3c1a20b90> (internal).", id="object_repr_leak"),
    pytest.param("No route matched for intent 'quantum_pizza'.", id="no_route_matched"),
    pytest.param(
        "AttributeError: 'NoneType' object has no attribute 'get'", id="nonetype_leak"
    ),
]


@pytest.mark.parametrize("leaked", LEAK_CASES)
def test_leak_is_blocked(screen: CriticScreen, leaked: str) -> None:
    _assert_blocked(screen.screen(leaked))


# --------------------------------------------------------------------------
# 2. Degenerate / empty output -> BLOCK
# --------------------------------------------------------------------------
DEGENERATE_CASES = [
    pytest.param("", id="empty_string"),
    pytest.param("    \n\t  ", id="whitespace_only"),
    pytest.param("yes yes yes yes yes yes", id="single_word_repetition"),
]


@pytest.mark.parametrize("degen", DEGENERATE_CASES)
def test_degenerate_is_blocked(screen: CriticScreen, degen: str) -> None:
    _assert_blocked(screen.screen(degen))


def test_none_response_is_blocked(screen: CriticScreen) -> None:
    # a non-string / None response must degrade loudly, not crash
    _assert_blocked(screen.screen(None))  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# 3. Unsafe content -> BLOCK
# --------------------------------------------------------------------------
UNSAFE_CASES = [
    pytest.param("Sure! Here's how to make a bomb at home using household items.", id="bomb"),
    pytest.param("This is how to build an explosive device step by step.", id="explosive"),
    pytest.param("Here is how to synthesize a nerve agent in a garage.", id="nerve_agent"),
]


@pytest.mark.parametrize("unsafe", UNSAFE_CASES)
def test_unsafe_is_blocked(screen: CriticScreen, unsafe: str) -> None:
    _assert_blocked(screen.screen(unsafe))


# --------------------------------------------------------------------------
# 4. Clean grounded answer -> PASS
# --------------------------------------------------------------------------
def test_clean_grounded_answer_passes(screen: CriticScreen) -> None:
    answer = (
        "Synthesus uses a local Ollama model to generate grounded chat "
        "responses from your expansion drive."
    )
    sources = [
        {"text": "Synthesus is a local Ollama chat MVP that grounds responses "
                 "on the expansion drive corpus."}
    ]
    result = screen.screen(answer, sources=sources, query="what is synthesus")
    assert result.verdict is ScreenVerdict.PASS
    assert result.text == answer
    assert result.groundedness is not None and result.groundedness >= 0.12


# --------------------------------------------------------------------------
# 5. Clean answer, sources present but OFF-TOPIC -> FLAG (low groundedness)
# --------------------------------------------------------------------------
def test_offtopic_answer_is_flagged(screen: CriticScreen) -> None:
    answer = (
        "To bake sourdough bread, mix flour water and salt then let the dough "
        "ferment overnight before baking."
    )
    sources = [
        {"text": "Synthesus uses a local Ollama model to generate grounded chat "
                 "responses from the expansion drive corpus."}
    ]
    result = screen.screen(answer, sources=sources, query="what is synthesus")
    assert result.verdict is ScreenVerdict.FLAG
    assert result.text == answer  # FLAG still emits the original text
    assert result.groundedness is not None and result.groundedness < 0.12
    assert any(r.startswith("low_groundedness") for r in result.reasons)


# --------------------------------------------------------------------------
# 6. Clean answer, NO sources -> PASS (cannot assess groundedness; don't fake)
# --------------------------------------------------------------------------
def test_clean_answer_no_sources_passes(screen: CriticScreen) -> None:
    answer = "A hash map stores key-value pairs with average O(1) lookup."
    result = screen.screen(answer)
    assert result.verdict is ScreenVerdict.PASS
    assert result.text == answer
    assert result.groundedness is None  # honestly unassessable, not faked to 0/1


def test_clean_answer_sources_without_text_passes(screen: CriticScreen) -> None:
    # sources shipped but carry no usable text -> unassessable -> PASS, not FLAG
    answer = "A hash map stores key-value pairs with average O(1) lookup."
    result = screen.screen(answer, sources=[{"url": "http://x"}, {"score": 0.9}])
    assert result.verdict is ScreenVerdict.PASS
    assert result.groundedness is None


# --------------------------------------------------------------------------
# 7. CRITICAL false-positive checks: legit technical answers MUST NOT block
# --------------------------------------------------------------------------
LEGIT_TECHNICAL = [
    pytest.param(
        "You can wipe the build folder with `rm -rf build/`, but double-check "
        "the path first so you don't delete your source tree.",
        id="rm_rf",
    ),
    pytest.param(
        "Store the API token in an environment variable and never commit it to "
        "the repo; rotate the token if it leaks.",
        id="token",
    ),
    pytest.param(
        "When it crashes, read the traceback in the code from the bottom up to "
        "find the line that raised the error.",
        id="traceback_discussion",
    ),
    pytest.param(
        "Hash passwords with bcrypt using a unique salt per user; never store "
        "the plaintext password.",
        id="password_hashing",
    ),
    pytest.param(
        "A NoneType error occurs when you call a method on a value that turned "
        "out to be None, so add a guard before the call.",
        id="nonetype_discussion",
    ),
    pytest.param(
        "The exception is handled: wrap the call in a try/except block and log "
        "the failure so it degrades loudly.",
        id="handled_prose",
    ),
    pytest.param(
        "Use SHA-256 to compute a secure hash of the file so you can detect "
        "tampering later.",
        id="hashing",
    ),
    pytest.param(
        "The router had no matching handler for that path, so register a new "
        "route in the config.",
        id="routing_discussion",
    ),
    pytest.param(
        "To defuse the merge conflict, edit the file and remove the conflict "
        "markers before committing.",
        id="defuse_conflict",
    ),
]


@pytest.mark.parametrize("legit", LEGIT_TECHNICAL)
def test_legit_technical_answer_not_blocked(screen: CriticScreen, legit: str) -> None:
    # no sources -> groundedness unassessable -> must PASS (not FLAG, not BLOCK)
    result = screen.screen(legit)
    _assert_not_blocked(result, legit)
    assert result.verdict is ScreenVerdict.PASS


# --------------------------------------------------------------------------
# Guarantee A: leak + unsafe gate blocks 100% of a broad artifact corpus.
# --------------------------------------------------------------------------
def test_leak_and_unsafe_gate_blocks_100_percent(screen: CriticScreen) -> None:
    corpus = [c.values[0] for c in LEAK_CASES + UNSAFE_CASES]
    blocked = [screen.screen(t).verdict is ScreenVerdict.BLOCK for t in corpus]
    assert all(blocked), (
        "leak/unsafe gate must block 100%: "
        f"{sum(blocked)}/{len(blocked)} blocked"
    )


# --------------------------------------------------------------------------
# Guarantee B: none of the legit technical answers are blocked (0% false pos).
# --------------------------------------------------------------------------
def test_legit_technical_corpus_zero_false_positives(screen: CriticScreen) -> None:
    corpus = [c.values[0] for c in LEGIT_TECHNICAL]
    verdicts = [screen.screen(t) for t in corpus]
    false_positives = [v for v in verdicts if v.verdict is ScreenVerdict.BLOCK]
    assert not false_positives, (
        f"{len(false_positives)} legit technical answers were false-blocked: "
        f"{[v.reasons for v in false_positives]}"
    )


# --------------------------------------------------------------------------
# Precedence: a leak inside otherwise-grounded text still BLOCKS (gate wins).
# --------------------------------------------------------------------------
def test_leak_wins_over_groundedness(screen: CriticScreen) -> None:
    answer = "Synthesus grounds on the drive. response_template rendered here."
    sources = [{"text": "Synthesus grounds on the expansion drive corpus."}]
    _assert_blocked(screen.screen(answer, sources=sources))


# --------------------------------------------------------------------------
# The configured groundedness floor is the tuned value (documents the dial).
# --------------------------------------------------------------------------
def test_default_groundedness_floor_is_tuned(screen: CriticScreen) -> None:
    assert screen._floor == pytest.approx(0.12)
