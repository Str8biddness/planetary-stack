#!/usr/bin/env python3
"""
Shallow NL front end — Synthesus 5
===================================

Turns plain-English questions into OPERATOR CHAINS over the reasoning world
(vsa_reason.py). No neural parser — pattern rules + a tiny verb lemmatizer map
a question to the right composition/entailment/negation call, so the whole
system can be *talked to*:

    "who bit the man?"                     -> composition
    "what did the wolf chase?"             -> composition (patient)
    "is a dog an animal?"                  -> entailment
    "what kind of thing is a whale?"       -> entailment (hypernyms)
    "which canine chases the fox?"         -> composition + entailment
    "who feeds the one that bit the man?"  -> composition o composition
    "who did not bite the man?"            -> logical negation

Run:  python3 packages/reasoning/vsa_nl.py
"""
from __future__ import annotations
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vsa_reason import ReasoningSystem, FACTS  # noqa: E402

# surface verb form -> stored present-tense form
VERB = {
    "bit": "bites", "bite": "bites", "bites": "bites",
    "chase": "chases", "chased": "chases", "chases": "chases",
    "feed": "feeds", "fed": "feeds", "feeds": "feeds",
    "see": "sees", "saw": "sees", "sees": "sees", "seen": "sees",
}


def lemma(v):
    return VERB.get(v, v)


class NLReasoner:
    def __init__(self):
        self.R = ReasoningSystem()
        a = re.compile  # local alias
        # (regex, handler) — order matters; specific patterns first
        self.rules = [
            (a(r"who did not (\w+) the (\w+)"),               self._not_who),
            (a(r"who (\w+) the one that (\w+) the (\w+)"),     self._multi_hop),
            (a(r"which (\w+) (\w+) the (\w+)"),                self._which_kind),
            (a(r"what kind of thing is (?:a |an )?(\w+)"),     self._kinds),
            (a(r"what is (?:a |an )?(\w+)"),                   self._kinds),
            (a(r"is (?:a |an )?(\w+) (?:a |an )?(\w+)"),       self._is_a),
            (a(r"what did the (\w+) (\w+)"),                   self._patient),
            (a(r"who (\w+) the (\w+)"),                        self._who),
        ]

    # --- handlers (return a string answer; R.trace holds the steps) ---
    def _who(self, m):
        return self.R.who(lemma(m.group(1)), m.group(2)) or "no answer"

    def _patient(self, m):
        return self.R.patient_of(m.group(1), lemma(m.group(2))) or "no answer"

    def _is_a(self, m):
        return "yes" if self.R.is_a(m.group(1), m.group(2)) else "no"

    def _kinds(self, m):
        return ", ".join(self.R.kinds_of(m.group(1))) or "unknown"

    def _which_kind(self, m):
        return self.R.which_KIND_does(m.group(1), lemma(m.group(2)), m.group(3))

    def _multi_hop(self, m):
        outer, inner_v, inner_o = lemma(m.group(1)), lemma(m.group(2)), m.group(3)
        mid = self.R.who(inner_v, inner_o)
        if mid is None:
            return f"nothing {inner_v} the {inner_o}"
        return self.R.who(outer, mid) or f"no one {outer} the {mid}"

    def _not_who(self, m):
        verb, patient = lemma(m.group(1)), m.group(2)
        did = {s for s, v, o in FACTS if (v, o) == (verb, patient)}
        actors = {s for s, _, _ in FACTS}
        self.R.trace = [f"    [negation] actors - {{x: x {verb} {patient}}} "
                        f"= {sorted(actors)} - {sorted(did)}"]
        return ", ".join(sorted(actors - did)) or "everyone did"

    def ask(self, question):
        q = question.lower().strip().rstrip("?").strip()
        for rx, fn in self.rules:
            mm = rx.search(q)
            if mm:
                self.R.trace = []
                ans = fn(mm)
                return ans, list(self.R.trace)
        return "(could not parse)", []


def main():
    nl = NLReasoner()
    print("facts:", "; ".join(f"{s} {v} {o}" for s, v, o in FACTS), "\n")

    questions = [
        "Who bit the man?",
        "What did the wolf chase?",
        "Is a dog an animal?",
        "Is a dog a feline?",
        "What kind of thing is a wolf?",
        "What kind of thing is a whale?",   # out-of-world -> honestly 'unknown'
        "Which canine chases the fox?",
        "Who feeds the one that bit the man?",
        "Who did not bite the man?",
    ]
    for q in questions:
        ans, trace = nl.ask(q)
        print(f"Q: {q}")
        for t in trace:
            print(t)
        print(f"  => {ans}\n")


if __name__ == "__main__":
    main()
