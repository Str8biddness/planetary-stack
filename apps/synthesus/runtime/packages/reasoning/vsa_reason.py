#!/usr/bin/env python3
"""
Operator chaining — a reasoning SYSTEM, not isolated operators — Synthesus 5
============================================================================

The previous demos each proved one operator. This one CHAINS them: the output
of one becomes the input to the next, over a single shared world. That is the
step where a pile of capabilities becomes reasoning.

The world has two coupled views over the SAME entities:
  * a FACT STORE (events)      -> composition / relational query  (vsa_query)
  * a TAXONOMY  (is-a graph)   -> entailment / deduction          (vsa_entail)

Compound questions then require more than one operator:

  "Who bit the man, and is it an animal?"
        composition: AGENT where ACTION=bites, PATIENT=man  -> dog
        entailment : dog is-a animal?  dog->canine->mammal->animal -> YES

  "Who feeds the one that bit the man?"        (relational hop o relational hop)
  "Which canine chases the fox?"               (query filtered by a type check)
  "Which feline bit the man?"                  (chain that correctly DECLINES)

Every chain prints a trace, so the reasoning is inspectable end to end.

Run:  python3 packages/reasoning/vsa_reason.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_twolayer import TwoLayerVSA          # noqa: E402
from vsa_query import FactStore               # noqa: E402
from vsa_entail import EntailmentSpace        # noqa: E402

# Taxonomy over the SAME entities that appear in the fact corpus, so the two
# operators share a vocabulary and can hand results to each other.
TAXONOMY = [
    ("dog", "canine"), ("wolf", "canine"), ("fox", "canine"),
    ("cat", "feline"),
    ("man", "human"), ("woman", "human"), ("child", "human"),
    ("canine", "mammal"), ("feline", "mammal"), ("human", "mammal"),
    ("mammal", "animal"), ("animal", "entity"),
]

FACTS = [
    ("dog", "bites", "man"),
    ("wolf", "chases", "fox"),
    ("man", "feeds", "dog"),
    ("fox", "chases", "cat"),
    ("woman", "sees", "wolf"),
    ("child", "feeds", "cat"),
]


class ReasoningSystem:
    def __init__(self):
        self.vsa = TwoLayerVSA()              # animal corpus -> 100% role recovery
        self.store = FactStore(self.vsa)
        for s, v, o in FACTS:
            self.store.add(s, v, o)
        self.tax = EntailmentSpace(edges=TAXONOMY)
        self.trace = []

    def _log(self, op, msg):
        self.trace.append(f"    [{op}] {msg}")

    def _run(self, title, fn):
        self.trace = []
        print(f"\nQ: {title}")
        answer = fn()
        for line in self.trace:
            print(line)
        print(f"  => {answer}")

    # --- single operators (the primitives being chained) ---
    def who(self, action, patient):
        a, _ = self.store.ask({"ACTION": action, "PATIENT": patient}, "AGENT")
        self._log("composition", f"AGENT where ACTION={action}, PATIENT={patient} -> {a}")
        return a

    def patient_of(self, agent, action):
        o, _ = self.store.ask({"AGENT": agent, "ACTION": action}, "PATIENT")
        self._log("composition", f"PATIENT where AGENT={agent}, ACTION={action} -> {o}")
        return o

    def is_a(self, x, y):
        ok = x in self.tax.idx and y in self.tax.idx and self.tax.entails(x, y)
        path = self.tax.path(x, y) if ok else None
        via = " -> ".join(path) if path else "no path"
        self._log("entailment", f"{x} is-a {y}? {ok}  ({via})")
        return ok

    def kinds_of(self, x):
        hs = self.tax.hypernyms(x) if x in self.tax.idx else []
        self._log("entailment", f"hypernyms({x}) -> {hs}")
        return hs

    # --- chained reasoning ---
    def who_and_type_check(self, action, patient, kind):
        agent = self.who(action, patient)
        if agent is None:
            return f"no one {action} the {patient}"
        return f"{agent} (an {kind})" if self.is_a(agent, kind) \
            else f"{agent}, but it is not a {kind}"

    def who_feeds_the_one_that(self, inner_action, inner_patient):
        mid = self.who(inner_action, inner_patient)
        if mid is None:
            return f"nothing {inner_action} the {inner_patient}"
        feeder = self.who("feeds", mid)
        return feeder if feeder else f"no one feeds the {mid}"

    def what_kind_did(self, action, patient):
        agent = self.who(action, patient)
        if agent is None:
            return f"nothing {action} the {patient}"
        return self.kinds_of(agent)

    def which_KIND_does(self, kind, action, patient):
        """Query then filter results by a type (entailment) check."""
        agent = self.who(action, patient)
        if agent is None:
            return f"no one {action} the {patient}"
        return agent if self.is_a(agent, kind) \
            else f"the one that {action} the {patient} ({agent}) is not a {kind}"


def main():
    R = ReasoningSystem()
    print("world: 6 events  +  taxonomy of 14 concepts (shared entities)")
    print("facts:", "; ".join(f"{s} {v} {o}" for s, v, o in FACTS))

    R._run("Who bit the man, and is it an animal?",
           lambda: R.who_and_type_check("bites", "man", "animal"))

    R._run("What kind of thing bit the man?",
           lambda: R.what_kind_did("bites", "man"))

    R._run("Who feeds the one that bit the man?",
           lambda: R.who_feeds_the_one_that("bites", "man"))

    R._run("Which canine chases the fox?",
           lambda: R.which_KIND_does("canine", "chases", "fox"))

    R._run("Which feline bit the man?  (should decline)",
           lambda: R.which_KIND_does("feline", "bites", "man"))


if __name__ == "__main__":
    main()
