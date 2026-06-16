#!/usr/bin/env python3
"""
Fusion generator — C(t) operationalized — Synthesus 5
=====================================================

The generation experiment exposed: meaning = SYMMETRIC association (coherent but
not fluent); generation = DIRECTIONAL transitions (fluent but wanders). Neither
alone works. This fuses them, mapping onto the C(t) decomposition:

  next token  =  sample TRANSITION distribution        (Psi_f / fluid: what follows)
                 reranked by MEANING similarity to the  (Mc / crystallized: stay coherent)
                 running THREAD vector                  (Ns / narrative: hold the topic)

  score(c) = log P_transition(c | last)  +  lambda * cos(vec(c), thread)   [content words]
           = log P_transition(c | last)                                     [function words]

Measured against pure-bigram (fluid only) and pure-similarity (crystallized only)
on fluency (valid-bigram rate) and coherence (topic cohesion).

Run:  ./venv/bin/python packages/reasoning/vsa_fusion_generator.py
"""
from __future__ import annotations
import os
import re
import sys
import math
import random
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_twolayer import cooccurrence, ppmi, svd_embed  # noqa: E402

STOP = set("the a an and or of to in into on at by for with from as is are was were be "
           "been it its this that these those there here when where which who what why how "
           "not no s than then so if but we you they he she i".split())


def load():
    text = open(os.path.join(os.path.dirname(__file__), "..", "..", "data", "corpus",
                             "real_corpus.txt"), encoding="utf-8", errors="ignore").read()
    toks = re.findall(r"[a-z]+", text.lower())
    bi = defaultdict(Counter)
    for i in range(len(toks) - 1):
        bi[toks[i]][toks[i + 1]] += 1
    real_bg = set((toks[i], toks[i + 1]) for i in range(len(toks) - 1))
    counts = Counter(toks)
    vocab = [w for w, _ in counts.most_common(2500)]
    vidx = {w: i for i, w in enumerate(vocab)}
    E = svd_embed(ppmi(cooccurrence(toks, vidx, window=5)), 64)
    return bi, real_bg, E, vidx, vocab


class FusionGen:
    def __init__(self):
        self.bi, self.real_bg, self.E, self.vidx, self.vocab = load()

    def vec(self, w):
        return self.E[self.vidx[w]] if w in self.vidx else None

    @staticmethod
    def _cos(a, b):
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        return float(a @ b / (na * nb)) if na and nb else 0.0

    # ── baselines ──
    def gen_bigram(self, seed, n, rng):
        out = [seed]
        for _ in range(n):
            c = self.bi[out[-1]]
            if not c:
                break
            out.append(rng.choices(list(c), weights=list(c.values()))[0])
        return out

    def gen_similarity(self, seed, n, rng):
        out, used = [seed], {seed}
        for _ in range(n):
            if out[-1] not in self.vidx:
                break
            sims = self.E @ self.E[self.vidx[out[-1]]]
            nxt = next((self.vocab[j] for j in np.argsort(-sims)
                        if self.vocab[j] not in used), None)
            if not nxt:
                break
            out.append(nxt); used.add(nxt)
        return out

    # ── the fusion: fluid x crystallized x narrative ──
    def gen_fusion(self, seed, n, rng, lam=1.6, decay=0.7):
        out = [seed]
        thread = self.vec(seed).copy() if (seed not in STOP and self.vec(seed) is not None) \
            else np.zeros(self.E.shape[1])
        for _ in range(n):
            cand = self.bi[out[-1]]                     # Psi_f: fluent options
            if not cand:
                break
            total = sum(cand.values())
            scores = {}
            for w, ct in cand.items():
                s = math.log(ct / total)                # fluid: transition log-prob
                v = self.vec(w)
                if w not in STOP and v is not None and np.linalg.norm(thread) > 0:
                    s += lam * self._cos(v, thread)     # Mc/Ns: coherence with thread
                scores[w] = s
            # sample from softmax of fused scores (temp slightly < 1 for focus)
            ws = list(scores); z = np.array([scores[w] for w in ws]); z -= z.max()
            p = np.exp(z / 0.7); p /= p.sum()
            pick = ws[rng.choices(range(len(ws)), weights=p)[0]]
            out.append(pick)
            v = self.vec(pick)                          # Ns: update narrative thread
            if pick not in STOP and v is not None:
                thread = decay * thread + (1 - decay) * v
        return out

    # ── metrics ──
    def fluency(self, seq):
        pairs = [(seq[i], seq[i + 1]) for i in range(len(seq) - 1)]
        return sum(p in self.real_bg for p in pairs) / max(1, len(pairs))

    def coherence(self, seq):
        cv = [self.vec(w) for w in seq if w not in STOP and self.vec(w) is not None]
        if len(cv) < 2:
            return 0.0
        sims = [self._cos(cv[i], cv[j]) for i in range(len(cv)) for j in range(i + 1, len(cv))]
        return float(np.mean(sims))


def main():
    g = FusionGen()
    seeds = ["the", "space", "time", "light", "the", "motion", "energy", "we"]
    methods = [("bigram (Psi_f only)", g.gen_bigram),
               ("similarity (Mc only)", g.gen_similarity),
               ("FUSION (Psi_f x Mc x Ns)", g.gen_fusion)]
    print("sample outputs (seed='space'):")
    rng = random.Random(3)
    for name, fn in methods:
        print(f"  {name:26}: {' '.join(fn('space', 14, rng))}")

    print("\nmeasured over 8 seeds (fluency = valid-bigram %, coherence = topic cohesion):")
    print("  method                     | fluency | coherence | fluency x coherence")
    print("  ---------------------------+---------+-----------+--------------------")
    for name, fn in methods:
        fl, co = [], []
        for s in seeds:
            rng = random.Random(hash(s) % 9999)
            seq = fn(s, 14, rng)
            fl.append(g.fluency(seq)); co.append(g.coherence(seq))
        f, c = np.mean(fl), np.mean(co)
        print(f"  {name:26} |  {f*100:4.0f}%  |   {c:+.2f}    |     {f*c:.3f}")
    print("\nThe fusion aims to win the PRODUCT (fluent AND coherent) — the axis")
    print("neither baseline can hold alone. This is C(t) made executable & measured.")


if __name__ == "__main__":
    main()
