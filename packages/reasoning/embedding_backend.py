#!/usr/bin/env python3
"""
Embedding backend — MiniLM organ that coexists with the grounded substrate
==========================================================================

Everything we built reasons over embedding vectors. This makes the *source* of
those vectors a pluggable organ, so all-MiniLM-L6-v2 drops in WITHOUT replacing
anything — it just becomes the production-grade meaning provider that the
existing components (Hopfield, similarity, KAL/FAISS retrieval, the fusion
coherence term, the groundedness tagger) consume.

  EmbeddingBackend.encode(text) -> vector
    - MiniLMBackend   : learned 384-d embeddings, pretrained on billions of
                        sentences (cat ~ feline out of the box), handles ANY text.
    - GroundedBackend : the sovereign PPMI+SVD grounding (no deps, vocab-limited).
  get_embedder()      : MiniLM if installed, else graceful fallback to grounded.

Install (one command, then MiniLM activates automatically everywhere):
    pip install sentence-transformers        # fastest path (pulls torch)
    # production-light alternative: export to ONNX + onnxruntime (matches the
    # existing ONNX ML organs, no torch).

What MiniLM does / doesn't: it upgrades the KNOWER (perception / meaning /
retrieval) to production quality. It is an ENCODER, not a generator — generation
is unchanged (retrieval/template via organs+patterns works; open-ended needs a
generator). It runs in parallel with everything; it's the embedding provider,
not a competitor to the operators.

Run:  ./venv/bin/python packages/reasoning/embedding_backend.py
"""
from __future__ import annotations
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class EmbeddingBackend:
    name = "base"
    dim = 0
    def encode(self, text: str) -> np.ndarray:
        raise NotImplementedError
    def encode_batch(self, texts) -> np.ndarray:
        return np.vstack([self.encode(t) for t in texts])


class MiniLMBackend(EmbeddingBackend):
    """all-MiniLM-L6-v2 as an organ. Learned, 384-d, handles arbitrary text."""
    name = "minilm"
    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # raises if absent
        self._m = SentenceTransformer(model)
        self.dim = self._m.get_sentence_embedding_dimension()
        self._cache: dict[str, np.ndarray] = {}
    def encode(self, text: str) -> np.ndarray:
        if text not in self._cache:
            self._cache[text] = np.asarray(self._m.encode(text), dtype=np.float32)
        return self._cache[text]
    def encode_batch(self, texts) -> np.ndarray:
        return np.asarray(self._m.encode(list(texts)), dtype=np.float32)


class GroundedBackend(EmbeddingBackend):
    """The existing sovereign PPMI+SVD grounding. No deps; limited to its vocab."""
    name = "grounded"
    def __init__(self, vsa=None):
        from vsa_twolayer import TwoLayerVSA
        self.vsa = vsa or TwoLayerVSA()
        self.dim = self.vsa.SEM.shape[1]
    def encode(self, text: str) -> np.ndarray:
        ws = [w for w in text.lower().split() if w in self.vsa.vidx]
        if not ws:
            return np.zeros(self.dim, dtype=np.float32)
        return self.vsa.SEM[[self.vsa.vidx[w] for w in ws]].mean(0).astype(np.float32)


def get_embedder(prefer: str = "minilm", **kw) -> EmbeddingBackend:
    """MiniLM if available; otherwise the grounded fallback (graceful, parallel)."""
    if prefer == "minilm":
        try:
            return MiniLMBackend(**kw)
        except Exception as e:
            print(f"[embedding] MiniLM unavailable ({type(e).__name__}); "
                  f"falling back to grounded.  -> pip install sentence-transformers")
    return GroundedBackend()


def _cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na and nb else 0.0


def main():
    emb = get_embedder()
    print(f"active embedding organ: {emb.name}  (dim {emb.dim})\n")
    words = ["cat", "dog", "wolf", "man"]
    base = emb.encode("cat")
    print("cosine of 'cat' to:")
    for w in words[1:]:
        print(f"   {w:6} {_cos(base, emb.encode(w)):+.3f}")
    if emb.name == "minilm":
        print(f"   feline {_cos(base, emb.encode('feline')):+.3f}   (arbitrary text — learned)")
    else:
        print("\n(grounded fallback is vocab-limited; install MiniLM to embed any text,")
        print(" e.g. 'feline', at production quality.)")
    print("\nWires into everything in ~2 lines, e.g.:")
    print("  emb = get_embedder()")
    print("  hop = ModernHopfield(emb.encode_batch(concepts), concepts)   # MiniLM attractors")
    print("  # same for KAL/FAISS retrieval, fusion coherence, groundedness tagger")


if __name__ == "__main__":
    main()
