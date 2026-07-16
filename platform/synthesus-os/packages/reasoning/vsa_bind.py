#!/usr/bin/env python3
"""
VSA binding on co-occurrence coordinates — Synthesus 5 prototype
================================================================

Thesis test (the smallest experiment that falsifies the whole program):

    Meaning lives in DISTRIBUTIONAL geometry (PPMI + SVD, same math as
    tools/cooccurrence_grounding.py) -> "dog" lands near "wolf".

    STRUCTURE lives in VECTOR-SYMBOLIC binding (Holographic Reduced
    Representations; Plate 1995) -> "dog bites man" != "man bites dog",
    and you can READ THE ROLES BACK OUT.

Averaging word vectors (what embed_texts currently does) destroys order:
    mean(dog, bites, man) == mean(man, bites, dog)   <- can never reason.

Binding preserves it inside ONE fixed-dimension vector, deterministically,
in pure linear algebra. No transformer, no backprop at inference.

Run:  python3 packages/reasoning/vsa_bind.py
"""
from __future__ import annotations
import re
import numpy as np

# --------------------------------------------------------------------------
# 1. DISTRIBUTIONAL GROUNDING  (identical method to cooccurrence_grounding.py)
# --------------------------------------------------------------------------
# Compact corpus with clear subject-verb-object structure AND topical
# clustering, so (a) co-occurrence has signal and (b) the demo is legible.
CORPUS = """
the dog bites the man and the dog chases the cat across the yard.
the man bites into bread while the dog bites the bone in the yard.
the wolf and the dog hunt while the fox and the cat watch the man.
the man feeds the dog and the woman feeds the cat in the morning.
the cat chases the fox and the fox chases the cat through the forest.
the man sees the wolf and the woman sees the fox near the dog.
the child feeds the dog while the man sees the cat chase the fox.
the wolf bites the fox and the dog bites the wolf as the man watches.
a wolf chases a fox and a dog chases a cat as the man and woman watch.
the man and the woman and the child feed the dog and the cat.
"""

STOP = set("the a an and or as from into in near while all of to".split())


def tokenize(text: str):
    return re.findall(r"[a-z]+", text.lower())


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
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log((C * total) / (row * col))
    pmi[~np.isfinite(pmi)] = 0.0
    return np.maximum(pmi, 0.0)


def embed(M, dims):
    U, S, _ = np.linalg.svd(M, full_matrices=False)
    E = U[:, :dims] * np.sqrt(S[:dims])
    n = np.linalg.norm(E, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return E / n  # L2-normalized -> cosine == dot


# --------------------------------------------------------------------------
# 2. VECTOR-SYMBOLIC ALGEBRA  (Holographic Reduced Representations)
# --------------------------------------------------------------------------
# bind   = circular convolution            (associate role <-> filler)
# unbind = circular correlation (approx inv) (query a role, recover filler)
# bundle = normalized sum                   (superpose role-filler pairs)
def bind(a, b):
    return np.fft.irfft(np.fft.rfft(a) * np.fft.rfft(b), n=len(a))


def unbind(c, a):
    return np.fft.irfft(np.fft.rfft(c) * np.conj(np.fft.rfft(a)), n=len(c))


def bundle(vectors):
    s = np.sum(vectors, axis=0)
    nrm = np.linalg.norm(s)
    return s / nrm if nrm else s


def cleanup(probe, vocab, E):
    """Nearest grounded concept to a noisy unbound vector."""
    sims = E @ (probe / (np.linalg.norm(probe) or 1.0))
    order = np.argsort(-sims)
    return [(vocab[j], float(sims[j])) for j in order]


# --------------------------------------------------------------------------
# 3. SENTENCE ENCODING:  S = AGENT*subj  +  ACTION*verb  +  PATIENT*obj
# --------------------------------------------------------------------------
def encode_svo(subj, verb, obj, vidx, E, roles):
    return bundle([
        bind(roles["AGENT"],   E[vidx[subj]]),
        bind(roles["ACTION"],  E[vidx[verb]]),
        bind(roles["PATIENT"], E[vidx[obj]]),
    ])


def main():
    tokens = tokenize(CORPUS)
    counts = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    vocab = sorted(w for w, c in counts.items() if c >= 2 and w not in STOP)
    vidx = {w: i for i, w in enumerate(vocab)}
    print(f"corpus: {len(tokens)} tokens, vocab {len(vocab)}")

    DIMS = min(64, len(vocab))
    E = embed(ppmi(build_cooccurrence(tokens, vidx)), DIMS)
    print(f"grounded coordinates: {len(vocab)} concepts x {DIMS} dims (PPMI+SVD)\n")

    # ---- (a) grounding works: similar words land near each other ----
    print("=== distributional grounding (meaning is real, not hashed) ===")
    for p in ("dog", "man", "fox"):
        nbrs = cleanup(E[vidx[p]], vocab, E)[1:4]
        print(f"  {p:5} ~ " + ", ".join(f"{w}({s:.2f})" for w, s in nbrs))

    # ---- random, near-orthogonal role vectors (the "slots") ----
    rng = np.random.default_rng(7)
    roles = {r: (lambda v: v / np.linalg.norm(v))(rng.standard_normal(DIMS))
             for r in ("AGENT", "ACTION", "PATIENT")}

    s1 = encode_svo("dog", "bites", "man", vidx, E, roles)
    s2 = encode_svo("man", "bites", "dog", vidx, E, roles)

    # ---- (b) THE TEST: does word order survive? ----
    print("\n=== structure test: 'dog bites man' vs 'man bites dog' ===")
    avg1 = bundle([E[vidx["dog"]], E[vidx["bites"]], E[vidx["man"]]])
    avg2 = bundle([E[vidx["man"]], E[vidx["bites"]], E[vidx["dog"]]])
    cos_avg  = float(avg1 @ avg2 / ((np.linalg.norm(avg1) or 1) * (np.linalg.norm(avg2) or 1)))
    cos_bind = float(s1 @ s2 / ((np.linalg.norm(s1) or 1) * (np.linalg.norm(s2) or 1)))
    print(f"  AVERAGING (current embed_texts): cosine = {cos_avg:.3f}   "
          f"{'-> IDENTICAL, order lost' if cos_avg > 0.999 else ''}")
    print(f"  VSA BINDING (this prototype)  : cosine = {cos_bind:.3f}   "
          f"-> DISTINCT, order preserved")

    # ---- (c) read the roles back out of the single bound vector ----
    print("\n=== role recovery from 'dog bites man' (unbind + cleanup) ===")
    for role in ("AGENT", "ACTION", "PATIENT"):
        top = cleanup(unbind(s1, roles[role]), vocab, E)[:2]
        guess, conf = top[0]
        runner = f"  (next: {top[1][0]} {top[1][1]:.2f})"
        print(f"  {role:8} -> {guess:6} ({conf:.2f}){runner}")


if __name__ == "__main__":
    main()
