#!/usr/bin/env python3
"""
Energy / Hopfield settling reasoner — the imagination organ — Synthesus 5
=========================================================================

Reasoning as ENERGY MINIMISATION: a noisy/partial cue is "settled" into the
nearest stored attractor by descending an energy surface. This is the rigorous,
GPU-shaped form of the "waves settle into a stable node" intuition — a MODERN
HOPFIELD network (Ramsauer et al. 2020, "Hopfield Networks is All You Need"):

    update:  xi <- X^T softmax(beta * X xi)      (== attention; converges fast)
    energy:  E(xi) = -lse(beta, X xi) + 1/2 xi.xi   (decreases each step)

X = stored patterns (here the GROUNDED concept coordinates, so it settles into
real meaning). It is the principled form of VSA cleanup, and an associative
*completion* engine: give it a corrupted/partial concept, it imagines the whole.

Role in the architecture: the GPU "imagination hemisphere". It proposes a
completed pattern; the symbolic layer verifies/tags it (grounded vs educated
guess). beta is the IMAGINATION TEMPERATURE: high beta = decisive recall, low
beta = blended/imaginative completion.

Core op is X@xi and X^T@softmax(...) -> dense matmuls, batchable over many cues:
CPU/NumPy here; a CuPy/torch swap runs it in parallel on GPU unchanged.

Run:  python3 packages/reasoning/vsa_hopfield.py
"""
from __future__ import annotations
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_twolayer import TwoLayerVSA  # noqa: E402


def _lse(z):                       # numerically stable log-sum-exp
    m = z.max()
    return m + np.log(np.exp(z - m).sum())


class ModernHopfield:
    def __init__(self, patterns: np.ndarray, labels, beta: float = 8.0):
        # L2-normalize stored attractors so overlap == cosine
        self.X = patterns / (np.linalg.norm(patterns, axis=1, keepdims=True) + 1e-9)
        self.labels = labels
        self.beta = beta

    def energy(self, xi):
        return float(-_lse(self.beta * (self.X @ xi)) + 0.5 * xi @ xi)

    def step(self, xi):
        z = self.beta * (self.X @ xi)
        z -= z.max()
        w = np.exp(z); w /= w.sum()
        return self.X.T @ w

    def settle(self, cue, steps=50, tol=1e-6):
        xi = cue / (np.linalg.norm(cue) + 1e-9)
        traj = [self.energy(xi)]
        for _ in range(steps):
            nxt = self.step(xi)
            traj.append(self.energy(nxt))
            if np.linalg.norm(nxt - xi) < tol:
                xi = nxt
                break
            xi = nxt
        return xi, traj

    def recall(self, cue, **kw):
        xi, traj = self.settle(cue, **kw)
        sims = self.X @ (xi / (np.linalg.norm(xi) + 1e-9))
        j = int(np.argmax(sims))
        return self.labels[j], float(sims[j]), traj

    # ── image-space batched fast path (settle many cues as one tensor op) ──
    # Identical math to settle(), reformulated so the whole batch settles in
    # parallel; a NumPy->CuPy backend swap runs it on GPU unchanged.
    def settle_batch(self, cues, steps: int = 50):
        XI = cues / (np.linalg.norm(cues, axis=1, keepdims=True) + 1e-9)  # [B,d]
        for _ in range(steps):
            Z = self.beta * (XI @ self.X.T)                # [B,N]
            Z -= Z.max(axis=1, keepdims=True)
            W = np.exp(Z); W /= W.sum(axis=1, keepdims=True)
            XI = W @ self.X                                # [B,d]
        return XI

    def recall_batch(self, cues, steps: int = 50):
        XI = self.settle_batch(np.atleast_2d(cues), steps=steps)
        sims = (XI / (np.linalg.norm(XI, axis=1, keepdims=True) + 1e-9)) @ self.X.T
        idx = np.argmax(sims, axis=1)
        return [(self.labels[int(j)], float(sims[i, int(j)])) for i, j in enumerate(idx)]

    @classmethod
    def from_concepts(cls, concepts, beta: float = 8.0, embedder=None):
        """Build a Hopfield whose attractors are embeddings of `concepts` from the
        embedding organ (MiniLM if installed, else grounded fallback)."""
        import os as _os, sys as _sys
        _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        from embedding_backend import get_embedder
        emb = embedder or get_embedder()
        X = emb.encode_batch(list(concepts))
        return cls(X, list(concepts), beta=beta)


def main():
    vsa = TwoLayerVSA()
    net = ModernHopfield(vsa.SEM, vsa.vocab, beta=8.0)
    rng = np.random.default_rng(0)
    print(f"stored {len(vsa.vocab)} grounded attractors x {vsa.SEM.shape[1]} dims\n")

    # ── A. energy descent: a noisy cue settles into an attractor ──
    target = "dog" if "dog" in vsa.vidx else vsa.vocab[0]
    clean = vsa.SEM[vsa.vidx[target]]
    cue = clean + 0.9 * rng.standard_normal(clean.shape)
    label, conf, traj = net.recall(cue)
    print(f"=== A. settling a noisy '{target}' cue ===")
    print("  energy: " + " -> ".join(f"{e:.3f}" for e in traj[:5]) +
          (" ..." if len(traj) > 5 else ""))
    print(f"  settled in {len(traj)-1} steps -> '{label}' (overlap {conf:.2f})  "
          f"monotone={'yes' if all(b <= a + 1e-9 for a, b in zip(traj, traj[1:])) else 'no'}\n")

    # ── B. recovery rate vs noise (associative completion) ──
    print("=== B. attractor recovery vs cue noise (30 trials/concept) ===")
    for sigma in (0.3, 0.6, 0.9, 1.3):
        hits = tot = 0
        for w in vsa.vocab:
            base = vsa.SEM[vsa.vidx[w]]
            for _ in range(30):
                noisy = base + sigma * rng.standard_normal(base.shape)
                lab, _, _ = net.recall(noisy)
                hits += int(lab == w); tot += 1
        print(f"  sigma={sigma:>3} -> {100*hits/tot:5.1f}% recovered")

    # ── C. imagination temperature: ambiguous cue between two concepts ──
    a, b = vsa.vocab[0], vsa.vocab[min(5, len(vsa.vocab)-1)]
    blend = 0.5 * (vsa.SEM[vsa.vidx[a]] + vsa.SEM[vsa.vidx[b]])
    print(f"\n=== C. beta as imagination temperature (cue = {a}+{b} blend) ===")
    for beta in (1.0, 4.0, 16.0):
        net.beta = beta
        lab, conf, _ = net.recall(blend)
        mode = "decisive recall" if conf > 0.9 else "blended / imaginative"
        print(f"  beta={beta:>4} -> '{lab}' overlap {conf:.2f}   ({mode})")

    print("\nThe organ settles cues into grounded attractors (energy descends);\n"
          "beta dials decisive recall <-> imaginative completion. Outputs feed the\n"
          "groundedness tagger: high overlap = grounded, low = educated guess.")


if __name__ == "__main__":
    main()
