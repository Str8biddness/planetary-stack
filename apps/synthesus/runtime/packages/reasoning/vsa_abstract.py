#!/usr/bin/env python3
"""
Abstractive Controller — the Smelter / Machinist loop — Synthesus 5
===================================================================

Implements the Verb-Domain "Abstractive Conversion" reasoning controller on top
of the VSA operators. Instead of declining flatly when a literal query has no
answer, it MELTS the query down a level of abstraction and re-machines it.

  Rule 1 (Direct Machining): query within tolerance (a fact exists) -> answer it
                             directly via composition.
  Rule 2 (First Conversion): no direct fact -> melt one argument UP its taxonomy
                             (entailment) and re-machine: "no record of the
                             specific, but at the <category> level ...".
  Rule 3 (Deep Conversion):  still stalled -> melt further up and re-machine.
  Rule 4 (Scrap):            nothing at any abstraction -> honest generic fallback.

This is exactly the cliff->ramp fix: the dialogue stack's "generic fallback" is
replaced by abstraction-escalating reasoning that chains composition (Rule 1)
with entailment (Rules 2-3).

Run:  python3 packages/reasoning/vsa_abstract.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_reason import ReasoningSystem, FACTS  # noqa: E402

VERB = {"bit": "bites", "bites": "bites", "chase": "chases", "chases": "chases",
        "feed": "feeds", "feeds": "feeds", "see": "sees", "sees": "sees"}


def lemma(v):
    return VERB.get(v, v)


class AbstractiveController:
    def __init__(self):
        self.R = ReasoningSystem()
        self.tax = self.R.tax

    def _chain(self, x):
        """Ordered abstraction chain: [x, parent, grandparent, ... root]."""
        chain, cur, seen = [], x, set()
        while cur and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            parents = self.tax.parents.get(cur, [])
            cur = parents[0] if parents else None
        return chain

    def who_does(self, action, patient):
        action = lemma(action)
        trace = []
        chain = self._chain(patient)  # melt path for the patient argument

        for level, category in enumerate(chain):
            if level == 0:
                # Rule 1: direct machining via the composition operator
                agent = self.R.store.ask(
                    {"ACTION": action, "PATIENT": category}, "AGENT")[0]
                trace.append(f"    [Rule 1 · direct]   {action} the {category}? "
                             f"-> {agent or 'no fit (out of tolerance)'}")
                if agent:
                    return agent, f"{agent} {action} the {patient}", trace
            else:
                # Rule 2/3: re-machine against the abstracted category
                rule = "Rule 2 · first conversion" if level == 1 else "Rule 3 · deep conversion"
                hits = [(s, o) for (s, v, o) in FACTS
                        if lemma(v) == action and (o == category or self.tax.entails(o, category))]
                trace.append(f"    [{rule}]  melt {patient}->{category}; "
                             f"{action} a {category}? -> "
                             f"{hits[0][0] + ' ' + action + ' ' + hits[0][1] if hits else 'still stalled'}")
                if hits:
                    s, o = hits[0]
                    ans = (f"no direct record of '{action} the {patient}'; "
                           f"at the {category} level: {s} {action} {o} (a {category})")
                    return s, ans, trace

        trace.append("    [Rule 4 · scrap]    no fit at any abstraction -> generic fallback")
        return None, f"I have no record bearing on '{action} the {patient}'.", trace


def main():
    ctrl = AbstractiveController()
    print("facts:", "; ".join(f"{s} {v} {o}" for s, v, o in FACTS))
    print("taxonomy: dog/wolf/fox->canine, cat->feline, man/woman/child->human, "
          "*->mammal->animal->entity\n")

    queries = [
        ("chases", "fox"),    # Rule 1: direct hit
        ("chases", "wolf"),   # Rule 2: no fact about chasing the wolf -> canine level
        ("chases", "man"),    # Rule 3: nothing at human level -> mammal level
        ("flies", "airplane"),  # Rule 4: out of world entirely
    ]
    for action, patient in queries:
        agent, answer, trace = ctrl.who_does(action, patient)
        print(f"Q: who {action} the {patient}?")
        for t in trace:
            print(t)
        print(f"  => {answer}\n")


if __name__ == "__main__":
    main()
