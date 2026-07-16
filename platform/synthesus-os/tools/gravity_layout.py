#!/usr/bin/env python3
"""
Gravity Layout — Synthesus 5 (N-body concept solar system)
Lays out concepts by physical forces on the co-occurrence graph:

  mass  m_i      = graph centrality (sum of a word's co-occurrence weight)
  ATTRACTION     = co-occurrence (PPMI) pulls related words together  (springs)
  REPULSION      = mass*mass / r^2 keeps the field from collapsing      (N-body)
  displacement   = F / m  -> heavy words barely move (suns), light words orbit

No hash, no neural net. Pure mechanics on statistics. Heavy hub words settle
into "suns" with their semantic families in orbit.
"""
import sys, os
import numpy as np
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricRefinery
from cooccurrence_grounding import build_cooccurrence, ppmi

CORPUS_FILE = "data/corpus/real_corpus.txt"


def simulate(W, mass, dims=2, steps=400, k_rep=0.02, k_attr=0.04, seed=1):
    N = len(mass)
    rng = np.random.RandomState(seed)
    X = rng.randn(N, dims) * 0.1
    m = mass / mass.mean()
    for s in range(steps):
        diff = X[:, None, :] - X[None, :, :]          # (N,N,d) i relative to j
        dist = np.sqrt((diff ** 2).sum(-1)) + 1e-3
        np.fill_diagonal(dist, np.inf)                # no self force
        # repulsion: gravity-magnitude but pushing apart, mass-weighted
        rep = (k_rep * (m[:, None] * m[None, :]) / dist ** 2)[:, :, None] * (diff / dist[:, :, None])
        # attraction: springs along co-occurrence edges
        attr = -k_attr * (W[:, :, None] * diff)
        F = rep.sum(1) + attr.sum(1)
        cool = 1.0 - s / steps
        step = (F / m[:, None]) * (0.05 * cool)       # heavy = small step
        step = np.clip(step, -0.1, 0.1)
        X += step
    return X


def neighbors_in_layout(word, words, X, k=6):
    i = words.index(word)
    d = np.linalg.norm(X - X[i], axis=1)
    return [words[j] for j in np.argsort(d) if j != i][:k]


if __name__ == "__main__":
    r = GeometricRefinery()
    toks = r.clean_and_tokenize(open(CORPUS_FILE, encoding="utf-8").read())
    counts = {}
    for t in toks:
        counts[t] = counts.get(t, 0) + 1
    # keep the most informative ~250 words so the O(N^2) sim stays fast
    stop = set("the a an and or of to in into from as is are was be by for with that "
               "this it he we us on at which not but their his her its them then than "
               "there here when what who all can may will one two".split())
    vocab = [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])
             if w not in stop][:250]
    idx = {w: i for i, w in enumerate(vocab)}
    print(f"bodies: {len(vocab)} concepts")

    W = ppmi(build_cooccurrence(toks, idx))
    np.fill_diagonal(W, 0.0)
    mass = W.sum(1) + 1e-6

    X = simulate(W, mass, dims=2)

    print("\n=== the SUNS (highest mass / centrality) ===")
    for i in np.argsort(-mass)[:8]:
        print(f"  {vocab[i]:14} mass={mass[i]/mass.mean():.2f}")

    print("\n=== orbital families (nearest bodies in the layout) ===")
    for sun in ["space", "time", "species", "energy", "truth"]:
        if sun in idx:
            print(f"  {sun:9} ☉ -> " + ", ".join(neighbors_in_layout(sun, vocab, X)))

    # optional picture
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        sizes = 8 + 300 * (mass / mass.max())
        plt.figure(figsize=(11, 11))
        plt.scatter(X[:, 0], X[:, 1], s=sizes, alpha=0.5)
        for i in np.argsort(-mass)[:25]:
            plt.text(X[i, 0], X[i, 1], vocab[i], fontsize=8)
        plt.title("Synthesus concept solar system (mass = centrality)")
        plt.axis("off")
        plt.tight_layout()
        plt.savefig("gravity_solar_system.png", dpi=110)
        print("\n🖼  saved gravity_solar_system.png")
    except Exception as e:
        print(f"\n(no image: {e})")
