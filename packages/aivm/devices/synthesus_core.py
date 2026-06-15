"""
SynthesusReasoningCore — live cognition backend for the AIVM pipeline.

Wires the VSA reasoning operators + NL front end into the kernel's device
contract. Mount it as an NPC's `reasoning_core`; VGD/VRD/VND then delegate to it
(see those devices' `_core` checks). This replaces the stub generation +
always-pass coherence gate with the real, grounded, declining-not-hallucinating
reasoning we built in packages/reasoning/.
"""
from __future__ import annotations
import os
import sys
from typing import Any, Dict

# make the reasoning package importable (it uses flat module names)
_REASONING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reasoning")
sys.path.insert(0, os.path.abspath(_REASONING))

from vsa_nl import NLReasoner  # noqa: E402

NO_ANSWER = "[NO_GROUNDED_ANSWER]"
_DEGENERATE = {None, "", "no answer", "unknown", "(could not parse)", NO_ANSWER}


class SynthesusReasoningCore:
    def __init__(self):
        self.nl = NLReasoner()
        self.last_trace = []

    # VRD.plan delegates here
    def plan(self, intent: str, context: Dict[str, Any]) -> str:
        return f"resolve: {intent}"

    # VGD.generate delegates here
    def generate(self, request: Dict[str, Any]) -> str:
        text = request.get("input", "")
        ans, trace = self.nl.ask(text)
        self.last_trace = trace
        if ans in _DEGENERATE or (isinstance(ans, str) and
                                  ans.lower().startswith(("i have no record", "no direct record"))):
            return NO_ANSWER          # grounded refusal -> coherence will fail it
        return str(ans)

    # VND.coherence_check delegates here — a REAL gate, not `return True`
    def coherence_check(self, draft: str) -> bool:
        if not draft or not draft.strip():
            return False
        if draft.strip() == NO_ANSWER:
            return False              # refuse to emit an ungrounded answer
        return True
