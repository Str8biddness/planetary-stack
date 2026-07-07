#!/usr/bin/env python3
"""
Relational query over a VSA fact store — Synthesus 5
=====================================================

Builds on vsa_twolayer.py. Stores several who-did-what-to-whom facts as bound
holographic vectors, then ANSWERS RELATIONAL QUESTIONS by unbinding:

    "who bit the man?"        -> constrain ACTION=bites, PATIENT=man -> AGENT?
    "what did the wolf chase?" -> constrain AGENT=wolf, ACTION=chases -> PATIENT?

A Q&A template bot matches keywords against canned answers. This does not
match anything — it RECONSTRUCTS the missing role from the geometry of the
stored relation. That is the capability gap we set out to demonstrate.

Run:  python3 packages/reasoning/vsa_query.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_twolayer import TwoLayerVSA, unbind, nearest  # noqa: E402

ROLES = ("AGENT", "ACTION", "PATIENT")


class FactStore:
    """A list of bound SVO facts over a shared TwoLayerVSA space."""

    def __init__(self, vsa: TwoLayerVSA):
        self.vsa = vsa
        self.facts = []          # list[(vector, (s,v,o))]

    def add(self, subj, verb, obj):
        self.facts.append((self.vsa.encode(subj, verb, obj), (subj, verb, obj)))

    def _recovered_roles(self, fact_vec):
        """Unbind every role from one fact -> the exact word it holds."""
        out = {}
        for r in ROLES:
            word, conf = nearest(unbind(fact_vec, self.vsa.roles[r]),
                                 self.vsa.ID, self.vsa.vocab, 1)[0]
            out[r] = (word, conf)
        return out

    def ask(self, known: dict, unknown: str):
        """
        known:   {role: word} constraints, e.g. {"ACTION":"bites","PATIENT":"man"}
        unknown: role to solve for, e.g. "AGENT"
        Returns (answer_word, confidence) or (None, 0.0) if no fact matches.
        """
        best, best_conf = None, 0.0
        for vec, _src in self.facts:
            rec = self._recovered_roles(vec)
            if all(rec[r][0] == w for r, w in known.items()):
                word, conf = rec[unknown]
                if conf > best_conf:
                    best, best_conf = word, conf
        return best, best_conf


def main():
    vsa = TwoLayerVSA()
    store = FactStore(vsa)

    facts = [
        ("dog", "bites", "man"),
        ("wolf", "chases", "fox"),
        ("man", "feeds", "dog"),
        ("fox", "chases", "cat"),
        ("woman", "sees", "wolf"),
        ("child", "feeds", "cat"),
    ]
    for s, v, o in facts:
        store.add(s, v, o)
    print(f"stored {len(facts)} facts as bound holographic vectors "
          f"(identity dims {vsa.ID.shape[1]})\n")
    for s, v, o in facts:
        print(f"    {s} {v} {o}")

    # natural-language-ish question -> (constraints, unknown, expected)
    queries = [
        ("who bit the man?",            {"ACTION": "bites", "PATIENT": "man"},  "AGENT",   "dog"),
        ("what did the wolf chase?",    {"AGENT": "wolf",   "ACTION": "chases"}, "PATIENT", "fox"),
        ("who feeds the dog?",          {"ACTION": "feeds", "PATIENT": "dog"},  "AGENT",   "man"),
        ("what did the fox chase?",     {"AGENT": "fox",    "ACTION": "chases"}, "PATIENT", "cat"),
        ("what does the woman do to the wolf?",
                                        {"AGENT": "woman",  "PATIENT": "wolf"}, "ACTION",  "sees"),
        ("who bit the cat?",            {"ACTION": "bites", "PATIENT": "cat"},  "AGENT",   None),  # no such fact
    ]

    print("\n=== relational queries (reconstructed, not matched) ===")
    hits = checkable = 0
    for q, known, unknown, expected in queries:
        ans, conf = store.ask(known, unknown)
        if expected is None:
            verdict = "OK (correctly: no matching fact)" if ans is None else f"XX (spurious: {ans})"
        else:
            checkable += 1
            ok = ans == expected
            hits += ok
            verdict = f"{'OK' if ok else 'XX'}  -> {ans} ({conf:.2f})"
        print(f"  Q: {q:38} {verdict}")
    print(f"\n  {hits}/{checkable} answerable queries correct; "
          f"unanswerable query correctly declined")


if __name__ == "__main__":
    main()
