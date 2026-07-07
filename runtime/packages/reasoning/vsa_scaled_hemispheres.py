#!/usr/bin/env python3
"""
Scaled grounding across the hemispheres — Synthesus 5
=====================================================

Scales the SHARED semantic substrate to the real ~292k-word corpus (Einstein's
*Relativity*) and runs the grounding-dependent hemispheres on it:

  * associative imagination (Hopfield settling, vsa_hopfield)
  * analogy (vector translation)
  * similarity / neighbours

All three are pure functions of the coordinate space, so scaling the corpus
scales them directly — no architecture change. This also tests whether scale
fixes the Hopfield capacity weakness seen at 13 toy dims.

HONEST SCOPE: the STRUCTURED hemispheres (symbolic composition's fact-store,
abstraction's entailment taxonomy) need *relations* (facts, is-a edges), which
raw text does not provide. They scale via relation EXTRACTION (e.g. the
distributional-inclusion hypothesis for hypernyms) — a separate frontier, not
shown here.

Run:  python3 packages/reasoning/vsa_scaled_hemispheres.py
"""
from __future__ import annotations
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_twolayer import cooccurrence, ppmi, svd_embed, nearest  # noqa: E402
from vsa_scale import tokenize, CORPUS_PATH                       # noqa: E402
from vsa_hopfield import ModernHopfield                          # noqa: E402

DIMS = 128       # capacity scales with dimensionality (toy was 13)
TOPV = 1500


def build_grounding():
    text = open(CORPUS_PATH, encoding="utf-8", errors="ignore").read()
    tokens = tokenize(text)
    counts = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    vocab = [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])
             if counts[w] >= 5][:TOPV]
    vidx = {w: i for i, w in enumerate(vocab)}
    E = svd_embed(ppmi(cooccurrence(tokens, vidx, window=5)), DIMS)
    return E, vocab, vidx, len(tokens)


def main():
    t0 = time.time()
    E, vocab, vidx, ntok = build_grounding()
    hop = ModernHopfield(E, vocab, beta=20.0)
    rng = np.random.default_rng(0)
    print(f"scaled grounding: {ntok:,} tokens -> {len(vocab)} concepts x {DIMS} "
          f"dims in {time.time()-t0:.1f}s\n")

    # 1) shared substrate: physics-accurate neighbours
    print("=== similarity hemisphere (shared substrate) ===")
    for p in ("space", "time", "light", "mass", "gravitation"):
        if p in vidx:
            nb = nearest(E[vidx[p]], E, vocab, k=5)[1:5]
            print(f"  {p:11} ~ " + ", ".join(f"{w}({s:.2f})" for w, s in nb))

    # 2) imagination hemisphere: Hopfield recovery vs CORRUPTION.
    # Noise is sized RELATIVE to the unit-norm signal (norm = frac), so the test
    # is comparable across dimensionalities (fixed per-component sigma is not:
    # its norm grows like sqrt(dims) and swamps the signal at high dims).
    print("\n=== imagination hemisphere: Hopfield recovery vs corruption ===")
    sample = vocab[:200]
    for frac in (0.3, 0.6, 0.9, 1.2):
        hits = 0
        for w in sample:
            n = rng.standard_normal(DIMS)
            n *= frac / (np.linalg.norm(n) + 1e-9)     # ||noise|| == frac
            lab, _, _ = hop.recall(E[vidx[w]] + n)
            hits += int(lab == w)
        print(f"  corruption={frac:>3} of signal -> {100*hits/len(sample):5.1f}% recovered")

    # 3) imagination settling a multi-concept physics cue
    print("\n=== imagination settling (multi-concept cue) ===")
    for terms in (["space", "time"], ["mass", "energy"], ["light", "velocity"]):
        present = [t for t in terms if t in vidx]
        if not present:
            continue
        cue = np.mean([E[vidx[t]] for t in present], axis=0)
        lab, ov, _ = hop.recall(cue)
        print(f"  {'+'.join(present):20} -> settles toward '{lab}' (overlap {ov:.2f})")

    # 4) analogy on the scaled space
    print("\n=== analogy hemisphere (scaled) ===")
    def analogy(a, b, c, k=3):
        if not all(w in vidx for w in (a, b, c)):
            return None
        t = E[vidx[c]] + E[vidx[b]] - E[vidx[a]]
        t /= np.linalg.norm(t) or 1.0
        sims = E @ t
        return [(vocab[j], float(sims[j])) for j in np.argsort(-sims)
                if vocab[j] not in (a, b, c)][:k]
    for a, b, c in [("space", "time", "length"), ("mass", "energy", "force")]:
        r = analogy(a, b, c)
        print(f"  {a}:{b}::{c}:?  -> " + (", ".join(f"{w}({s:.2f})" for w, s in r)
                                          if r else "n/a"))

    print("\nThe grounding-dependent hemispheres (imagination, analogy, similarity)\n"
          "scale to the real corpus directly; capacity rises with dims. Structured\n"
          "hemispheres (symbolic facts, entailment taxonomy) need relation\n"
          "extraction — the remaining frontier.")


if __name__ == "__main__":
    main()
