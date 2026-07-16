#!/usr/bin/env python3
"""
Amplified Memory Router — governance over memory sources — Synthesus 5
=====================================================================

Direct reuse of the metacognitive loop from vsa_amplify.py, now pointed at the
MEMORY layer instead of the reasoning operators. The legacy stack has a fixed
4-module fallback cascade (Knowledge Graph -> Knowledge Cloud -> Personality
Bank -> Context Recall). A fixed order has a failure mode: a greedy source that
answers *almost* anything (semantic/Cloud) intercepts queries it gets WRONG
before the right source is ever consulted.

The same MetaController learns, per query-type, which source to TRUST first —
turning the fixed cascade into a learned router. Outcome labels are real
(retrieved answer checked against ground truth), exactly as in vsa_amplify.

Run:  python3 packages/reasoning/vsa_memory.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_amplify import MetaController  # noqa: E402  (reuse the loop verbatim)


# ── the workload: each query has a type (= domain) and a ground-truth answer ──
QUERIES = [
    {"q": "capital of france",  "type": "factual",    "truth": "paris"},
    {"q": "what is a dog",      "type": "factual",    "truth": "mammal"},
    {"q": "tell me about rivers","type": "topical",   "truth": "rivers_flow_to_sea"},
    {"q": "about gravity",      "type": "topical",    "truth": "gravity_pulls_mass"},
    {"q": "what is your name",  "type": "personal",   "truth": "aria"},
    {"q": "what do you like",   "type": "personal",   "truth": "tea"},
    {"q": "what did i just ask","type": "contextual", "truth": "capital_of_france"},
    {"q": "repeat that",        "type": "contextual", "truth": "paris"},
]


def acceptable(query, answer):
    return answer == query["truth"]   # the real outcome label


# ── memory sources, each with a different competence profile ──
class KnowledgeGraph:
    name = "kgraph"
    def attempt(self, q):
        return (q["truth"], 0.95) if q["type"] == "factual" else (None, 0.0)

class KnowledgeCloud:
    """Semantic/FAISS: answers almost anything — precise on topical, but returns
    a confident-ish WRONG match on everything else (the cascade's hazard)."""
    name = "cloud"
    def attempt(self, q):
        if q["type"] == "topical":
            return (q["truth"], 0.80)
        return (q["q"].split()[0] + "_ish", 0.55)   # plausible but wrong

class PersonalityBank:
    name = "persona"
    def attempt(self, q):
        return (q["truth"], 0.90) if q["type"] == "personal" else (None, 0.0)

class ContextRecall:
    name = "context"
    def attempt(self, q):
        return (q["truth"], 0.90) if q["type"] == "contextual" else (None, 0.0)


class MemoryRouter:
    TOL = 0.5

    def __init__(self):
        self.meta = MetaController()
        self.sources = [KnowledgeGraph(), KnowledgeCloud(),
                        PersonalityBank(), ContextRecall()]

    def evaluate(self, order_for):
        cov = correct = conf_sum = right_src = 0
        for q in QUERIES:
            for src in order_for(q["type"]):
                ans, c = src.attempt(q)
                if c >= self.TOL and ans is not None:
                    cov += 1
                    conf_sum += c
                    ok = acceptable(q, ans)
                    correct += int(ok)
                    right_src += int(ok)
                    break
        n = len(QUERIES)
        return cov / n, correct / n, conf_sum / n

    def train(self, epochs=6):
        for _ in range(epochs):
            for q in QUERIES:
                # shadow-evaluate every source (off-policy), score real outcomes
                for src in self.sources:
                    ans, c = src.attempt(q)
                    if c >= self.TOL and ans is not None:
                        self.meta.record(q["type"], src.name, c, acceptable(q, ans))


def main():
    r = MemoryRouter()
    fixed = [KnowledgeGraph(), KnowledgeCloud(), PersonalityBank(), ContextRecall()]

    base = r.evaluate(lambda t: fixed)              # legacy fixed cascade
    r.train()
    learned = r.evaluate(lambda t: r.meta.rank(t, r.sources))

    print("memory governance: 4 sources = {kgraph, cloud, persona, context}")
    print("legacy = fixed cascade [kgraph -> cloud -> persona -> context]\n")
    print("learned per-type routing (source the loop now trusts first):")
    for t in ("factual", "topical", "personal", "contextual"):
        ranked = r.meta.rank(t, r.sources)
        scores = ", ".join(f"{s.name}={r.meta.score(t, s.name):.2f}" for s in ranked)
        print(f"  {t:11} -> {ranked[0].name:8} first   ({scores})")

    print("\n                     | coverage | accuracy | avg conf")
    print("---------------------+----------+----------+---------")
    print(f"  fixed cascade      |  {base[0]*100:4.0f}%   |  {base[1]*100:4.0f}%   |   {base[2]:.2f}")
    print(f"  learned routing    |  {learned[0]*100:4.0f}%   |  {learned[1]*100:4.0f}%   |   {learned[2]:.2f}")
    print("\nThe fixed cascade lets the greedy semantic source intercept personal &\n"
          "contextual queries with confident-wrong matches. The loop learns to send\n"
          "each query-type to the source that is actually right -- same coverage,\n"
          "accuracy recovered, learned from real retrieval outcomes.")


if __name__ == "__main__":
    main()
