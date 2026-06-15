"""
SynthesusReasoningCore — live cognition backend for the AIVM pipeline.

Wires the VSA reasoning operators + NL front end into the kernel's device
contract. Mount it as an NPC's `reasoning_core`; VGD/VRD/VND then delegate to it.

Groundedness tagging (the imagination upgrade)
----------------------------------------------
Generation and verification are the same predictive act; the difference is
whether there is support. So instead of a binary pass/fail gate, every answer is
TAGGED:
  * grounded   -> verified by the symbolic operators (exact composition /
                  entailment). State it as fact.
  * imagination-> no direct support, but inferred by abstraction (the smelter
                  loop). Plausible, "educated guess" — surfaced, FLAGGED, not
                  emitted as fact. (This is the socket the future GPU
                  "imagination hemisphere" plugs into.)
  * ungrounded -> neither. Declined.
The coherence gate emits grounded + imagination (flagged) and refuses ungrounded.
"""
from __future__ import annotations
import os
import re
import sys
from typing import Any, Dict, Tuple

_REASONING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reasoning")
sys.path.insert(0, os.path.abspath(_REASONING))

from vsa_nl import NLReasoner, lemma          # noqa: E402
from vsa_abstract import AbstractiveController  # noqa: E402

NO_ANSWER = "[NO_GROUNDED_ANSWER]"
_DEGENERATE = {None, "", "no answer", "unknown", "(could not parse)", NO_ANSWER}
_TAG_PREFIX = {"grounded": "[verified]", "imagination": "[educated guess]"}


class SynthesusReasoningCore:
    def __init__(self):
        self.nl = NLReasoner()
        self.ctrl = AbstractiveController()   # imagination path (abstraction)
        self.last_groundedness = "ungrounded"
        self.last_confidence = 0.0
        self.last_trace = []

    # ── the 3-way classifier ──
    def reason(self, text: str) -> Tuple[Any, str, float]:
        ans, trace = self.nl.ask(text)
        self.last_trace = trace
        grounded = ans not in _DEGENERATE and not (
            isinstance(ans, str) and ans.lower().startswith(
                ("i have no record", "no direct record")))
        if grounded:
            return ans, "grounded", 1.0
        # imagination fallback: infer via abstraction on who-queries
        m = re.search(r"who (\w+) the (\w+)", text.lower())
        if m:
            agent, answer, atrace = self.ctrl.who_does(lemma(m.group(1)), m.group(2))
            if agent is not None:
                self.last_trace = atrace
                return answer, "imagination", 0.5
        return None, "ungrounded", 0.0

    # VRD.plan delegates here
    def plan(self, intent: str, context: Dict[str, Any]) -> str:
        return f"resolve: {intent}"

    # VGD.generate delegates here — returns a TAGGED answer
    def generate(self, request: Dict[str, Any]) -> str:
        ans, tag, conf = self.reason(request.get("input", ""))
        self.last_groundedness, self.last_confidence = tag, conf
        if tag == "ungrounded":
            return NO_ANSWER
        return f"{_TAG_PREFIX[tag]} {ans}"

    # VND.coherence_check delegates here — grounded & imagination pass
    # (imagination is flagged, not discarded); ungrounded is refused.
    def coherence_check(self, draft: str) -> bool:
        return bool(draft and draft.strip() and draft.strip() != NO_ANSWER)
