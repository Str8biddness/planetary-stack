#!/usr/bin/env python3
"""
Realizer — template surface realization (the buildable core of GRE's ReverseRealizer).

Turns a structured reasoning result (a head concept + its related concepts +
whether the belief resolved) into a grammatical English sentence. No LLM: just
grammar templates + Oxford-comma list construction. This is the non-neural fix
for the system's weakest link — output was topical word-lists, not sentences.

When the belief is uncertain (high PPBRS entropy) it picks a HEDGED template, so
the surface form carries the calibrated uncertainty rather than hiding it.
"""
from __future__ import annotations
from collections import deque
from typing import List


class Realizer:
    CONFIDENT = [
        "{head} is closely tied to {list}.",
        "{head} connects most strongly to {list}.",
        "In these terms, {head} relates to {list}.",
        "{head} sits among ideas like {list}.",
    ]
    HEDGED = [
        "I'm not certain, but {head} may relate to {list}.",
        "This one is unclear — {head} seems loosely connected to {list}.",
        "Tentatively, {head} might involve {list}.",
    ]

    def __init__(self):
        self._recent = deque(maxlen=4)   # avoid repeating templates back-to-back

    @staticmethod
    def _oxford(words: List[str]) -> str:
        words = [w for w in words if w]
        if not words:
            return "related ideas"
        if len(words) == 1:
            return words[0]
        if len(words) == 2:
            return f"{words[0]} and {words[1]}"
        return ", ".join(words[:-1]) + f", and {words[-1]}"

    def realize(self, head: str, related: List[str], resolved: bool) -> str:
        bank = self.CONFIDENT if resolved else self.HEDGED
        tmpl = next((t for t in bank if t not in self._recent), bank[0])
        self._recent.append(tmpl)
        s = tmpl.format(head=head, list=self._oxford(related))
        return s[0].upper() + s[1:]


if __name__ == "__main__":
    r = Realizer()
    print(r.realize("energy", ["mass", "motion", "transmission"], resolved=True))
    print(r.realize("light", ["velocity", "ray", "propagation"], resolved=True))
    print(r.realize("species", ["geometry", "music"], resolved=False))
