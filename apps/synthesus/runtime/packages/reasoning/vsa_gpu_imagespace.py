#!/usr/bin/env python3
"""
Image-space GPU optimization of the reasoning settle — Synthesus 5
==================================================================

The spatial/image-space math insight, applied to reasoning: a BATCH of reasoning
states is an IMAGE (B states x d dims = a B*d tensor). Settling that whole image
at once is one parallel tensor op (batched matmul + softmax) instead of a Python
loop over states — which is exactly the GPU's native path (the same parallel
per-element transform anaglyph/texture math rides).

Backend-agnostic: NumPy here (CPU); set the backend to CuPy and the identical
code runs on GPU. The CPU batched-vs-loop speedup is a conservative PROXY for the
GPU win (GPU adds thousands of parallel lanes on top).

  per-state loop:  for each cue:  xi <- X^T softmax(beta X xi)        (serial)
  image-space:     XI <- softmax(beta * C @ X^T) @ X   over ALL cues  (parallel)

Run:  python3 packages/reasoning/vsa_gpu_imagespace.py
"""
from __future__ import annotations
import os
import sys
import time

# ── backend: GPU if CuPy is present, else CPU NumPy (identical code path) ──
try:
    import cupy as xp                     # noqa: F401
    BACKEND = "cupy (GPU)"
except Exception:
    import numpy as xp
    BACKEND = "numpy (CPU)"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_scaled_hemispheres import build_grounding  # noqa: E402


def _norm_rows(M):
    return M / (xp.linalg.norm(M, axis=1, keepdims=True) + 1e-9)


def settle_loop(X, cues, beta, steps):
    """Per-state settle (serial) — one cue at a time."""
    out = xp.empty_like(cues)
    for i in range(cues.shape[0]):
        xi = cues[i] / (xp.linalg.norm(cues[i]) + 1e-9)
        for _ in range(steps):
            z = beta * (X @ xi)
            z -= z.max()
            w = xp.exp(z); w /= w.sum()
            xi = X.T @ w
        out[i] = xi
    return out


def settle_image(X, cues, beta, steps):
    """Image-space settle (parallel) — the whole batch as one tensor op."""
    XI = _norm_rows(cues)                         # [B, d]
    for _ in range(steps):
        Z = beta * (XI @ X.T)                     # [B, N]
        Z -= Z.max(axis=1, keepdims=True)
        W = xp.exp(Z); W /= W.sum(axis=1, keepdims=True)
        XI = W @ X                                # [B, d]
    return XI


def main():
    import numpy as np
    E, vocab, vidx, ntok = build_grounding()      # real-corpus attractors
    X = _norm_rows(xp.asarray(E))
    N, d = X.shape
    B, beta, steps = 512, 20.0, 10
    rng = np.random.default_rng(0)
    cues = xp.asarray(E[rng.integers(0, N, B)] + 0.6 * rng.standard_normal((B, d)))

    print(f"backend = {BACKEND}")
    print(f"attractors {N} x {d}  |  batch {B} cues  |  {steps} settle steps\n")

    # correctness: image-space == loop (same recovered attractor per cue)
    Rl = settle_loop(X, cues, beta, steps)
    Ri = settle_image(X, cues, beta, steps)
    lab_l = xp.argmax(_norm_rows(Rl) @ X.T, axis=1)
    lab_i = xp.argmax(_norm_rows(Ri) @ X.T, axis=1)
    agree = float((lab_l == lab_i).mean())

    # timing
    t = time.time(); settle_loop(X, cues, beta, steps);  t_loop = time.time() - t
    t = time.time(); settle_image(X, cues, beta, steps); t_img = time.time() - t

    print(f"correctness: image-space vs loop agree on {agree*100:.1f}% of cues")
    print(f"per-state loop : {t_loop*1000:7.1f} ms")
    print(f"image-space    : {t_img*1000:7.1f} ms")
    print(f"speedup        : {t_loop/max(t_img,1e-9):6.1f}x  (on {BACKEND})")
    print("\nSame math, reformulated as a parallel image-space tensor op. On CPU the\n"
          "win is BLAS vectorization; swap the backend to CuPy and the identical\n"
          "code runs on GPU, adding thousands of parallel lanes on top.")


if __name__ == "__main__":
    main()
