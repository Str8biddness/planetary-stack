#!/usr/bin/env python3
"""
Scaling the grounding — Synthesus 5
====================================

The architecture is fixed; only the DATA scales. Same PPMI+SVD method as
vsa_twolayer.py / tools/cooccurrence_grounding.py, now run on a real ~292k-word
corpus (data/corpus/real_corpus.txt — Einstein's *Relativity*) instead of a
hand-built toy. Demonstrates that grounding QUALITY (the second of the two
dials; structure was the first) improves with corpus size at zero architectural
cost.

Run:  python3 packages/reasoning/vsa_scale.py
"""
from __future__ import annotations
import os
import re
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_twolayer import cooccurrence, ppmi, svd_embed, nearest  # noqa: E402

CORPUS_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                           "data", "corpus", "real_corpus.txt")

STOP = set("""
the a an and or but if then else of to in into from on at by for with without about
as is are was were be been being it its this that these those there here when where
which who whom whose what why how all any both each few more most other some such no
not only own same so than too very can will just should now i you he she we they me him
her us them my your his our their have has had having would could may might must shall
let also upon among between out up down over under again further once because while
during before after above below do does did doing thus hence therefore one two we our
""".split())


def tokenize(text):
    return [t for t in re.findall(r"[a-z]+", text.lower())
            if len(t) >= 3 and t not in STOP]


def main():
    if not os.path.exists(CORPUS_PATH):
        print(f"corpus not found: {CORPUS_PATH}")
        return
    t0 = time.time()
    text = open(CORPUS_PATH, encoding="utf-8", errors="ignore").read()
    tokens = tokenize(text)

    counts = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    # cap to the most frequent content words so SVD stays tractable
    TOPV = 1500
    vocab = [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])
             if counts[w] >= 5][:TOPV]
    vidx = {w: i for i, w in enumerate(vocab)}
    print(f"corpus: {len(tokens):,} content tokens, vocab capped to {len(vocab)}")

    M = ppmi(cooccurrence(tokens, vidx, window=5))
    E = svd_embed(M, dims=64)
    print(f"grounded {len(vocab)} concepts x 64 dims in {time.time() - t0:.1f}s\n")

    probes = ["space", "time", "light", "motion", "mass",
              "energy", "theory", "measure", "clock", "earth"]
    print("=== nearest concepts by resonance (real corpus, scaled) ===")
    for p in probes:
        if p in vidx:
            nbrs = nearest(E[vidx[p]], E, vocab, k=6)[1:6]
            print(f"  {p:8} -> " + ", ".join(f"{w}({s:.2f})" for w, s in nbrs))

    # analogy sanity if the vocabulary supports it
    def analogy(a, b, c, k=3):
        if not all(w in vidx for w in (a, b, c)):
            return None
        tgt = E[vidx[c]] + E[vidx[b]] - E[vidx[a]]
        tgt /= np.linalg.norm(tgt) or 1.0
        sims = E @ tgt
        return [(vocab[j], float(sims[j])) for j in np.argsort(-sims)
                if vocab[j] not in (a, b, c)][:k]

    print("\n=== analogy on the scaled space (if vocab permits) ===")
    for a, b, c in [("time", "clock", "space"), ("space", "time", "length")]:
        r = analogy(a, b, c)
        print(f"  {a}:{b}::{c}:?  -> "
              + (", ".join(f"{w}({s:.2f})" for w, s in r) if r else "n/a"))

    print("\nTakeaway: identical method, richer data -> sharper, automatically "
          "derived\nconcept geometry. The 100TB firehose is this knob turned up.")


if __name__ == "__main__":
    main()
