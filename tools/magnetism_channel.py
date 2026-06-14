#!/usr/bin/env python3
"""
Magnetism Channel — Synthesus 5 (the second force law)
Gravity (symmetric co-occurrence) says HOW RELATED two concepts are. It cannot
say anything DIRECTIONAL or OPPOSED, because attraction has no polarity.

Magnetism adds that missing axis. Polarity is derived, not hand-set, from the
ASYMMETRY of directed co-occurrence:

    D[i,j] = how often i appears just BEFORE j
    charge p_i = (out_i - in_i) / (out_i + in_i)     in [-1, +1]

p_i > 0  -> a "source/north" word that leads          (modifier, cause, general)
p_i < 0  -> a "sink/south" word that follows          (head, effect, specific)

Combined resonance = gravity (topical) AND magnetic agreement (same polarity).
Two words can be topically identical yet magnetically opposed -> the magnet
pulls them apart on the polarity axis while gravity keeps them in the family.
"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricRefinery
from cooccurrence_grounding import build_cooccurrence, ppmi, embed

CORPUS_FILE = "data/corpus/real_corpus.txt"


def directed_cooccurrence(tokens, idx, window=4):
    V = len(idx)
    D = np.zeros((V, V))
    seq = [idx[t] for t in tokens if t in idx]
    for i, wi in enumerate(seq):
        for j in range(i + 1, min(len(seq), i + window + 1)):
            D[wi, seq[j]] += 1.0          # wi precedes seq[j]
    return D


if __name__ == "__main__":
    r = GeometricRefinery()
    toks = r.clean_and_tokenize(open(CORPUS_FILE, encoding="utf-8").read())
    counts = {}
    for t in toks:
        counts[t] = counts.get(t, 0) + 1
    vocab = sorted(w for w, c in counts.items() if c >= 20)
    idx = {w: i for i, w in enumerate(vocab)}
    words = vocab

    # --- gravity channel (symmetric): topical position ---
    Wsym = ppmi(build_cooccurrence(toks, idx))
    G = embed(Wsym, 32)                              # rows L2-normalized
    grav = lambda a, b: float(G[idx[a]] @ G[idx[b]])

    # --- magnetism channel (asymmetric): derived from the dominant CIRCULATION ---
    # Net flow cancels in the margins; the signal lives in A = D - D^T (antisymmetric).
    D = directed_cooccurrence(toks, idx)
    A = D - D.T
    U, S, Vt = np.linalg.svd(A)                       # top mode = dominant word-order flow
    pol = U[:, 0] - Vt[0]
    pol = pol / (np.abs(pol).max() + 1e-9)            # global magnetic charge in [-1,1]
    P = {w: float(pol[idx[w]]) for w in words}

    # Robust per-pair directionality: does a precede b, or b precede a?
    def flow(a, b):
        da, db = D[idx[a], idx[b]], D[idx[b], idx[a]]
        return (da - db) / (da + db + 1e-9)           # >0: a leads b ; <0: b leads a

    print(f"vocab {len(words)}  |  gravity=32-dim cosine, magnetism=A=D−Dᵀ circulation\n")
    order = np.argsort(-pol)
    print("=== NORTH pole (lead the dominant flow) ===")
    print("   " + ", ".join(words[i] for i in order[:12]))
    print("=== SOUTH pole (follow it) ===")
    print("   " + ", ".join(words[i] for i in order[-12:]))

    pairs = [("space", "time"), ("general", "particular"), ("cause", "effect"),
             ("natural", "selection"), ("truth", "falsehood"), ("large", "small"),
             ("simple", "complex"), ("means", "end")]
    print("\n=== pair               gravity   flow(a→b)   reading ===")
    for a, b in pairs:
        if a in idx and b in idx:
            f = flow(a, b)
            rd = f"{a}→{b}" if f > 0.05 else (f"{b}→{a}" if f < -0.05 else "symmetric")
            print(f"  {a:>8}/{b:<10}     {grav(a,b):+.2f}      {f:+.2f}      {rd}")
        else:
            miss = a if a not in idx else b
            print(f"  {a:>8}/{b:<10}     (—  '{miss}' below min_count)")
    print("\nGravity gives one symmetric number (how related). Magnetism adds the")
    print("DIRECTION gravity structurally cannot carry: which concept leads.")
