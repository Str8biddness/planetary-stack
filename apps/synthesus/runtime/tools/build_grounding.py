#!/usr/bin/env python3
"""
Grounding Builder — Synthesus 5
Authors deliberate 5-axis coordinates so that semantically related concepts
*resonate* (high cosine) and unrelated concepts separate. This is the
grounding_map_ path the engine already prefers over generate_vector_from_hash.

Design rules (so chaining in compose_sentence actually stays on-topic):
  - Axis 3 (phase) is the cluster "key": all members of a cluster share it,
    and clusters are spaced > 0.12 apart so the key-filter keeps chains in-cluster.
  - Axes 0,1,2,4 carry a distinct direction per cluster (low cross-cosine).
  - Members = cluster base + tiny jitter -> within-cluster cosine ~1 (unison),
    so the consonant-interval chainer walks the cluster instead of leaving it.
"""
import json, math, sys, os
from pathlib import Path

SHARD_DIR = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")

# concept clusters (the "meaning" we are grounding)
CLUSTERS = {
    "water":        ["water", "ocean", "river", "lake", "rain", "sea", "wave", "stream", "flow"],
    "intelligence": ["intelligence", "mind", "thought", "reason", "logic", "learning", "knowledge", "cognition"],
    "energy":       ["energy", "power", "force", "heat", "electricity", "motion", "current", "charge"],
    "space":        ["space", "gravity", "mass", "orbit", "planet", "star", "cosmos", "universe"],
    "truth":        ["truth", "fact", "reality", "honesty", "proof", "evidence", "certainty"],
    "peace":        ["peace", "calm", "harmony", "quiet", "serenity", "stillness"],
    "nature":       ["nature", "tree", "forest", "earth", "plant", "mountain", "soil"],
}

# Meaning lives in DIRECTION over axes (x, y, z); scale is reserved for
# selection priority (uniformly high so grounded concepts win the scale-sort
# in compose_sentence instead of losing to accidental hash matches).
DIRS = [
    (1.0, 0.1, 0.1),   # water
    (0.1, 1.0, 0.1),   # intelligence
    (0.1, 0.1, 1.0),   # energy
    (1.0, 1.0, 0.1),   # space
    (0.1, 1.0, 1.0),   # truth
    (1.0, 0.1, 1.0),   # peace
    (1.0, 0.6, 0.6),   # nature
]
GROUNDED_SCALE = 0.85  # high + uniform: grounded words rank first by scale axis

def jitter(seed):  # deterministic tiny offset per word, range ~[-0.012, 0.012]
    h = 0
    for c in seed:
        h = (h * 131 + ord(c)) & 0xFFFFFFFF
    return ((h % 1000) / 1000.0 - 0.5) * 0.024

def cosine(a, b):
    d = sum(x*y for x, y in zip(a, b))
    m = math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(x*x for x in b))
    return d / m if m else 0.0

def build():
    names = list(CLUSTERS)
    n = len(names)
    bases, vectors = {}, {}
    for i, name in enumerate(names):
        phase = 0.06 + i * (0.88 / (n - 1))          # spaced ~0.146 apart
        dx, dy, dz = DIRS[i]
        base = [dx, dy, dz, phase, GROUNDED_SCALE]
        bases[name] = base
        for w in CLUSTERS[name]:
            j = jitter(w)
            vectors[w] = [
                round(dx + j, 5), round(dy + j, 5), round(dz + j, 5),
                round(phase, 5), round(GROUNDED_SCALE + j, 5),
            ]
    return names, bases, vectors

def report(names, bases, vectors):
    print("=== cluster base resonance matrix (cross-cluster should be LOW) ===")
    print("            " + "".join(f"{m[:6]:>8}" for m in names))
    for a in names:
        row = "".join(f"{cosine(bases[a], bases[b]):8.2f}" for b in names)
        print(f"{a[:10]:<12}{row}")
    # within-cluster sanity: member vs its base
    print("\n=== within-cluster member resonance (should be ~1.00) ===")
    for name in names:
        ws = CLUSTERS[name]
        lo = min(cosine(vectors[w], bases[name]) for w in ws)
        print(f"  {name:<12} min(member, base) = {lo:.3f}  ({len(ws)} words)")

if __name__ == "__main__":
    names, bases, vectors = build()
    report(names, bases, vectors)
    SHARD_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "metadata": {"source": "build_grounding.py", "dimensions": 5,
                     "note": "deliberate semantic grounding; overrides hash"},
        "vectors": vectors,
    }
    path = SHARD_DIR / "grounding.kn"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Grounding map saved: {path}  ({len(vectors)} grounded concepts)")
