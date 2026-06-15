#!/usr/bin/env python3
"""
Amplified Reasoning Router — metacognitive operator governance — Synthesus 5
===========================================================================

Refines the legacy `packages/core/amplification_bridge.py` into the new system.

The legacy bridge was a sound design with two dead wires:
  (1) nothing ever set `action_outcome`, so its success/failure learning never
      fired; and
  (2) it governed game "organs" via a TS config it couldn't import from Python.

Here both are fixed by re-pointing it at the REASONING OPERATORS:
  * Each operator (Direct composition, Smelter/abstraction) becomes an "organ".
  * The VSA layer SUPPLIES the outcome label the bridge was missing: an answer
    is checkable against the world, so success/failure is real, not absent.
  * A per-domain promotion score (EMA of confidence + success, same shape as the
    legacy formula) makes the router try the historically-best operator FIRST,
    and fall through to the others — i.e. it learns to COMBINE forms of
    reasoning instead of running a hand-fixed cascade.

This is the metacognitive layer of the consciousness loop made operational:
the runtime monitors its own reasoning and re-routes it. Not a claim about
consciousness — a claim about self-tuning, which this demonstrably does.

Run:  python3 packages/reasoning/vsa_amplify.py
"""
from __future__ import annotations
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_reason import ReasoningSystem, FACTS  # noqa: E402


# ── the world (shared with the reasoning system) ──
def acceptable(action, patient, answer):
    """Ground-truth check — this IS the outcome label the legacy bridge lacked."""
    exact = [s for s, v, o in FACTS if v == action and o == patient]
    if exact:
        return answer == exact[0]      # direct fact exists -> must match it
    return answer is not None          # no direct fact -> any abstraction helps


# ── reasoning operators, as governed "organs" ──
class DirectOrgan:
    name = "direct"

    def __init__(self, R):
        self.R = R

    def attempt(self, action, patient):
        a = self.R.store.ask({"ACTION": action, "PATIENT": patient}, "AGENT")[0]
        return (a, 1.0) if a else (None, 0.0)   # precise but narrow


class SmelterOrgan:
    name = "smelter"

    def __init__(self, R):
        self.R = R

    def attempt(self, action, patient):
        # abstraction-only: melt the patient UP its taxonomy (skip exact level)
        cur, chain = patient, []
        while cur:
            ps = self.R.tax.parents.get(cur, [])
            cur = ps[0] if ps else None
            if cur:
                chain.append(cur)
        for cat in chain:
            hits = [s for s, v, o in FACTS
                    if v == action and (o == cat or self.R.tax.entails(o, cat))]
            if hits:
                return (hits[0], 0.5)           # broad but approximate
        return (None, 0.0)


# ── refined amplification bridge: per-domain operator scoring ──
class MetaController:
    def __init__(self):
        self.m = {}   # (domain, organ) -> dict(score, conf, n, succ)

    def _key(self, d, o):
        return (d, o)

    def score(self, domain, organ):
        return self.m.get(self._key(domain, organ), {"score": 0.5})["score"]

    def record(self, domain, organ, confidence, success):
        k = self._key(domain, organ)
        e = self.m.setdefault(k, {"score": 0.5, "conf": 0.5, "n": 0, "succ": 0})
        a = 0.25                                   # EMA factor
        e["conf"] = (1 - a) * e["conf"] + a * confidence
        e["n"] += 1
        e["succ"] += int(success)
        succ_rate = e["succ"] / e["n"]
        e["score"] = 0.4 * succ_rate + 0.6 * e["conf"]   # legacy-shaped formula

    def rank(self, domain, organs):
        return sorted(organs, key=lambda o: self.score(domain, o.name), reverse=True)


class AmplifiedRouter:
    TOL = 0.4          # confidence tolerance to accept an answer

    def __init__(self):
        self.R = ReasoningSystem()
        self.meta = MetaController()
        self.organs = [SmelterOrgan(self.R), DirectOrgan(self.R)]  # deliberately suboptimal start

    def answer(self, action, patient, learn=True):
        # INFERENCE: try operators in learned order, stop at first that answers.
        order = self.meta.rank(action, self.organs)
        chosen = (None, None, len(order), acceptable(action, patient, None))
        for i, organ in enumerate(order):
            ans, conf = organ.attempt(action, patient)
            if conf >= self.TOL and ans is not None:
                chosen = (ans, organ.name, i + 1, acceptable(action, patient, ans))
                break
        # LEARNING: shadow-evaluate EVERY operator (off-policy) so competence is
        # learned without the cold-start bias of only-scoring-the-one-that-ran.
        # Abstention is neutral; only actual answers are scored.
        if learn:
            for organ in self.organs:
                ans, conf = organ.attempt(action, patient)
                if conf >= self.TOL and ans is not None:
                    self.meta.record(action, organ.name, conf,
                                     acceptable(action, patient, ans))
        return chosen


def main():
    random.seed(1)
    router = AmplifiedRouter()

    # workload: most queries are direct; some only abstraction can reach
    workload = [
        ("chases", "fox"), ("chases", "cat"), ("feeds", "dog"),
        ("feeds", "cat"), ("bites", "man"), ("sees", "wolf"),
        ("chases", "wolf"),   # no direct fact -> only smelter (wolf->canine)
        ("feeds", "fox"),     # no direct fact -> only smelter (fox->canine -> feeds dog)
    ]

    # evaluate the workload under a given operator ORDER, reporting quality.
    CONF = {"direct": 1.0, "smelter": 0.5}

    def evaluate(order_for):
        hits = conf_sum = precise = answered = 0
        for a, p in workload:
            for organ in order_for(a):
                ans, c = organ.attempt(a, p)
                if c >= router.TOL and ans is not None:
                    answered += 1
                    conf_sum += c
                    precise += int(organ.name == "direct")
                    hits += int(acceptable(a, p, ans))
                    break
        n = len(workload)
        return hits / n, conf_sum / n, precise / answered

    print("metacognitive reasoning router: operators = {direct, smelter} as organs")
    print("start order = [smelter, direct] (deliberately suboptimal)\n")

    # BASELINE: legacy-style fixed order, smelter first
    base = evaluate(lambda a: [SmelterOrgan(router.R), DirectOrgan(router.R)])

    # TRAIN: shadow-learning over the workload (real outcome labels from VSA)
    for _ in range(6):
        for a, p in workload:
            router.answer(a, p, learn=True)

    learned = evaluate(lambda a: router.meta.rank(a, router.organs))

    print("learned per-domain routing (operator the loop now trusts first):")
    for action in ("chases", "feeds", "bites", "sees"):
        ranked = router.meta.rank(action, router.organs)
        scores = ", ".join(f"{o.name}={router.meta.score(action, o.name):.2f}" for o in ranked)
        print(f"  {action:8} -> {ranked[0].name:8} first   ({scores})")

    print("\n                     | coverage | avg answer conf | % via precise op")
    print("---------------------+----------+-----------------+-----------------")
    print(f"  baseline (smelter) |  {base[0]*100:4.0f}%   |      {base[1]:.2f}       |      {base[2]*100:3.0f}%")
    print(f"  learned routing    |  {learned[0]*100:4.0f}%   |      {learned[1]:.2f}       |      {learned[2]*100:3.0f}%")
    print("\nSame coverage; the loop learned to route answers through the precise\n"
          "operator (raising confidence), keeping smelter as the fallback for the\n"
          "queries direct can't reach — learned from real outcomes, the exact wire\n"
          "the legacy amplification_bridge was missing.")


if __name__ == "__main__":
    main()
