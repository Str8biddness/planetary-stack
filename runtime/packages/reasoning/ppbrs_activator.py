#!/usr/bin/env python3
"""
PPBRS Activator — Pattern Probability Based Reasoning over GROUNDED embeddings.

A real, runnable implementation of the PPBRS core (von Mises-Fisher likelihood,
log-space Bayesian update, entropy/confidence). The spec's own examples seed the
pattern set with np.random.randn embeddings (noise); here the patterns are the
co-occurrence-derived concept vectors from grounding_derived.kn, so the Bayesian
layer reasons over *meaning*, not noise.

    L(c | p) = exp(beta * cos(c, e_p))                       # vMF likelihood
    log posterior = log prior + log L,  normalized by log_sum_exp
    H = -sum p log p                                          # uncertainty

Standalone (numpy + stdlib only) so it imports without the heavy package init.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

# Shard dir convention shared with the rest of the tools (hardcoded path; a
# repo-wide cleanup to make this relative is tracked separately).
DEFAULT_SHARD = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards/grounding_derived.kn")


class PatternField:
    """The pattern set: words + L2-normalized embedding matrix, with encoding."""

    def __init__(self, vectors: Dict[str, list]):
        self.words: List[str] = list(vectors)
        self.index = {w: i for i, w in enumerate(self.words)}
        E = np.array([vectors[w] for w in self.words], dtype=float)
        self.E = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-12)
        self.vec = {w: self.E[i] for i, w in enumerate(self.words)}

    @classmethod
    def from_shard(cls, path: Path = DEFAULT_SHARD) -> "PatternField":
        return cls(json.load(open(path, encoding="utf-8"))["vectors"])

    def encode(self, text: str) -> Optional[np.ndarray]:
        """Context vector = mean of grounded token vectors (None if none ground)."""
        toks = [t.strip(".,;:!?\"'()") for t in text.lower().split()]
        present = [self.vec[t] for t in toks if t in self.index]
        if not present:
            return None
        c = np.mean(present, axis=0)
        n = np.linalg.norm(c)
        return c / n if n > 0 else None

    def __len__(self):
        return len(self.words)


class ProbabilisticPatternActivator:
    """Maintains a Bayesian belief distribution over the pattern field."""

    def __init__(self, field: PatternField, beta: float = 12.0):
        self.field = field
        self.beta = beta
        self.reset()

    def reset(self) -> None:
        n = len(self.field)
        self.logp = np.full(n, -np.log(n))          # uniform prior
        self.steps = 0

    def update(self, context_vec: np.ndarray,
               prior_bias: Optional[np.ndarray] = None) -> np.ndarray:
        """One Bayesian step. Returns posterior probabilities (linear space)."""
        c = context_vec / (np.linalg.norm(context_vec) + 1e-12)
        loglik = self.beta * (self.field.E @ c)     # vMF log-likelihood
        lp = self.logp + loglik
        if prior_bias is not None:
            lp = lp + np.log(prior_bias + 1e-12)
        m = np.max(lp)
        self.logp = lp - (m + np.log(np.sum(np.exp(lp - m))))
        self.steps += 1
        return np.exp(self.logp)

    def observe(self, text: str) -> Optional[np.ndarray]:
        """Convenience: encode text and update. None if text isn't grounded."""
        c = self.field.encode(text)
        return None if c is None else self.update(c)

    def entropy(self) -> float:
        p = np.exp(self.logp)
        return float(-np.sum(p * np.log(p + 1e-12)))

    def confidence_gap(self) -> float:
        p = np.sort(np.exp(self.logp))[::-1]
        return float(p[0] - p[1]) if p.size >= 2 else 0.0

    def top_k(self, k: int = 5) -> List[Tuple[str, float]]:
        idx = np.argsort(-self.logp)[:k]
        return [(self.field.words[i], float(np.exp(self.logp[i]))) for i in idx]

    def normalized_entropy(self) -> float:
        """Entropy / log(N): 0 = certain, 1 = uniform. Scale-invariant."""
        n = len(self.field)
        return self.entropy() / float(np.log(n)) if n > 1 else 0.0

    def is_resolved(self, max_norm_entropy: float = 0.30) -> bool:
        """Resolved = belief is concentrated, measured by *normalized* entropy.

        Using normalized entropy (not a top-1 probability floor) means a coherent
        multi-topic query — belief split across a few RELATED concepts — still
        resolves, while only genuinely diffuse, cross-domain beliefs stay
        unresolved. log(N)-scaled so the threshold holds as the vocabulary grows.
        """
        return self.normalized_entropy() < max_norm_entropy


if __name__ == "__main__":
    field = PatternField.from_shard()
    print(f"PatternField: {len(field)} grounded patterns\n")
    for label, ev in [("coherent (biology)", ["species", "varieties", "descent"]),
                      ("incoherent (mixed)", ["species", "geometry", "fertility"])]:
        act = ProbabilisticPatternActivator(field)
        print(f"{label}: start H={act.entropy():.2f}")
        for w in ev:
            if act.observe(w) is not None:
                print(f"  +{w:9} H={act.entropy():.2f} resolved={act.is_resolved()} "
                      f"top={act.top_k(3)}")
        print()
