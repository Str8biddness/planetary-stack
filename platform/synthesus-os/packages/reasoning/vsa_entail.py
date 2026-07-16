#!/usr/bin/env python3
"""
Entailment operator via order embeddings — Synthesus 5
=======================================================

The third reasoning operator. Entailment / is-a / deduction is ASYMMETRIC and
TRANSITIVE:

    dog is-a mammal,  mammal is-a animal   =>   dog is-a animal

Cosine similarity (the association/analogy metric) is SYMMETRIC and cannot
express this: cos(dog, animal) == cos(animal, dog). Entailment needs a
*partial order*, so we use ORDER EMBEDDINGS (Vendrov et al. 2016): embed each
concept in the non-negative orthant and define

    x is-a y   <=>   v(x) >= v(y)  coordinate-wise        (the reversed product order)
    penalty E(x,y) = || max(0, v(y) - v(x)) ||            (0 == entails)

Instead of learning v by SGD, we DERIVE it analytically from the is-a graph:

    v(x)[c] = 1  iff  c is x itself or a hypernym (ancestor) of x

Then v(x) >= v(y) exactly when y is among x's ancestors -> x is-a y. Crucially
we feed only DIRECT parent edges; the ancestor closure (hence multi-hop
DEDUCTION) emerges from the geometry, it is never stated. This is the same
"meaning is geometry" program as the other operators: here meaning = containment.

Bridge to the distributional layer: the distributional inclusion hypothesis
(Geffet & Dagan 2005) says a narrow term's contexts are a subset of a broad
term's contexts — i.e. the same containment, derivable from co-occurrence at
scale. The taxonomy here stands in for that (or for a WordNet/KG).

Run:  python3 packages/reasoning/vsa_entail.py
"""
from __future__ import annotations
from collections import deque

import numpy as np

# DIRECT is-a edges only (child -> parent). The closure is derived, not listed.
EDGES = [
    ("dog", "mammal"), ("cat", "mammal"), ("whale", "mammal"),
    ("eagle", "bird"), ("sparrow", "bird"),
    ("mammal", "animal"), ("bird", "animal"),
    ("oak", "tree"), ("tree", "plant"),
    ("rose", "flower"), ("flower", "plant"),
    ("animal", "entity"), ("plant", "entity"),
]


class EntailmentSpace:
    def __init__(self, edges=EDGES):
        self.parents = {}
        nodes = set()
        for c, p in edges:
            self.parents.setdefault(c, []).append(p)
            nodes.update((c, p))
        self.nodes = sorted(nodes)
        self.idx = {n: i for i, n in enumerate(self.nodes)}

        # ancestor-or-self closure -> order-embedding coordinates
        self.V = np.zeros((len(self.nodes), len(self.nodes)), dtype=np.float64)
        for n in self.nodes:
            for a in self._ancestors_or_self(n):
                self.V[self.idx[n], self.idx[a]] = 1.0

    def _ancestors_or_self(self, n):
        seen, q = set(), deque([n])
        while q:
            cur = q.popleft()
            if cur in seen:
                continue
            seen.add(cur)
            q.extend(self.parents.get(cur, []))
        return seen

    # --- the operator ---
    def penalty(self, x, y):
        """0 == x entails y (x is-a y). Larger == further from entailing."""
        vx, vy = self.V[self.idx[x]], self.V[self.idx[y]]
        return float(np.linalg.norm(np.maximum(0.0, vy - vx)))

    def entails(self, x, y):
        return self.penalty(x, y) == 0.0 and x != y

    def hypernyms(self, x):
        return [n for n in self.nodes if n != x and self.entails(x, n)]

    def hyponyms(self, y):
        return [n for n in self.nodes if n != y and self.entails(n, y)]

    def path(self, x, y):
        """A direct-edge path x -> ... -> y, to EXPLAIN a derived entailment."""
        prev, q = {x: None}, deque([x])
        while q:
            cur = q.popleft()
            if cur == y:
                seq = []
                while cur is not None:
                    seq.append(cur)
                    cur = prev[cur]
                return list(reversed(seq))
            for p in self.parents.get(cur, []):
                if p not in prev:
                    prev[p] = cur
                    q.append(p)
        return None


def main():
    S = EntailmentSpace()
    print(f"concepts {len(S.nodes)}  |  direct is-a edges {len(EDGES)} "
          f"(closure derived)\n")

    print("=== asymmetry (cosine can't do this) ===")
    for x, y in (("dog", "animal"), ("animal", "dog")):
        print(f"  {x} is-a {y}? {S.entails(x, y)}   (penalty {S.penalty(x, y):.2f})")

    print("\n=== deduction: multi-hop entailment never stated directly ===")
    for x, y in (("dog", "animal"), ("whale", "entity"), ("rose", "plant"),
                 ("oak", "entity")):
        ok = S.entails(x, y)
        p = S.path(x, y)
        hops = " -> ".join(p) if p else "—"
        direct = (x, y) in EDGES
        tag = "DIRECT" if direct else f"DERIVED ({len(p) - 1} hops)"
        print(f"  {x} is-a {y}: {ok}   [{tag}]   {hops}")

    print("\n=== negatives (siblings & cross-branch) ===")
    for x, y in (("dog", "cat"), ("dog", "plant"), ("eagle", "mammal")):
        print(f"  {x} is-a {y}? {S.entails(x, y)}   (penalty {S.penalty(x, y):.2f})")

    print("\n=== queries ===")
    for x in ("whale", "rose"):
        print(f"  hypernyms({x}) = {S.hypernyms(x)}")
    for y in ("animal", "plant"):
        print(f"  hyponyms({y})  = {S.hyponyms(y)}")

    # exhaustive self-check: derived closure == graph reachability
    def reachable(x, y):
        return y in S._ancestors_or_self(x) and x != y
    bad = [(x, y) for x in S.nodes for y in S.nodes
           if S.entails(x, y) != reachable(x, y)]
    print(f"\n  consistency: order-embedding entailment == is-a reachability "
          f"on all {len(S.nodes) ** 2} pairs -> {'OK' if not bad else f'MISMATCH {bad}'}")


if __name__ == "__main__":
    main()
