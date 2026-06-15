"""
SynthesusReasoningCore — live cognition backend for the AIVM pipeline.

Dual-process / dual-hemisphere reasoning behind the kernel's device contract.

  LEFT (grounding):    symbolic VSA operators via the NL front end -> verified.
  RIGHT (imagination): when grounding fails, infer/associate ->
       (a) abstraction (the smelter loop) — inferential imagination, then
       (b) Hopfield ENERGY SETTLING — associative imagination: settle the query's
           concepts into the nearest grounded attractor (vsa_hopfield).
  ARBITER:             grounded answers are stated as fact; imagined answers are
                       FLAGGED ("[educated guess] ..."); ungrounded -> declined.

Generation and hallucination are the same predictive act; this core makes the
difference explicit and tagged.  Mount as an NPC `reasoning_core`; VGD/VRD/VND
delegate to it.
"""
from __future__ import annotations
import os
import re
import sys
from typing import Any, Dict, Tuple

import numpy as np

_REASONING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reasoning")
sys.path.insert(0, os.path.abspath(_REASONING))

from vsa_nl import NLReasoner, lemma          # noqa: E402
from vsa_abstract import AbstractiveController  # noqa: E402
from vsa_hopfield import ModernHopfield        # noqa: E402

NO_ANSWER = "[NO_GROUNDED_ANSWER]"
_DEGENERATE = {None, "", "no answer", "unknown", "(could not parse)", NO_ANSWER}
_TAG_PREFIX = {"grounded": "[verified]", "imagination": "[educated guess]"}


class SynthesusReasoningCore:
    def __init__(self, beta: float = 8.0):
        self.nl = NLReasoner()                       # left hemisphere (symbolic)
        self.ctrl = AbstractiveController()          # imagination: abstraction
        vsa = self.nl.R.vsa
        self.hop = ModernHopfield(vsa.SEM, vsa.vocab, beta=beta)  # imagination: settling
        self.last_groundedness = "ungrounded"
        self.last_mechanism = "none"
        self.last_confidence = 0.0
        self.last_trace = []

    def _cue(self, text: str):
        """Build a Hopfield cue from whatever grounded concepts the query names."""
        vsa = self.nl.R.vsa
        vecs = [vsa.SEM[vsa.vidx[t]] for t in re.findall(r"[a-z]+", text.lower())
                if t in vsa.vidx]
        return np.mean(vecs, axis=0) if vecs else None

    # ── dual-process classifier ──
    def reason(self, text: str) -> Tuple[Any, str, float]:
        # 1. LEFT: symbolic grounding
        ans, trace = self.nl.ask(text)
        self.last_trace = trace
        if ans not in _DEGENERATE and not (isinstance(ans, str) and
                ans.lower().startswith(("i have no record", "no direct record"))):
            self.last_mechanism = "symbolic"
            return ans, "grounded", 1.0

        # 2. RIGHT (inferential): abstraction / smelter on who-queries
        m = re.search(r"who (\w+) the (\w+)", text.lower())
        if m:
            agent, answer, atrace = self.ctrl.who_does(lemma(m.group(1)), m.group(2))
            if agent is not None:
                self.last_trace = atrace
                self.last_mechanism = "abstraction"
                return answer, "imagination", 0.5

        # 3. RIGHT (associative): Hopfield energy settling into a grounded attractor
        cue = self._cue(text)
        if cue is not None:
            cue_n = cue / (np.linalg.norm(cue) + 1e-9)
            evocation = float(np.max(self.hop.X @ cue_n))   # how strongly it evokes
            concept, _overlap, _traj = self.hop.recall(cue)
            self.last_mechanism = "hopfield"
            return f"this settles toward '{concept}' (associative)", "imagination", evocation

        # 4. nothing to ground or imagine from
        self.last_mechanism = "none"
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

    # VND.coherence_check delegates here — grounded & imagination pass (flagged);
    # ungrounded is refused.
    def coherence_check(self, draft: str) -> bool:
        return bool(draft and draft.strip() and draft.strip() != NO_ANSWER)
