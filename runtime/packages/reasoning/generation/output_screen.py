"""C-301 Critic output screen — the final safety gate on user-facing answers.

Every normal-path response is screened here before it leaves the runtime, for
three failure classes:

  * template / internal leakage   GATE  — blocked 100% of detected cases
  * degenerate / unsafe output    GATE  — blocked 100% of detected cases
  * low groundedness              TARGET— flagged (best-effort, not blocked)

It composes the existing ``TemplateLeakageGuard`` rather than reinventing it.
A blocked answer is NEVER emitted — it is replaced by a safe fallback. This is
a *screen*, a last line of defence; it is not a substitute for grounded
generation, and it does not claim to catch every hallucination. Honest by design.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence

try:
    from .template_guard import TemplateLeakageGuard, TemplateSurface
except ImportError:  # pragma: no cover - packaging fallback
    from template_guard import TemplateLeakageGuard, TemplateSurface  # type: ignore


class ScreenVerdict(str, Enum):
    PASS = "pass"    # emit as-is
    FLAG = "flag"    # emit, but annotate (e.g. low groundedness)
    BLOCK = "block"  # do NOT emit; replace with the safe fallback


@dataclass
class ScreenResult:
    verdict: ScreenVerdict
    text: str                                   # text to actually emit (original or fallback)
    reasons: list[str] = field(default_factory=list)
    groundedness: Optional[float] = None
    original_blocked: bool = False


SAFE_FALLBACK = (
    "I don't have a grounded, verified answer for that yet — and I'd rather not "
    "hand you something unreliable. Try rephrasing, or add a source to the "
    "expansion drive so I can ground on it."
)

# Internal machinery / template markers that must never reach a user.
# Each marker is a *leaked-artifact shape*, tightened so it does not fire on
# ordinary technical prose that merely *discusses* the same concept.
_LEAK_MARKERS = (
    "[amplification halt]",
    "[fallback]",
    "[module]",
    "response_template",
    "traceback (most recent call last)",
    # tightened: only the leaked AttributeError repr form, not a discussion of
    # "a NoneType error" in a legit Python answer.
    "'nonetype' object",
    " object at 0x",
    "as an ai language model",
    "no route matched",
    # NOTE: the router's "Handled:" template surface is still caught (case-
    # sensitively) by TemplateLeakageGuard below; a lowercase "handled:" marker
    # here only false-blocked prose like "the error is handled: use try/except",
    # so it is intentionally NOT listed.
)

# Conservative unsafe-output patterns. Keyed on *instructional intent toward a
# weapon of mass harm* — the verb (make/build/synthesize…) plus a specific
# weapon noun within a short window. Legit technical discussion (`rm -rf`,
# tokens, hashing, tracebacks) never names these weapons, so it is NOT
# false-blocked. Extend via ``extra_unsafe`` per deployment.
_WEAPON = (
    r"bombs?|explosives?|detonators?|nerve agents?|chemical weapons?|"
    r"biological weapons?|bioweapons?|dirty bombs?|pipe bombs?|\bied\b"
)
_DEFAULT_UNSAFE = (
    r"\bhow to (make|build|construct|synthesize|manufacture|assemble|create)\b"
    r".{0,30}\b(" + _WEAPON + r")",
)

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) > 2}


class CriticScreen:
    """Screen a final answer for leakage, degeneracy, unsafe content, groundedness."""

    def __init__(
        self,
        *,
        groundedness_floor: float = 0.12,
        extra_unsafe: Sequence[str] = (),
    ):
        self._guard = TemplateLeakageGuard()
        self._floor = groundedness_floor
        self._unsafe = tuple(_DEFAULT_UNSAFE) + tuple(extra_unsafe)

    # -- individual checks -------------------------------------------------
    def _leaks(self, text: str) -> list[str]:
        low = text.lower()
        hits = [m.strip() for m in _LEAK_MARKERS if m in low]
        guard = self._guard.inspect(text, surface=TemplateSurface.NORMAL)
        if not guard.allowed:
            hits.extend(f"template:{s}" for s in guard.matched_signatures)
        return hits

    def _degenerate(self, text: str) -> list[str]:
        stripped = text.strip()
        if not stripped:
            return ["empty_output"]
        words = stripped.split()
        # collapse to one unique word repeated, or a lone error-ish token
        if len(words) >= 4 and len(set(w.lower() for w in words)) == 1:
            return ["degenerate_repetition"]
        return []

    def _unsafe_hits(self, text: str) -> list[str]:
        low = text.lower()
        return [f"unsafe:{p}" for p in self._unsafe if re.search(p, low)]

    def _groundedness(self, text: str, sources: Sequence[Any]) -> Optional[float]:
        """Token overlap between answer and cited source text. None if not assessable."""
        src_text = " ".join(
            str(s.get("text") or s.get("content") or s.get("snippet") or "")
            for s in sources if isinstance(s, dict)
        )
        if not src_text.strip():
            return None  # no source text shipped -> cannot assess; do not fake it
        ans, src = _tokens(text), _tokens(src_text)
        if not ans:
            return 0.0
        return len(ans & src) / len(ans)

    # -- the gate ----------------------------------------------------------
    def screen(
        self,
        response: str,
        *,
        sources: Optional[Sequence[Any]] = None,
        query: str = "",
    ) -> ScreenResult:
        text = response if isinstance(response, str) else str(response or "")
        reasons: list[str] = []

        blocking = self._leaks(text) + self._degenerate(text) + self._unsafe_hits(text)
        if blocking:
            return ScreenResult(
                verdict=ScreenVerdict.BLOCK,
                text=SAFE_FALLBACK,
                reasons=blocking,
                original_blocked=True,
            )

        grounded = self._groundedness(text, sources or [])
        if grounded is not None and grounded < self._floor:
            reasons.append(f"low_groundedness:{grounded:.3f}")
            return ScreenResult(
                verdict=ScreenVerdict.FLAG,
                text=text,
                reasons=reasons,
                groundedness=grounded,
            )

        return ScreenResult(verdict=ScreenVerdict.PASS, text=text, groundedness=grounded)
