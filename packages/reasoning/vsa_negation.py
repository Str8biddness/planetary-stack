#!/usr/bin/env python3
"""
Negation operator — Synthesus 5
================================

Negation has two faces; we implement both, on the shared substrate.

1. GEOMETRIC negation = reflection through a hyperplane.
   Antonyms are distributionally NEAR each other (hot/cold share contexts), so
   cosine cannot separate them — same asymmetry problem entailment had. Given an
   antonym axis (a polarity pair, the grounding, like is-a edges were), we
   reflect a concept across the hyperplane bisecting that axis:

       d = v(pos) - v(neg);  m = (v(pos)+v(neg))/2
       negate(x) = x - 2 ((x - m) . d_hat) d_hat

   Reflecting along the axis a concept lies on flips its polarity (hot->cold)
   while leaving off-axis concepts essentially unchanged (negating "big" along
   the temperature axis is a no-op) — which is the correct behaviour.

2. LOGICAL negation = set complement, for the reasoning system:
   "who did NOT bite the man?", "which animals are NOT canines?". Exact, and
   composes with the other operators (vsa_reason.py).

Run:  python3 packages/reasoning/vsa_negation.py
"""
from __future__ import annotations
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_twolayer import TwoLayerVSA          # noqa: E402
from vsa_entail import EntailmentSpace        # noqa: E402

# Corpus with parallel polarity pairs so each antonym axis is a real direction.
NEG_CORPUS = """
the fire is hot and the fire gives heat and the summer day is hot.
the ice is cold and the ice gives chill and the winter day is cold.
the hot fire warms the room while the cold ice cools the room.
the giant is big and the giant is tall and the giant fills the hall.
the ant is small and the ant is tiny and the ant hides in the grass.
the big giant towers while the small ant crawls on the ground.
the warm summer is hot and the cool winter is cold through the year.
hot and cold name the heat while big and small name the size.
the day is hot or cold and the giant or ant is big or small.
"""

# Given antonym axes (the grounding for geometric negation).
AXES = [("hot", "cold"), ("big", "small")]


class NegationSpace:
    def __init__(self, corpus=NEG_CORPUS, axes=AXES):
        self.vsa = TwoLayerVSA(corpus=corpus, sem_dims=64)
        self.SEM, self.vocab, self.vidx = self.vsa.SEM, self.vsa.vocab, self.vsa.vidx
        self.axes = [(p, n) for p, n in axes if p in self.vidx and n in self.vidx]

    def _axis(self, pos, neg):
        d = self.SEM[self.vidx[pos]] - self.SEM[self.vidx[neg]]
        m = (self.SEM[self.vidx[pos]] + self.SEM[self.vidx[neg]]) / 2.0
        nrm = np.linalg.norm(d)
        return (d / nrm if nrm else d), m

    def _best_axis(self, x):
        """Pick the antonym axis the concept actually lies on (max projection)."""
        best, score = None, -1.0
        for pos, neg in self.axes:
            dh, m = self._axis(pos, neg)
            proj = abs(float((self.SEM[self.vidx[x]] - m) @ dh))
            if proj > score:
                best, score = (pos, neg, dh, m), proj
        return best

    def negate(self, x, k=3):
        if x not in self.vidx:
            return [(f"<{x} not in vocab>", 0.0)]
        pos, neg, dh, m = self._best_axis(x)
        v = self.SEM[self.vidx[x]]
        reflected = v - 2.0 * float((v - m) @ dh) * dh
        r = reflected / (np.linalg.norm(reflected) or 1.0)
        sims = self.SEM @ r
        out = [(self.vocab[j], float(sims[j]))
               for j in np.argsort(-sims) if self.vocab[j] != x][:k]
        return out, (pos, neg)


# --- logical negation over the reasoning world (set complement) ------------
FACTS = [("dog", "bites", "man"), ("wolf", "chases", "fox"),
         ("man", "feeds", "dog"), ("fox", "chases", "cat")]
TAX = [("dog", "canine"), ("wolf", "canine"), ("fox", "canine"),
       ("cat", "feline"), ("canine", "mammal"), ("feline", "mammal"),
       ("mammal", "animal"), ("animal", "entity")]


def logical_negation_demo():
    from vsa_query import FactStore
    vsa = TwoLayerVSA()
    store = FactStore(vsa)
    for s, v, o in FACTS:
        store.add(s, v, o)
    tax = EntailmentSpace(edges=TAX)

    actors = sorted({s for s, _, _ in FACTS})
    # who did NOT bite the man?
    bit_man = {s for s, v, o in FACTS if (v, o) == ("bites", "man")}
    print(f"  who did NOT bite the man? -> {sorted(set(actors) - bit_man)}")
    # which animals are NOT canines?
    animals = set(tax.hyponyms("animal"))
    canines = set(tax.hyponyms("canine")) | {"canine"}
    print(f"  which animals are NOT canines? -> "
          f"{sorted(a for a in animals - canines if a in {'cat','feline','dog','wolf','fox'})}")


def main():
    N = NegationSpace()
    print(f"vocab {len(N.vocab)}  |  axes {N.axes}\n")

    print("=== geometric negation (reflection across antonym hyperplane) ===")
    for w in ("hot", "cold", "big", "small"):
        (cands, axis) = N.negate(w)
        shown = ", ".join(f"{x}({s:.2f})" for x, s in cands)
        print(f"  negate({w:5}) [axis {axis[0]}/{axis[1]}] -> {shown}")

    print("\n=== logical negation (set complement, composes with reasoning) ===")
    logical_negation_demo()


if __name__ == "__main__":
    main()
