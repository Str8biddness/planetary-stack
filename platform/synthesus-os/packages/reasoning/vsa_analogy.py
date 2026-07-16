#!/usr/bin/env python3
"""
Analogy operator over the grounded semantic layer — Synthesus 5
================================================================

Analogy = a:b :: c:?  solved by VECTOR TRANSLATION in the distributional
semantic space:                d  =  argmax  cos( SEM[c] + SEM[b] - SEM[a] )

KEY ARCHITECTURAL POINT (why this lives in the SEMANTIC layer, not the
identity layer): the identity vectors in vsa_twolayer.py are *random* symbols.
A transform learned from one random pair (t = b ⊘ a) maps a -> b and nothing
else; it cannot generalize to c. Generalizing analogy REQUIRES the grounded
geometry where a consistent relation is a consistent DIRECTION. So:

    identity layer  -> exact structure / role binding (vsa_twolayer, vsa_query)
    semantic layer  -> generalization: analogy, similarity, category (here)

Same shared space, two complementary operators. This file reuses
TwoLayerVSA's PPMI+SVD semantic layer unchanged.

Run:  python3 packages/reasoning/vsa_analogy.py
"""
from __future__ import annotations
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_twolayer import TwoLayerVSA  # noqa: E402

# Corpus engineered with PARALLEL male/female and royal/common contexts so a
# consistent "gender" and "rank" direction emerges in co-occurrence space.
# (Analogy needs the relation to be a stable direction; that needs parallel
# data. On a real corpus this emerges naturally at scale.)
ANALOGY_CORPUS = """
the king rules the land and the king wears the crown and the king leads the army.
the queen rules the land and the queen wears the crown and the queen leads the court.
the man works the field and the man wears the coat and the man leads the house.
the woman works the field and the woman wears the coat and the woman leads the home.
the prince serves the king and the prince trains with the man in the yard.
the princess serves the queen and the princess trains with the woman in the hall.
the boy follows the man and the boy follows the prince and the boy serves the king.
the girl follows the woman and the girl follows the princess and the girl serves the queen.
the king and the man and the prince and the boy stand on the right.
the queen and the woman and the princess and the girl stand on the left.
the king loves the queen and the man loves the woman as the prince loves the princess.
the boy and the girl watch the king and the queen rule the land.
"""


# Closed-class words are never the answer to a content-word analogy. Excluding
# them from CANDIDATES (not from the geometry) is the standard, principled
# cleanup — it removes centroid-hugging intruders like "on"/"with".
FUNCTION_WORDS = set("""
on with at by off up down in into out over under here there left right
the a an and or as from of to is are be this that these those for
""".split())


class AnalogyEngine:
    def __init__(self, corpus=ANALOGY_CORPUS, sem_dims=64):
        self.vsa = TwoLayerVSA(corpus=corpus, sem_dims=sem_dims)
        self.SEM = self.vsa.SEM
        self.vocab = self.vsa.vocab
        self.vidx = self.vsa.vidx

    def _rank(self, target, exclude, k):
        t = target / (np.linalg.norm(target) or 1.0)
        sims = self.SEM @ t
        out = []
        for j in np.argsort(-sims):
            w = self.vocab[j]
            if w in exclude or w in FUNCTION_WORDS:
                continue
            out.append((w, float(sims[j])))
            if len(out) >= k:
                break
        return out

    def analogy(self, a, b, c, k=3):
        """a is to b as c is to ?  ->  ranked candidates."""
        for w in (a, b, c):
            if w not in self.vidx:
                return [(f"<{w} not in vocab>", 0.0)]
        target = self.SEM[self.vidx[c]] + self.SEM[self.vidx[b]] - self.SEM[self.vidx[a]]
        return self._rank(target, exclude={a, b, c}, k=k)


def main():
    eng = AnalogyEngine()
    print(f"vocab {len(eng.vocab)}  |  semantic dims {eng.SEM.shape[1]}\n")

    # sanity: similar words near each other
    print("=== grounding sanity (neighbors) ===")
    for w in ("king", "man", "girl"):
        if w in eng.vidx:
            nb = eng.analogy  # noqa (just to keep flake quiet)
            sims = eng.SEM @ eng.SEM[eng.vidx[w]]
            near = [(eng.vocab[j], float(sims[j]))
                    for j in np.argsort(-sims) if eng.vocab[j] != w][:3]
            print(f"  {w:6} ~ " + ", ".join(f"{x}({s:.2f})" for x, s in near))

    tests = [
        ("man", "woman", "king", "queen"),
        ("woman", "man", "queen", "king"),
        ("king", "queen", "prince", "princess"),
        ("boy", "girl", "prince", "princess"),
        ("man", "woman", "boy", "girl"),
        ("king", "man", "queen", "woman"),   # rank direction: royal -> common
    ]

    print("\n=== analogy: a is to b as c is to ? ===")
    top1 = top3 = total = 0
    for a, b, c, expected in tests:
        cands = eng.analogy(a, b, c, k=3)
        names = [w for w, _ in cands]
        total += 1
        is1 = names[:1] == [expected]
        is3 = expected in names
        top1 += is1
        top3 += is3
        flag = "OK " if is1 else ("~3 " if is3 else "XX ")
        shown = ", ".join(f"{w}({s:.2f})" for w, s in cands)
        print(f"  [{flag}] {a:6}:{b:8}:: {c:7}:?  (want {expected:9}) -> {shown}")
    print(f"\n  top-1: {top1}/{total}   top-3: {top3}/{total}")


if __name__ == "__main__":
    main()
