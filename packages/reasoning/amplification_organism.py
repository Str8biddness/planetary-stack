#!/usr/bin/env python3
"""
Amplification Organism Framework — Synthesus 5
==============================================

An AMPLIFICATION ORGANISM is an ability-defined group of co-trained organ
*dependencies* plus a governing amplification loop. It exists to uplift exactly
one ability.

CRITICAL — organisms are DEPENDENCIES of Synthesus's abilities:
  Synthesus.ability "predict_next"  --requires-->  NextWordOrganism {context, transition}
  Synthesus.ability "converse"      --requires-->  ConversationOrganism {intent, ...}

Without the organism (present + trained + measured-passing), the ability is
UNAVAILABLE — hard-gated. No organism → Synthesus cannot predict the next word,
cannot converse, etc. Capability is gated by PROOF (it must pass its measured
bar), not by claim. New ability = new co-trained organism, plugged in as a
module; the others stay coherent.

Run:  ./venv/bin/python packages/reasoning/amplification_organism.py
"""
from __future__ import annotations
import math
import re
from collections import Counter, defaultdict

import numpy as np


class CapabilityUnavailable(RuntimeError):
    """Raised when a Synthesus ability is invoked but its organism isn't ready."""


# ── organs: the co-trained dependencies inside an organism ──
class Organ:
    def __init__(self, name): self.name = name; self.trained = False
    def train(self, data): self.trained = True


class TransitionOrgan(Organ):
    """Psi_f — what tends to follow what."""
    def __init__(self): super().__init__("transition"); self.bi = defaultdict(Counter)
    def train(self, tokens):
        for i in range(len(tokens) - 1): self.bi[tokens[i]][tokens[i + 1]] += 1
        self.trained = True
    def candidates(self, last, k=20): return [w for w, _ in self.bi[last].most_common(k)]
    def logp(self, last, w):
        tot = sum(self.bi[last].values()); return math.log(self.bi[last][w] / tot) if tot else -99


class ContextOrgan(Organ):
    """Mc/Ns — meaning + running context, to keep the choice coherent."""
    def __init__(self): super().__init__("context"); self.E = None; self.vidx = {}
    def train(self, tokens):
        vocab = [w for w, _ in Counter(tokens).most_common(2000)]
        self.vidx = {w: i for i, w in enumerate(vocab)}
        V = len(vocab); C = np.zeros((V, V))
        for i, w in enumerate(tokens):
            if w not in self.vidx: continue
            for j in range(max(0, i - 4), min(len(tokens), i + 5)):
                if j != i and tokens[j] in self.vidx: C[self.vidx[w], self.vidx[tokens[j]]] += 1
        # PPMI + SVD
        tot = C.sum(); row = C.sum(1, keepdims=True); col = C.sum(0, keepdims=True)
        with np.errstate(divide="ignore", invalid="ignore"):
            M = np.maximum(0, np.log((C * tot) / (row * col + 1e-9) + 1e-9))
        U, S, _ = np.linalg.svd(M, full_matrices=False)
        E = U[:, :32] * np.sqrt(S[:32]); n = np.linalg.norm(E, axis=1, keepdims=True); n[n == 0] = 1
        self.E = E / n; self.trained = True
    def vec(self, w): return self.E[self.vidx[w]] if (self.E is not None and w in self.vidx) else None


# ── the organism: a group of organs amplifying ONE ability ──
class AmplificationOrganism:
    ability = None
    bar = 0.0                      # measured threshold it must beat to be "ready"
    def __init__(self): self.organs = {}; self._score = None
    def train(self, data): raise NotImplementedError
    def measure(self, testset): raise NotImplementedError
    def run(self, *a): raise NotImplementedError
    def ready(self):
        return (all(o.trained for o in self.organs.values())
                and self._score is not None and self._score >= self.bar)


