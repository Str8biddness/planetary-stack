#!/usr/bin/env python3
"""
PPBRS proof-of-value — does the legacy spec compose with our grounded embeddings?

PPBRS maintains a Bayesian belief distribution over patterns, updated with a
von Mises-Fisher likelihood  L(c|p) = exp(beta * cos(c, e_p))  in log space.
The spec's math is sound — but its example embeddings are np.random.randn (and
its context encoder is char-hashing), i.e. NOISE. We already solved that:
grounding_derived.kn holds real co-occurrence embeddings. Feed those in and the
Bayesian layer reasons over meaning instead of noise.

This shows: (1) entropy drops as coherent evidence accumulates, (2) the posterior
concentrates on semantically correct patterns, (3) an incoherent query stays
uncertain — calibrated "I don't know", which our cosine-top-k composer can't do.
"""
import sys, os, json
import numpy as np
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
SHARD = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards/grounding_derived.kn")


class Activator:
    def __init__(self, words, E, beta=12.0):
        self.words = words
        self.E = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)
        self.beta = beta
        self.logp = np.full(len(words), -np.log(len(words)))   # uniform prior

    def update(self, ctx):
        ctx = ctx / (np.linalg.norm(ctx) + 1e-9)
        loglik = self.beta * (self.E @ ctx)                     # vMF log-likelihood
        lp = self.logp + loglik
        self.logp = lp - (np.max(lp) + np.log(np.sum(np.exp(lp - np.max(lp)))))
        return np.exp(self.logp)

    def entropy(self):
        p = np.exp(self.logp)
        return float(-np.sum(p * np.log(p + 1e-12)))

    def top(self, k=5):
        idx = np.argsort(-self.logp)[:k]
        return [(self.words[i], float(np.exp(self.logp[i]))) for i in idx]


def load():
    d = json.load(open(SHARD))["vectors"]
    words = list(d)
    return words, {w: np.array(v) for w, v in d.items()}, np.array([d[w] for w in words])


def run(label, evidence, words, vecs, E):
    print(f"\n=== {label}: evidence {evidence} ===")
    act = Activator(words, E)
    print(f"  start    entropy={act.entropy():.2f}  (uniform over {len(words)})")
    for w in evidence:
        if w not in vecs:
            print(f"  '{w}' not grounded — skipped"); continue
        act.update(vecs[w])
        tops = ", ".join(f"{t}:{p:.2f}" for t, p in act.top(4))
        print(f"  +{w:9} entropy={act.entropy():.2f}  top: {tops}")


if __name__ == "__main__":
    words, vecs, E = load()
    # 1. coherent physics evidence -> should converge, entropy should fall
    run("COHERENT", ["space", "time", "motion", "gravitation"], words, vecs, E)
    # 2. coherent biology evidence
    run("COHERENT", ["species", "varieties", "descent"], words, vecs, E)
    # 3. incoherent / cross-domain evidence -> should STAY uncertain
    run("INCOHERENT", ["species", "geometry", "fertility"], words, vecs, E)
