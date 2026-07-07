"""
SynthesusReasoningCore — live cognition backend for the AIVM pipeline.

Dual-process reasoning GOVERNED by the amplification router.

  Hemispheres-as-organs:
    symbolic    (LEFT, grounding) -> verified answers, confidence 1.0
    abstraction (RIGHT, inferential imagination)
    hopfield    (RIGHT, associative imagination, energy settling)
  The MetaController (reused from vsa_amplify) learns, PER query-type, which
  hemisphere to try first — grounded answers outrank imagined ones because their
  confidence is higher, so the loop naturally prefers grounding where it works
  and imagination where grounding can't reach.

  Arbiter: grounded -> stated as fact ("[verified]"); imagined -> flagged
  ("[educated guess]"); ungrounded -> declined.

Mount as an NPC `reasoning_core`; VGD/VRD/VND delegate to it.
"""
from __future__ import annotations
import os
import re
import sys
from typing import Any, Dict, Tuple

import numpy as np

_REASONING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "reasoning")
sys.path.insert(0, os.path.abspath(_REASONING))

from vsa_nl import NLReasoner, lemma            # noqa: E402
from vsa_abstract import AbstractiveController    # noqa: E402
from vsa_hopfield import ModernHopfield          # noqa: E402
from vsa_amplify import MetaController            # noqa: E402  (the governance loop)

NO_ANSWER = "[NO_GROUNDED_ANSWER]"
_DEGENERATE = {None, "", "no answer", "unknown", "(could not parse)", NO_ANSWER}
_TAG_PREFIX = {"grounded": "[verified]", "imagination": "[educated guess]"}
TOL = 0.4


# ── hemispheres as governed organs ──
class _Symbolic:
    name, tag = "symbolic", "grounded"
    def __init__(self, core): self.c = core
    def attempt(self, text):
        ans, trace = self.c.nl.ask(text)
        ok = ans not in _DEGENERATE and not (isinstance(ans, str) and
             ans.lower().startswith(("i have no record", "no direct record")))
        return (ans, 1.0, trace) if ok else (None, 0.0, trace)


class _Abstraction:
    name, tag = "abstraction", "imagination"
    def __init__(self, core): self.c = core
    def attempt(self, text):
        m = re.search(r"who (\w+) the (\w+)", text.lower())
        if not m:
            return (None, 0.0, [])
        agent, answer, atrace = self.c.ctrl.who_does(lemma(m.group(1)), m.group(2))
        # structured inference: higher value than loose association
        return (answer, 0.7, atrace) if agent is not None else (None, 0.0, atrace)


class _Hopfield:
    name, tag = "hopfield", "imagination"
    def __init__(self, core): self.c = core
    def attempt(self, text):
        cue = self.c._cue(text)            # nouns only
        if cue is None:
            return (None, 0.0, [])
        cue_n = cue / (np.linalg.norm(cue) + 1e-9)
        evocation = float(np.max(self.c.hop.X @ cue_n))
        if evocation < 0.5:                # too weak a cue to imagine from
            return (None, 0.0, [])
        concept, _ov, _tr = self.c.hop.recall(cue)
        # loose association: a fixed, modest value below structured inference
        return (f"this settles toward '{concept}' (associative)", 0.65, [])


class SynthesusReasoningCore:
    def __init__(self, beta: float = 8.0):
        self.nl = NLReasoner()                       # symbolic
        self.ctrl = AbstractiveController()          # abstraction
        vsa = self.nl.R.vsa
        self.hop = ModernHopfield(vsa.SEM, vsa.vocab, beta=beta)  # settling

        self.organs = [_Symbolic(self), _Abstraction(self), _Hopfield(self)]
        self.meta = MetaController()                 # governs the hemispheres
        self.last_groundedness = "ungrounded"
        self.last_mechanism = "none"
        self.last_confidence = 0.0
        self.last_attempts = 0
        self.last_trace = []
        self._bootstrap()

    # ── helpers ──
    # function words + action verbs excluded so the cue is built from NOUN
    # concepts (a who/what query should evoke the entity, not the verb).
    _NOT_CUE = set("who what is are was the a an and or of to me about tell something "
                   "kind thing do does did this that it bites bite bit chases chase "
                   "feeds feed fed sees see saw flies fly".split())

    def _cue(self, text: str):
        vsa = self.nl.R.vsa
        vecs = [vsa.SEM[vsa.vidx[t]] for t in re.findall(r"[a-z]+", text.lower())
                if t in vsa.vidx and t not in self._NOT_CUE]
        return np.mean(vecs, axis=0) if vecs else None

    @staticmethod
    def _domain(text: str) -> str:
        t = text.lower().strip()
        if t.startswith("who "): return "who"
        if t.startswith(("is ", "are ", "was ")): return "isa"
        if t.startswith("what"): return "what"
        return "open"

    def _bootstrap(self, epochs: int = 5):
        """Train the governance loop on representative queries (shadow eval):
        score each hemisphere per domain; abstention is neutral, not failure."""
        samples = [
            "who bit the man", "who feeds the dog", "who chases the wolf",
            "is a dog an animal", "is a dog a feline",
            "what kind of thing is a wolf",
            "tell me about the wolf and the fox",
            "something about the dog and the cat", "the man and the dog",
        ]
        for _ in range(epochs):
            for s in samples:
                d = self._domain(s)
                for org in self.organs:
                    ans, conf, _ = org.attempt(s)
                    if conf >= TOL and ans is not None:
                        self.meta.record(d, org.name, conf, True)

    # ── governed dual-process reasoning ──
    def reason(self, text: str) -> Tuple[Any, str, float]:
        domain = self._domain(text)
        order = self.meta.rank(domain, self.organs)
        for i, org in enumerate(order):
            ans, conf, trace = org.attempt(text)
            if conf >= TOL and ans is not None:
                self.last_mechanism = org.name
                self.last_attempts = i + 1
                self.last_trace = trace
                return ans, org.tag, conf
        self.last_mechanism, self.last_attempts = "none", len(order)
        return None, "ungrounded", 0.0

    def plan(self, intent: str, context: Dict[str, Any]) -> str:
        return f"resolve: {intent}"

    def generate(self, request: Dict[str, Any]) -> str:
        ans, tag, conf = self.reason(request.get("input", ""))
        self.last_groundedness, self.last_confidence = tag, conf
        if tag == "ungrounded":
            return NO_ANSWER
        return f"{_TAG_PREFIX[tag]} {ans}"

    def coherence_check(self, draft: str) -> bool:
        return bool(draft and draft.strip() and draft.strip() != NO_ANSWER)

    # introspection for demos/inspection
    def routing_table(self) -> Dict[str, str]:
        return {d: self.meta.rank(d, self.organs)[0].name
                for d in ("who", "isa", "what", "open")}
