#!/usr/bin/env python3
"""
The machinery of meaning — real vs synthetic association databases
==================================================================

Builds exactly what was proposed:
  (1) REAL association DB     — word -> co-occurring words, from a real corpus.
  (2) SYNTHETIC (structured)  — every real word RELABELED to a made-up word,
      same association structure preserved.
  (3) SYNTHETIC (random)      — made-up words with RANDOM associations.

Then we dissect: where does "meaning" (semantic clustering) live? In the words,
in the structure, or in the data being real?

Run:  ./venv/bin/python packages/reasoning/vsa_meaning_machinery.py
"""
from __future__ import annotations
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_twolayer import cooccurrence, ppmi, svd_embed  # noqa: E402

# corpus with 3 clear concept clusters (5 words each)
CORPUS = """
water flows in the ocean and the river and the lake when the rain falls.
the ocean and the river and the lake hold the water from the rain.
rain feeds the river the lake the ocean with fresh water again.
fire and flame give off heat as the burn makes thick smoke.
the flame and the fire burn with heat and rising smoke.
heat from the fire and the flame and the burn fills the smoke.
the sky holds the cloud and the star and the sun and the moon.
the sun and the moon and the star shine in the sky beyond the cloud.
the cloud drifts in the sky past the sun the moon and the star.
""".strip()

CLUSTERS = {
    "water": ["water", "ocean", "river", "lake", "rain"],
    "fire":  ["fire", "flame", "heat", "burn", "smoke"],
    "sky":   ["sky", "cloud", "star", "sun", "moon"],
}
STOP = set("the a an and in of on with from when off as give gives makes hold holds "
           "feeds fills shine shines drifts past beyond again rising thick falls flows fresh".split())
FAKE = ["glor", "fren", "tisk", "vorm", "plee", "krad", "snuth", "blicket", "zorp",
        "florp", "quax", "drempt", "wug", "fendle", "morb"]  # made-up words


def tokenize(t):
    return [w for w in re.findall(r"[a-z]+", t.lower()) if w not in STOP]


def vectors(tokens, vocab):
    vidx = {w: i for i, w in enumerate(vocab)}
    return svd_embed(ppmi(cooccurrence(tokens, vidx, window=6)), min(10, len(vocab))), vidx


def cluster_score(E, vidx, label_map):
    """avg within-cluster vs cross-cluster cosine (high gap = meaning present)."""
    def vec(w): return E[vidx[label_map[w]]]
    within, cross = [], []
    words = [w for c in CLUSTERS.values() for w in c]
    for i, a in enumerate(words):
        for b in words[i + 1:]:
            ca = next(c for c, ws in CLUSTERS.items() if a in ws)
            cb = next(c for c, ws in CLUSTERS.items() if b in ws)
            s = float(vec(a) @ vec(b) / ((np.linalg.norm(vec(a)) or 1) * (np.linalg.norm(vec(b)) or 1)))
            (within if ca == cb else cross).append(s)
    return np.mean(within), np.mean(cross)


def main():
    toks = tokenize(CORPUS)
    vocab = sorted(set(toks))
    real_map = {w: w for w in vocab}                       # identity

    # (1) REAL
    E, vidx = vectors(toks, vocab)
    w_r, c_r = cluster_score(E, vidx, real_map)

    # (2) SYNTHETIC structured: relabel every word -> a made-up word, keep structure
    relabel = {w: FAKE[i] for i, w in enumerate(vocab)}
    fake_tokens = [relabel[w] for w in toks]
    fake_vocab = sorted(set(fake_tokens))
    Ef, vidf = vectors(fake_tokens, fake_vocab)
    w_s, c_s = cluster_score(Ef, vidf, relabel)            # map real concept -> fake word
    print("=== made-up word neighbours (structure preserved) ===")
    for real_w in ("water", "fire", "sky"):
        fw = relabel[real_w]
        sims = Ef @ Ef[vidf[fw]]
        nb = [fake_vocab[j] for j in np.argsort(-sims) if fake_vocab[j] != fw][:4]
        inv = {v: k for k, v in relabel.items()}
        print(f"  {fw:8}(={real_w:6}) ~ " + ", ".join(f"{x}(={inv[x]})" for x in nb))

    # (3) SYNTHETIC random: made-up words, RANDOM associations
    rng = np.random.default_rng(0)
    shuffled = fake_tokens[:]; rng.shuffle(shuffled)
    Er, vidr = vectors(shuffled, fake_vocab)
    w_x, c_x = cluster_score(Er, vidr, relabel)

    print("\n=== the machinery: within-cluster vs cross-cluster similarity ===")
    print(f"  (1) REAL words, real structure       : within {w_r:+.2f}  cross {c_r:+.2f}  gap {w_r-c_r:+.2f}")
    print(f"  (2) FAKE words, REAL structure       : within {w_s:+.2f}  cross {c_s:+.2f}  gap {w_s-c_s:+.2f}")
    print(f"  (3) FAKE words, RANDOM structure     : within {w_x:+.2f}  cross {c_x:+.2f}  gap {w_x-c_x:+.2f}")

    print("\nDISSECTION:")
    print("  (1) vs (2): identical structure -> identical meaning. The made-up words")
    print("      cluster EXACTLY like the real ones. Meaning is NOT in the symbols.")
    print("  (2) vs (3): same fake symbols, but random associations -> meaning gone")
    print("      (gap collapses). Meaning is NOT in the symbols OR in 'being synthetic'.")
    print("  => The machinery of meaning is the ASSOCIATION STRUCTURE itself.")
    print("     Fake words work perfectly IF they carry real structure; the structure")
    print("     must come from real usage. Synthesis relabels meaning; it can't invent it.")


if __name__ == "__main__":
    main()
