#!/usr/bin/env python3
"""
Learned fusion operator (the ⊕) — on-substrate, no transformer — Synthesus 5
============================================================================

Learns the ⊕: a log-linear (max-entropy) next-token model whose weights over the
fusion features are trained by gradient descent on the real corpus.

  features per candidate w, given (last word, running thread):
    f1 = log P_transition(w | last)   (Psi_f  — fluency)
    f2 = cos(vec(w), thread)          (Ns     — narrative/topic)
    f3 = cos(vec(w), vec(last))       (Mc     — local meaning continuity)
    f4 = log unigram_freq(w)          (prior)
  P(w | ctx) = softmax_w( theta · f(w, ctx) ),  theta learned by SGD.

Measured on held-out next-token accuracy vs bigram and hand-tuned-fusion.
(Vectorized: per-word feature cache, so each position is one matmul.)

Run:  ./venv/bin/python -u packages/reasoning/vsa_learned_fusion.py
"""
from __future__ import annotations
import os
import re
import sys
import math
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_twolayer import cooccurrence, ppmi, svd_embed  # noqa: E402

STOP = set("the a an and or of to in into on at by for with from as is are was were be "
           "been it its this that there here when which who what s than then so we you they".split())
K = 30
DECAY = 0.7


def build():
    text = open(os.path.join(os.path.dirname(__file__), "..", "..", "data", "corpus",
                "real_corpus.txt"), encoding="utf-8", errors="ignore").read()
    toks = re.findall(r"[a-z]+", text.lower())
    split = int(len(toks) * 0.85)
    train = toks[:split]
    bi = defaultdict(Counter)
    for i in range(len(train) - 1):
        bi[train[i]][train[i + 1]] += 1
    freq = Counter(train)
    vocab = [w for w, _ in freq.most_common(3000)]
    vidx = {w: i for i, w in enumerate(vocab)}
    E = svd_embed(ppmi(cooccurrence(train, vidx, window=5)), 64)
    En = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)   # unit rows
    return toks, train, toks[split:], bi, freq, E, En, vidx


class Learned:
    def __init__(self):
        (self.toks, self.train, self.test, self.bi, self.freq,
         self.E, self.En, self.vidx) = build()
        self.dim = self.E.shape[1]
        self.logN = math.log(sum(self.freq.values()))
        self.cache = {}      # last -> (cands, idxs, Vn (C×dim unit), base[C×3]=f1,f3,f4)

    def _nv(self, w):        # unit vector or None
        return self.En[self.vidx[w]] if w in self.vidx else None

    def _entry(self, last):
        if last in self.cache:
            return self.cache[last]
        c = self.bi.get(last)
        if not c or len(c) < 2:
            self.cache[last] = None; return None
        cands = [w for w, _ in c.most_common(K)]
        tot = sum(c.values())
        lv = self._nv(last)
        Vn = np.zeros((len(cands), self.dim)); base = np.zeros((len(cands), 3))
        for i, w in enumerate(cands):
            v = self._nv(w)
            if v is not None:
                Vn[i] = v
            base[i, 0] = math.log(c[w] / tot)                          # f1 transition
            base[i, 1] = float(v @ lv) if (v is not None and lv is not None) else 0.0  # f3 local
            base[i, 2] = math.log(self.freq.get(w, 1)) - self.logN     # f4 freq
        cidx = {w: i for i, w in enumerate(cands)}
        self.cache[last] = (cands, cidx, Vn, base)
        return self.cache[last]

    def feats(self, last, thread):
        e = self._entry(last)
        if e is None:
            return None
        cands, cidx, Vn, base = e
        tn = np.linalg.norm(thread)
        f2 = (Vn @ thread) / tn if tn > 0 else np.zeros(len(cands))    # f2 thread
        F = np.column_stack([base[:, 0], f2, base[:, 1], base[:, 2]])
        return cands, cidx, F

    def positions(self, stream, n, seed=0):
        thread = np.zeros(self.dim); data = []
        for i in range(len(stream) - 1):
            last, nxt = stream[i], stream[i + 1]
            e = self._entry(last)
            if e is not None and nxt in e[1]:
                data.append((last, nxt, thread.copy()))
            v = self._nv(stream[i])
            if stream[i] not in STOP and v is not None:
                thread = DECAY * thread + (1 - DECAY) * v
        rng = np.random.default_rng(seed); rng.shuffle(data)
        return data[:n]

    def train_theta(self, epochs=6, lr=0.3):
        data = self.positions(self.train, 8000)
        F0 = np.vstack([self.feats(l, th)[2] for l, _, th in data[:2000]])
        mu, sd = F0.mean(0), F0.std(0) + 1e-9
        theta = np.zeros(4)
        for ep in range(epochs):
            rng = np.random.default_rng(ep)
            for k in rng.permutation(len(data)):
                last, truth, th = data[k]
                cands, cidx, F = self.feats(last, th)
                F = (F - mu) / sd
                z = F @ theta; z -= z.max(); p = np.exp(z); p /= p.sum()
                y = np.zeros(len(cands)); y[cidx[truth]] = 1
                theta += lr * (F.T @ (y - p))
            lr *= 0.8
        self.theta, self.mu, self.sd = theta, mu, sd
        return theta

    def evaluate(self):
        data = self.positions(self.test, 4000, seed=99)
        h1 = {"bigram": 0, "hand": 0, "learned": 0}
        h5 = {"bigram": 0, "hand": 0, "learned": 0}
        n = 0
        for last, truth, th in data:
            cands, cidx, F = self.feats(last, th)
            ti = cidx[truth]; n += 1
            scores = {"bigram": F[:, 0], "hand": F[:, 0] + 1.6 * F[:, 1],
                      "learned": ((F - self.mu) / self.sd) @ self.theta}
            for nm, sc in scores.items():
                order = np.argsort(-sc)
                h1[nm] += int(order[0] == ti); h5[nm] += int(ti in order[:5])
        return h1, h5, n


def main():
    m = Learned()
    print("training the ⊕ ...", flush=True)
    theta = m.train_theta()
    for nm, t in zip(["transition(Psi_f)", "thread(Ns)", "local-meaning(Mc)", "freq-prior"], theta):
        print(f"   {nm:20} {t:+.3f}")
    h1, h5, n = m.evaluate()
    print(f"\nheld-out next-token over {n} positions:")
    print("   ranker   | top-1  | top-5")
    for k in ("bigram", "hand", "learned"):
        print(f"   {k:8} |  {100*h1[k]/n:4.1f}% |  {100*h5[k]/n:4.1f}%")
    print("\nLearned ⊕ tunes weights on fixed features. Ceiling: a transformer learns")
    print("the FEATURES too — the next rung. This is the on-substrate learned operator.")


if __name__ == "__main__":
    main()
