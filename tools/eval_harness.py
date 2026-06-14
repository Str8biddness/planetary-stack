#!/usr/bin/env python3
"""
Evaluation Harness — Synthesus 5
The measuring stick. Objective, falsifiable checks so changes are judged by
numbers, not vibes. Exits non-zero if any gate fails (usable as a commit gate).

Gates:
  A. Motor safety   — benign queries must NOT run shell commands; only explicit
                      command words may. (Guards the whoami mis-fire.)
  B. Semantic AUC   — derived coordinates must rank related word pairs above
                      unrelated ones (intrinsic similarity quality).
  C. Family purity  — a composed concept-family must be far more self-coherent
                      than a random set of words.
  D. Hash parity    — the Python fallback vector must still match the C++ kernel.
"""
import sys, os, json, random
import numpy as np
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricEngineFallback
from action_assembler import ActionAssembler

SHARD_DIR = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")
results = []


def gate(name, passed, detail):
    results.append(passed)
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")


def load_derived():
    d = json.load(open(SHARD_DIR / "grounding_derived.kn", encoding="utf-8"))["vectors"]
    return {w: np.array(v) for w, v in d.items()}


def cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


# ---- A. Motor safety ----------------------------------------------------
def test_motor():
    print("\nA. Motor safety")
    motor = ActionAssembler(GeometricEngineFallback())
    benign = ["tell me about space", "describe light", "what is knowledge",
              "the origin of species", "explain energy and mass"]
    for q in benign:
        gate(f"benign '{q}'", motor.detect_action(q) is None, "no command fired")
    for q in ["list my shards", "who am i"]:
        gate(f"command '{q}'", motor.detect_action(q) is not None, "command fired")


# ---- B. Semantic ranking (AUC) -----------------------------------------
def test_semantic(D):
    print("\nB. Semantic ranking (related > unrelated)")
    related = [("space", "time"), ("mass", "motion"), ("light", "velocity"),
               ("species", "varieties"), ("species", "genus"), ("truth", "belief"),
               ("knowledge", "truth"), ("gravitation", "mass")]
    unrelated = [("space", "species"), ("mass", "truth"), ("light", "genus"),
                 ("velocity", "belief"), ("species", "motion"), ("truth", "light"),
                 ("knowledge", "velocity"), ("genus", "energy")]
    rs = [cos(D[a], D[b]) for a, b in related if a in D and b in D]
    us = [cos(D[a], D[b]) for a, b in unrelated if a in D and b in D]
    wins = sum(r > u for r in rs for u in us)
    auc = wins / (len(rs) * len(us))
    gate("ranking AUC", auc >= 0.80,
         f"AUC={auc:.2f}  (related μ={np.mean(rs):+.2f}, unrelated μ={np.mean(us):+.2f})")


# ---- C. Family purity --------------------------------------------------
def test_family(D):
    print("\nC. Family self-coherence vs random")
    rng = random.Random(0)
    words = list(D)

    def mean_pairwise(group):
        s = [cos(D[a], D[b]) for i, a in enumerate(group) for b in group[i + 1:]]
        return float(np.mean(s)) if s else 0.0

    for concept in ["light", "species", "knowledge", "motion"]:
        if concept not in D:
            continue
        fam = [w for w, _ in sorted(((w, cos(D[concept], v)) for w, v in D.items()),
                                    key=lambda kv: -kv[1])[1:7]]
        rand = rng.sample(words, 6)
        fc, rc = mean_pairwise(fam), mean_pairwise(rand)
        gate(f"family('{concept}')", fc > rc + 0.10,
             f"family={fc:+.2f} >> random={rc:+.2f}  [{' '.join(fam)}]")


# ---- D. Hash parity regression -----------------------------------------
def test_parity():
    print("\nD. Python↔C++ hash parity")
    v = GeometricEngineFallback().word_to_vector("intelligence")
    expect = [0.520394, 0.648234, 0.0449378, 0.828168, 0.799847]
    ok = all(abs(a - b) < 1e-5 for a, b in zip(v[:5], expect))
    gate("intelligence vector", ok, f"{[round(x,4) for x in v[:5]]}")


if __name__ == "__main__":
    print("=" * 60 + "\n  SYNTHESUS 5 — EVALUATION HARNESS\n" + "=" * 60)
    D = load_derived()
    print(f"derived grounding: {len(D)} concepts × {len(next(iter(D.values())))} dims")
    test_motor()
    test_semantic(D)
    test_family(D)
    test_parity()
    n_pass, n = sum(results), len(results)
    print("\n" + "=" * 60)
    print(f"  RESULT: {n_pass}/{n} gates passed")
    print("=" * 60)
    sys.exit(0 if n_pass == n else 1)
