#!/usr/bin/env python3
"""
Two-layer VSA on co-occurrence coordinates — Synthesus 5
=========================================================

v1 (vsa_bind.py) proved structure survives binding, but the VERB role
mis-recovered. Root cause: we bound the *semantic* vector as the filler, and
semantically similar words ("bites" sits on top of dog/man/woman) are
structurally confusable, made worse by the 13-dim cap.

The fix is to stop overloading one vector with two jobs:

    IDENTITY layer  -> a random, high-D, near-orthogonal symbol per word.
                       Clean to bind/unbind. This carries STRUCTURE.
    SEMANTIC layer  -> the PPMI+SVD coordinate per word.
                       Carries MEANING (dog ~ wolf).
    ASSOCIATION     -> identity <-> semantic, so a recovered symbol can be
                       looked up for its meaning, and vice-versa.

Encode a sentence by binding ROLE keys to IDENTITIES:
    S = AGENT (x) id[subj]  +  ACTION (x) id[verb]  +  PATIENT (x) id[obj]

Unbind a role -> clean up against the identity codebook -> exact word ->
follow the association to its meaning. You get BOTH: perfect structural
recovery AND semantic generalization, in one fixed-D vector, no net.

Run:  python3 packages/reasoning/vsa_twolayer.py
"""
from __future__ import annotations
import re
import numpy as np

# Shared corpus / math with vsa_bind.py (same PPMI+SVD method as
# tools/cooccurrence_grounding.py).
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

D_ID = 1024  # identity (structure) dimensionality — decoupled from vocab size


# ---- distributional grounding (meaning) ----------------------------------
def tokenize(t):
    return re.findall(r"[a-z]+", t.lower())


def cooccurrence(tokens, vidx, window=4):
    V = len(vidx)
    C = np.zeros((V, V))
    seq = [vidx[t] for t in tokens if t in vidx]
    for i, wi in enumerate(seq):
        for j in range(max(0, i - window), min(len(seq), i + window + 1)):
            if j != i:
                C[wi, seq[j]] += 1.0
    return C


def ppmi(C):
    total = C.sum()
    if not total:
        return C
    row, col = C.sum(1, keepdims=True), C.sum(0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log((C * total) / (row * col))
    pmi[~np.isfinite(pmi)] = 0.0
    return np.maximum(pmi, 0.0)


def svd_embed(M, dims):
    U, S, _ = np.linalg.svd(M, full_matrices=False)
    E = U[:, :dims] * np.sqrt(S[:dims])
    n = np.linalg.norm(E, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return E / n


# ---- HRR algebra ----------------------------------------------------------
def bind(a, b):
    return np.fft.irfft(np.fft.rfft(a) * np.fft.rfft(b), n=len(a))


def unbind(c, a):
    return np.fft.irfft(np.fft.rfft(c) * np.conj(np.fft.rfft(a)), n=len(c))


def bundle(vs):
    s = np.sum(vs, axis=0)
    nrm = np.linalg.norm(s)
    return s / nrm if nrm else s


def nearest(probe, codebook, labels, k=3):
    p = probe / (np.linalg.norm(probe) or 1.0)
    sims = codebook @ p
    return [(labels[j], float(sims[j])) for j in np.argsort(-sims)[:k]]


class TwoLayerVSA:
    def __init__(self, corpus=CORPUS, sem_dims=64, d_id=D_ID, seed=7):
        toks = tokenize(corpus)
        counts = {}
        for t in toks:
            counts[t] = counts.get(t, 0) + 1
        self.vocab = sorted(w for w, c in counts.items()
                            if c >= 2 and w not in STOP)
        self.vidx = {w: i for i, w in enumerate(self.vocab)}

        # SEMANTIC layer
        d = min(sem_dims, len(self.vocab))
        self.SEM = svd_embed(ppmi(cooccurrence(toks, self.vidx)), d)

        # IDENTITY layer — random, unit-norm, near-orthogonal symbols
        rng = np.random.default_rng(seed)
        ID = rng.standard_normal((len(self.vocab), d_id))
        self.ID = ID / np.linalg.norm(ID, axis=1, keepdims=True)

        # ROLE keys (also identity-space, so binding is clean)
        self.roles = {}
        for r in ("AGENT", "ACTION", "PATIENT"):
            v = rng.standard_normal(d_id)
            self.roles[r] = v / np.linalg.norm(v)

    # identity <-> meaning association
    def meaning_of(self, word, k=3):
        return nearest(self.SEM[self.vidx[word]], self.SEM, self.vocab, k + 1)[1:]

    def encode(self, subj, verb, obj):
        return bundle([
            bind(self.roles["AGENT"],   self.ID[self.vidx[subj]]),
            bind(self.roles["ACTION"],  self.ID[self.vidx[verb]]),
            bind(self.roles["PATIENT"], self.ID[self.vidx[obj]]),
        ])

    def recover(self, S, role):
        word, conf = nearest(unbind(S, self.roles[role]), self.ID, self.vocab, 1)[0]
        return word, conf


def main():
    m = TwoLayerVSA()
    print(f"vocab {len(m.vocab)}  |  semantic dims {m.SEM.shape[1]}  |  "
          f"identity dims {m.ID.shape[1]}\n")

    print("=== meaning layer still real (dog ~ wolf?) ===")
    for w in ("dog", "fox", "man"):
        print(f"  {w:5} ~ " + ", ".join(f"{x}({s:.2f})" for x, s in m.meaning_of(w)))

    s1 = m.encode("dog", "bites", "man")
    s2 = m.encode("man", "bites", "dog")
    cos = float(s1 @ s2 / ((np.linalg.norm(s1) or 1) * (np.linalg.norm(s2) or 1)))
    print(f"\n=== structure: 'dog bites man' vs 'man bites dog'  cosine = {cos:.3f} "
          f"(distinct) ===")

    print("\n=== role recovery (identity unbind -> exact word -> its meaning) ===")
    for role, truth in (("AGENT", "dog"), ("ACTION", "bites"), ("PATIENT", "man")):
        word, conf = m.recover(s1, role)
        ok = "OK " if word == truth else "XX "
        mean = ", ".join(f"{x}" for x, _ in m.meaning_of(word, 2))
        print(f"  [{ok}] {role:8} -> {word:6} ({conf:.2f})   meaning~ {mean}")

    # stress: recover all roles across several distinct sentences
    print("\n=== recovery accuracy over 6 sentences ===")
    trials = [("dog", "bites", "man"), ("man", "feeds", "dog"),
              ("wolf", "chases", "fox"), ("fox", "bites", "cat"),
              ("woman", "sees", "wolf"), ("child", "feeds", "cat")]
    hits = tot = 0
    for s, v, o in trials:
        S = m.encode(s, v, o)
        for role, truth in (("AGENT", s), ("ACTION", v), ("PATIENT", o)):
            tot += 1
            hits += (m.recover(S, role)[0] == truth)
    print(f"  {hits}/{tot} roles recovered correctly "
          f"({100 * hits / tot:.0f}%)")


if __name__ == "__main__":
    main()
