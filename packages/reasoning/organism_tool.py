#!/usr/bin/env python3
"""
Tool-Use Organism (ability #3) — Synthesus 5
=============================================

Detects which tool a query needs, extracts its arguments, and actually runs it.
Gated by the framework: Synthesus cannot use tools without this organism.

  ability "use_tool" ──requires──▶ ToolUseOrganism
        organs (dependencies): tool_selector (query → which tool, or none)
                               arg_extractor (query → the tool's arguments)

Measured bar: tool-selection accuracy on held-out queries. Real tools execute
(the calculator genuinely computes).

Run:  ./venv/bin/python packages/reasoning/organism_tool.py
"""
from __future__ import annotations
import os
import re
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from amplification_organism import AmplificationOrganism, Organ, Synthesus, CapabilityUnavailable  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression          # noqa: E402
from sklearn.pipeline import Pipeline                        # noqa: E402

_OPS = {"plus": "+", "add": "+", "added": "+", "minus": "-", "subtract": "-",
        "times": "*", "multiply": "*", "multiplied": "*", "divided": "/", "divide": "/"}


class ToolSelectorOrgan(Organ):
    """query → which tool (or 'none')."""
    TRAIN = {
        "calculator": ["what is 2 plus 2", "calculate 5 times 3", "add 10 and 20",
                       "whats 9 minus 4", "multiply 6 by 7", "what is 100 divided by 5",
                       "compute 8 times 8", "sum of 3 and 4"],
        "time":       ["what time is it", "whats the time", "tell me the time",
                       "current time", "do you know the time", "what is the time now"],
        "none":       ["hello there", "tell me about dragons", "how are you",
                       "whats your name", "thanks for the help", "goodbye"],
    }
    def __init__(self): super().__init__("tool_selector"); self.pipe = None
    def train(self, _=None):
        X = [q for qs in self.TRAIN.values() for q in qs]
        y = [t for t, qs in self.TRAIN.items() for _ in qs]
        self.pipe = Pipeline([("tfidf", TfidfVectorizer(ngram_range=(1, 2))),
                              ("clf", LogisticRegression(max_iter=1000))]).fit(X, y)
        self.trained = True
    def select(self, q): return self.pipe.predict([q.lower()])[0]


class ArgExtractorOrgan(Organ):
    """query → tool arguments (numbers + operator for the calculator)."""
    def __init__(self): super().__init__("arg_extractor")
    def train(self, _=None): self.trained = True
    def calc_args(self, q):
        nums = [float(n) for n in re.findall(r"\d+\.?\d*", q)]
        op = next((_OPS[w] for w in q.lower().split() if w in _OPS), None)
        return nums, op


class ToolUseOrganism(AmplificationOrganism):
    ability = "use_tool"
    bar = 0.8
    def __init__(self):
        super().__init__()
        self.sel = ToolSelectorOrgan(); self.ext = ArgExtractorOrgan()
        self.organs = {"tool_selector": self.sel, "arg_extractor": self.ext}
    def train(self, _=None): self.sel.train(); self.ext.train()
    def run(self, query):
        tool = self.sel.select(query)
        if tool == "calculator":
            nums, op = self.ext.calc_args(query)
            if len(nums) >= 2 and op:
                r = {"+": nums[0]+nums[1], "-": nums[0]-nums[1],
                     "*": nums[0]*nums[1], "/": nums[0]/nums[1] if nums[1] else float('nan')}[op]
                return f"[calculator] {nums[0]:g} {op} {nums[1]:g} = {r:g}"
            return "[calculator] couldn't parse the numbers"
        if tool == "time":
            return f"[time] {datetime.datetime.now():%H:%M:%S}"
        return "[none] (no tool needed)"
    def measure(self, test):       # test: list of (query, expected_tool)
        hit = sum(self.sel.select(q) == t for q, t in test)
        self._score = hit / len(test) if test else 0.0
        return self._score


def main():
    s = Synthesus()
    print("=== tool use is gated on its organism ===")
    print(f"can('use_tool') before organism: {s.can('use_tool')}")
    try: s.do("use_tool", "what is 7 times 8")
    except CapabilityUnavailable as e: print(f"  do() -> BLOCKED: {e}")

    org = ToolUseOrganism(); s.register(org); org.train()
    test = [("what is 7 times 8", "calculator"), ("add 12 and 30", "calculator"),
            ("whats the time right now", "time"), ("do you have the time", "time"),
            ("hi there friend", "none"), ("tell me a story", "none")]
    score = org.measure(test)
    print(f"\ntrained + measured. tool-selection accuracy = {score*100:.0f}%  (bar {org.bar*100:.0f}%)")
    print(f"can('use_tool') now: {s.can('use_tool')}")
    print("  organs (dependencies):", list(org.organs))
    for q in ["what is 7 times 8", "what is 100 divided by 5", "whats the time", "tell me about dragons"]:
        print(f"  do('use_tool', {q!r}) -> {s.do('use_tool', q)}")
    print("\nSynthesus cannot use tools without this organism (blocked above). Ability #3,")
    print("real tools execute (calculator genuinely computes), earned by measurement.")


if __name__ == "__main__":
    main()
