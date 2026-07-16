#!/usr/bin/env python3
"""
Co-occurrence Grounding — Synthesus 5 (ideas 1+2+4)
Derives MEANINGFUL geometric coordinates from word statistics — no hash, no
neural network, no transformer. Pure linear algebra:

    text -> co-occurrence counts -> PPMI -> truncated SVD -> coordinates

Words that appear in similar contexts land near each other, automatically,
across the whole vocabulary. This is the classical distributional-semantics
(LSA / GloVe-family) method, expressed as geometry. Dimensionality is a knob
(idea 4): 5 axes barely separates; 32 separates cleanly with the same kernel.
"""
import sys, os, json, math, argparse
import numpy as np
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricRefinery

SHARD_DIR = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")

# Function words carry grammar, not topic — excluded from the concept vocabulary
# so the derived families are content words, and so a query keys off 'space',
# not 'the'. Shared with the composer.
STOPWORDS = set("""
a an the and or but if then else of to in into from on at by for with without about
as is are was were be been being it its it's this that these those there here when
where which who whom whose what why how all any both each few more most other some
such no nor not only own same so than too very can will just should now i you he she
we they me him her us them my your his our their mine yours ours theirs am do does did
doing have has had having would could may might must shall let also upon among between
out up down over under again further once because while during before after above below
tell explain describe define discuss show give regarding concerning mention about thing
things know say said way regards cannot
""".split())

# Compact multi-domain corpus so co-occurrence has signal. Point --corpus at a
# real file (your 100TB firehose) to scale this to the full vocabulary.
CORPUS = """
the river flows into the sea and the ocean tide carries water to the lake.
rain falls from the sky and feeds the river and the stream and the lake.
the ocean wave moves water across the sea while the river current runs to shore.
the mind learns through thought and reason building knowledge and intelligence.
intelligence grows as the mind gathers knowledge through learning and logic.
clear thought and careful reason sharpen the mind and deepen knowledge.
energy flows as heat and power while electric current carries charge and force.
the motor converts energy into motion using electric power and current.
heat is energy and the charge moves through the wire carrying electric force.
gravity pulls mass through space as the planet follows its orbit around the star.
the star burns in deep space while the planet and its mass trace an orbit.
space holds the planet the star and the cosmos bound by gravity and mass.
truth rests on fact and evidence and honest proof gives us certainty.
we seek truth through fact and proof testing evidence to reach certainty.
honesty and proof reveal truth while fact and evidence resist doubt.
peace brings calm and quiet a gentle harmony of stillness and serenity.
in calm and quiet the mind finds peace harmony and a deep stillness.
serenity and calm settle the heart into peace quiet and stillness.
the forest and the tree grow from the earth and soil under the open sky.
nature fills the forest with tree and plant rooted in earth and soil.
the mountain rises over the forest while the river runs through the earth.
water and energy and nature shape the world that the mind seeks to understand.
the river runs through the forest as nature carries water across the earth.
power and force move mass while energy and motion shape the planet and its orbit.
knowledge of truth and fact helps the mind reason toward certainty and proof.
""".strip()


def build_cooccurrence(tokens, vocab_idx, window=4):
    V = len(vocab_idx)
    C = np.zeros((V, V), dtype=np.float64)
    seq = [vocab_idx[t] for t in tokens if t in vocab_idx]
    for i, wi in enumerate(seq):
        lo, hi = max(0, i - window), min(len(seq), i + window + 1)
        for j in range(lo, hi):
            if j != i:
                C[wi, seq[j]] += 1.0
    return C


def ppmi(C):
    total = C.sum()
    if total == 0:
        return C
    row = C.sum(axis=1, keepdims=True)
    col = C.sum(axis=0, keepdims=True)
    with np.errstate(divide='ignore', invalid='ignore'):
        pmi = np.log((C * total) / (row * col))
    pmi[~np.isfinite(pmi)] = 0.0
    return np.maximum(pmi, 0.0)


def embed(M, dims):
    U, S, _ = np.linalg.svd(M, full_matrices=False)
    E = U[:, :dims] * np.sqrt(S[:dims])
    # L2 normalize -> cosine resonance == dot product
    n = np.linalg.norm(E, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return E / n


def neighbors(word, words, E, k=6):
    if word not in words:
        return []
    i = words.index(word)
    sims = E @ E[i]
    order = np.argsort(-sims)
    return [(words[j], float(sims[j])) for j in order if j != i][:k]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", help="path to a text corpus (defaults to built-in)")
    ap.add_argument("--dims", type=int, default=32)
    ap.add_argument("--min-count", type=int, default=2)
    args = ap.parse_args()

    text = open(args.corpus, encoding="utf-8").read() if args.corpus else CORPUS
    refinery = GeometricRefinery()
    tokens = refinery.clean_and_tokenize(text)

    counts = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    vocab = sorted([w for w, c in counts.items()
                    if c >= args.min_count and w not in STOPWORDS])
    vocab_idx = {w: i for i, w in enumerate(vocab)}
    print(f"corpus: {len(tokens)} tokens, vocab {len(vocab)} (min_count={args.min_count})")

    M = ppmi(build_cooccurrence(tokens, vocab_idx))

    print("\n=== nearest concepts by RESONANCE (derived from statistics, no hash) ===")
    probes = ["water", "intelligence", "energy", "space", "truth", "peace", "nature"]
    for dims in (5, args.dims):
        E = embed(M, min(dims, len(vocab)))
        print(f"\n-- {dims} dimensions --")
        for p in probes:
            nbrs = neighbors(p, vocab, E, k=5)
            print(f"  {p:13} -> " + ", ".join(f"{w}({s:.2f})" for w, s in nbrs))

    # Emit the FULL-dimensional derived grounding the runtime consumes.
    Efull = embed(M, min(args.dims, len(vocab)))
    out = {"metadata": {"source": "cooccurrence_grounding.py",
                        "dimensions": Efull.shape[1],
                        "method": "PPMI+SVD distributional semantics (L2-normalized)"},
           "vectors": {w: [round(float(x), 6) for x in Efull[i]]
                       for w, i in vocab_idx.items()}}
    path = SHARD_DIR / "grounding_derived.kn"
    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\n💾 Derived grounding saved: {path}  "
          f"({len(vocab)} concepts × {Efull.shape[1]} dims)")
