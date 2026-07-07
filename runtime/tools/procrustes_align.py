#!/usr/bin/env python3
"""
Procrustes Anchor-Alignment — Synthesus 5 (gyroscopic stability)
Every fresh embedding build lands in an arbitrary rotated frame (SVD basis is
only defined up to rotation). Two builds of "the same" geometry therefore
DISAGREE coordinate-for-coordinate — this is the drift that makes shards from
different ingestion runs incompatible.

Fix: lock a few hand-grounded ANCHOR concepts as a fixed reference frame and
orthogonally rotate every new build onto them (orthogonal Procrustes). Like a
gyroscope, a small fixed reference holds the whole frame steady.

    R = argmin_R || B_anchors @ R - A_anchors ||   s.t. RᵀR = I
      = U Vᵀ   where  U S Vᵀ = svd(B_anchorsᵀ A_anchors)
"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricRefinery
from cooccurrence_grounding import build_cooccurrence, ppmi, embed

CORPUS_FILE = "data/corpus/real_corpus.txt"


def random_orthogonal(d, seed=0):
    Q, _ = np.linalg.qr(np.random.RandomState(seed).randn(d, d))
    return Q


def procrustes(B_anchor, A_anchor):
    """Orthogonal R minimizing ||B_anchor R - A_anchor||."""
    U, _, Vt = np.linalg.svd(B_anchor.T @ A_anchor)
    return U @ Vt


def mean_self_cosine(A, B):
    """Average cosine between the SAME word's vector in builds A and B."""
    An = A / (np.linalg.norm(A, axis=1, keepdims=True) + 1e-9)
    Bn = B / (np.linalg.norm(B, axis=1, keepdims=True) + 1e-9)
    return float(np.mean(np.sum(An * Bn, axis=1)))


if __name__ == "__main__":
    dims = 64
    r = GeometricRefinery()
    toks = r.clean_and_tokenize(open(CORPUS_FILE, encoding="utf-8").read())
    counts = {}
    for t in toks:
        counts[t] = counts.get(t, 0) + 1
    vocab = sorted(w for w, c in counts.items() if c >= 20)
    idx = {w: i for i, w in enumerate(vocab)}
    A = embed(ppmi(build_cooccurrence(toks, idx)), dims)   # reference build
    print(f"reference build: vocab {len(vocab)}, {dims} dims")

    # Simulate a fresh ingestion run: same geometry, drifted (rotated) frame.
    B = A @ random_orthogonal(dims, seed=7)

    print(f"drift before alignment: mean self-cosine = {mean_self_cosine(A, B):+.3f}\n")
    print("=== anchor budget: it takes ~D anchors to lock a D-dim frame ===")
    print(f"{'#anchors':>9} | {'non-anchor agreement after align':>34}")
    rng = np.random.RandomState(1)
    for k in [8, 16, 32, 48, 64, 96, 128, 256]:
        if k > len(vocab):
            break
        ai = sorted(rng.choice(len(vocab), size=k, replace=False).tolist())
        R = procrustes(B[ai], A[ai])
        B_aligned = B @ R
        non = [i for i in range(len(vocab)) if i not in set(ai)]
        score = mean_self_cosine(A[non], B_aligned[non])
        bar = "█" * int(max(0, score) * 30)
        print(f"{k:>9} | {score:+.3f}  {bar}")
    print(f"\n→ once anchors ≥ D ({dims}), a fixed reference set re-locks the "
          f"ENTIRE rotated frame (cosine → 1.0).")
    print("  This is the 'gyroscope': hold enough fixed axes and the whole "
          "field stays oriented across ingestion runs.")