class NextWordOrganism(AmplificationOrganism):
    ability = "predict_next"
    bar = 0.0                      # honest: just needs to be trained+measured to expose
    def __init__(self, lam=1.2):
        super().__init__()
        self.tr = TransitionOrgan(); self.ctx = ContextOrgan()
        self.organs = {"transition": self.tr, "context": self.ctx}
        self.lam = lam
    def train(self, tokens):
        self.tr.train(tokens); self.ctx.train(tokens)
    def run(self, context_words):
        if not context_words: return None
        last = context_words[-1]
        cands = self.tr.candidates(last)
        if not cands: return None
        thread = None
        for w in context_words[-5:]:
            v = self.ctx.vec(w)
            if v is not None: thread = v if thread is None else 0.7 * thread + 0.3 * v
        def score(w):
            s = self.tr.logp(last, w); v = self.ctx.vec(w)
            if v is not None and thread is not None:
                s += self.lam * float(v @ thread / ((np.linalg.norm(v)*np.linalg.norm(thread)) or 1))
            return s
        return max(cands, key=score)
    def measure(self, test_tokens):
        hit = tot = 0
        for i in range(2, len(test_tokens) - 1):
            pred = self.run(test_tokens[max(0, i-4):i+1])
            if pred is not None:
                tot += 1; hit += (pred == test_tokens[i + 1])
        self._score = hit / tot if tot else 0.0
        return self._score


# ── Synthesus: abilities are HARD-GATED on their organisms ──
class Synthesus:
    def __init__(self): self.organisms = {}
    def register(self, organism): self.organisms[organism.ability] = organism
    def can(self, ability):
        o = self.organisms.get(ability); return bool(o and o.ready())
    def do(self, ability, *args):
        o = self.organisms.get(ability)
        if o is None:
            raise CapabilityUnavailable(f"'{ability}': NO organism registered — ability does not exist.")
        if not o.ready():
            raise CapabilityUnavailable(f"'{ability}': organism present but NOT ready "
                                        f"(organs trained={all(x.trained for x in o.organs.values())}, "
                                        f"measured={o._score}). Ability gated until it earns its bar.")
        return o.run(*args)


CORPUS = ("the cat sat on the mat and the dog ran in the yard while the bird flew over the tree "
          "the river flows to the sea and the rain falls from the sky onto the green grass "
          "the sun warms the sky and the moon lights the night as the stars shine over the sea "
          "knowledge grows in the mind through thought and reason while the river runs to the sea ") * 6


def main():
    toks = re.findall(r"[a-z]+", CORPUS)
    split = int(len(toks) * 0.85); train, test = toks[:split], toks[split:]
    s = Synthesus()

    print("=== abilities are DEPENDENCIES on organisms (hard-gated) ===")
    print(f"can('predict_next') before any organism: {s.can('predict_next')}")
    try: s.do("predict_next", ["the"])
    except CapabilityUnavailable as e: print(f"  do() -> BLOCKED: {e}")

    org = NextWordOrganism(); s.register(org)
    print(f"\nregistered NextWordOrganism. can('predict_next') (untrained): {s.can('predict_next')}")
    try: s.do("predict_next", ["the"])
    except CapabilityUnavailable as e: print(f"  do() -> BLOCKED: {e}")

    org.train(train); score = org.measure(test)
    print(f"\ntrained + measured the organism. next-word top-1 = {score*100:.1f}%")
    print(f"can('predict_next') now: {s.can('predict_next')}")
    print("  organs (dependencies):", list(org.organs))
    print("  do('predict_next', ['the','river']) ->", s.do("predict_next", ["the", "river"]))
    print("  do('predict_next', ['the','sun']) ->", s.do("predict_next", ["the", "sun"]))

    print("\nSynthesus CANNOT predict the next word without this organism — proven above")
    print("(blocked before, works after). Each ability = one co-trained organism it")
    print("depends on; it earns the ability by measurement. New ability = new organism.")


if __name__ == "__main__":
    main()
