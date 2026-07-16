#!/usr/bin/env python3
"""
Spectral Ripple — Synthesus 5 (ideas 2+3)
The concept-graph Laplacian, one operator that yields BOTH:
  - eigenvectors of L      = vibrational modes = semantic axes (similarity)
  - heat kernel exp(-tL)   = ripples = diffusion (association / reasoning)

Pure linear algebra over word co-occurrence statistics. No hash, no neural
network, no transformer.

CLI examples:
  python tools/spectral_ripple.py --modes 5
  python tools/spectral_ripple.py --ripple water --t 0.3 1.5
  python tools/spectral_ripple.py --interfere water energy
  python tools/spectral_ripple.py --corpus data/big.txt --ripple gravity
"""
import sys, os, argparse
import numpy as np
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricRefinery
from cooccurrence_grounding import CORPUS, build_cooccurrence, ppmi

STOP = set("the a an and or of to in into from across through its is are as while "
           "it we us on at by for with that this his her their our your".split())


class ConceptField:
    """A vibrating field of concepts built from co-occurrence statistics."""

    def __init__(self, text, min_count=2, window=4, drop_stop=True):
        r = GeometricRefinery()
        toks = r.clean_and_tokenize(text)
        counts = {}
        for t in toks:
            counts[t] = counts.get(t, 0) + 1
        self.vocab = sorted(w for w, c in counts.items()
                            if c >= min_count and not (drop_stop and w in STOP))
        self.idx = {w: i for i, w in enumerate(self.vocab)}

        W = ppmi(build_cooccurrence(toks, self.idx, window))
        np.fill_diagonal(W, 0.0)
        d = W.sum(1); d[d == 0] = 1e-9
        Dm = np.diag(1.0 / np.sqrt(d))
        self.L = np.eye(len(self.vocab)) - Dm @ W @ Dm          # normalized Laplacian
        self.evals, self.evecs = np.linalg.eigh(self.L)         # vibrational modes
        print(f"🌐 ConceptField: {len(toks)} tokens, vocab {len(self.vocab)}, "
              f"{len(self.evals)} vibrational modes")

    # --- vibrations -------------------------------------------------------
    def modes(self, k=5, top=4):
        out = []
        for m in range(1, k + 1):                                # skip mode 0 (constant)
            v = self.evecs[:, m]
            pos = [self.vocab[i] for i in np.argsort(-v)[:top]]
            neg = [self.vocab[i] for i in np.argsort(v)[:top]]
            out.append((m, pos, neg))
        return out

    # --- ripples ----------------------------------------------------------
    def _heat(self, t):
        return self.evecs @ np.diag(np.exp(-t * self.evals)) @ self.evecs.T

    def ripple(self, word, t=0.5, top=6):
        if word not in self.idx:
            return []
        a = self._heat(t)[:, self.idx[word]].copy()
        a[self.idx[word]] = -np.inf
        return [(self.vocab[j], float(a[j])) for j in np.argsort(-a)[:top]]

    def interfere(self, words, t=1.0, top=6):
        words = [w for w in words if w in self.idx]
        if not words:
            return []
        H = self._heat(t)
        a = sum(H[:, self.idx[w]] for w in words)
        for w in words:
            a[self.idx[w]] = -np.inf
        return [(self.vocab[j], float(a[j])) for j in np.argsort(-a)[:top]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", help="text file (default: built-in domain corpus)")
    ap.add_argument("--min-count", type=int, default=2)
    ap.add_argument("--window", type=int, default=4)
    ap.add_argument("--modes", type=int, default=0)
    ap.add_argument("--ripple", metavar="WORD")
    ap.add_argument("--t", type=float, nargs="+", default=[0.3, 1.5])
    ap.add_argument("--interfere", nargs="+", metavar="WORD")
    args = ap.parse_args()

    text = open(args.corpus, encoding="utf-8").read() if args.corpus else CORPUS
    field = ConceptField(text, min_count=args.min_count, window=args.window)

    if args.modes:
        print("\n=== vibrational modes (semantic axes) ===")
        for m, pos, neg in field.modes(args.modes):
            print(f"  mode {m}: (+) {pos}  vs  (-) {neg}")
    if args.ripple:
        print(f"\n=== ripple from '{args.ripple}' ===")
        for t in args.t:
            sp = ", ".join(f"{w}({v:.3f})" for w, v in field.ripple(args.ripple, t))
            print(f"  t={t}: {sp}")
    if args.interfere:
        print(f"\n=== interference {args.interfere} ===")
        sp = ", ".join(f"{w}({v:.3f})" for w, v in field.interfere(args.interfere))
        print(f"  {sp}")
    if not (args.modes or args.ripple or args.interfere):
        # default demo
        for m, pos, neg in field.modes(3):
            print(f"  mode {m}: (+) {pos}  vs  (-) {neg}")


if __name__ == "__main__":
    main()
