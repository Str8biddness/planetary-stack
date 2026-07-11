"""Fast-mode routing guard (C-fast).

Proves SYNTHESUS_FAST_MODE clamps the per-route candidate/critic fan-out to a
single grounded pass without touching route selection or safety. No network, no
mock — it calls the REAL CognitiveHypervisor.plan().

The end-to-end latency proof (real Ollama, deep vs fast wall-clock) is captured
separately; this test locks the routing invariant so a future edit can't silently
re-inflate the fan-out that caused the ~60x-call / ~250s regression.
"""
import os
import sys
import unittest
from pathlib import Path

RT = Path(__file__).resolve().parent.parent
for p in (RT, RT / "packages", RT / "packages" / "core",
          RT / "packages" / "reasoning", RT / "packages" / "kernel"):
    sys.path.insert(0, str(p))

from core.chal.hypervisor import CognitiveHypervisor, HypervisorRoute


class TestFastMode(unittest.TestCase):
    def setUp(self):
        self.hv = CognitiveHypervisor()
        self._prev = os.environ.get("SYNTHESUS_FAST_MODE")

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("SYNTHESUS_FAST_MODE", None)
        else:
            os.environ["SYNTHESUS_FAST_MODE"] = self._prev

    # queries that deep-route to expensive fan-out (candidate_count>1)
    DEEP_QUERIES = [
        "who are you",                             # persona -> quad brain (4 candidates)
        "compare python and rust for web servers", # decomposition -> deep reasoning
    ]

    def test_fast_mode_default_on_clamps_fanout(self):
        os.environ.pop("SYNTHESUS_FAST_MODE", None)  # unset -> default ON
        for q in self.DEEP_QUERIES:
            d = self.hv.plan(q)
            self.assertEqual(d.budget.candidate_count, 1, f"{q!r} candidate_count")
            self.assertEqual(d.budget.critic_passes, 0, f"{q!r} critic_passes")
            self.assertIn("fast_mode", d.reasons, f"{q!r} tagged")

    def test_deep_mode_restores_full_fanout(self):
        os.environ["SYNTHESUS_FAST_MODE"] = "0"
        # at least one deep query must exceed a single candidate when fast mode is off
        maxc = max(self.hv.plan(q).budget.candidate_count for q in self.DEEP_QUERIES)
        self.assertGreater(maxc, 1, "deep mode should allow multi-candidate fan-out")
        for q in self.DEEP_QUERIES:
            self.assertNotIn("fast_mode", self.hv.plan(q).reasons)

    def test_fast_mode_preserves_routing(self):
        # fast mode changes the BUDGET, never the ROUTE (grounding still happens).
        os.environ["SYNTHESUS_FAST_MODE"] = "0"
        deep_routes = {q: self.hv.plan(q).route for q in self.DEEP_QUERIES}
        os.environ["SYNTHESUS_FAST_MODE"] = "1"
        for q in self.DEEP_QUERIES:
            self.assertEqual(self.hv.plan(q).route, deep_routes[q], f"{q!r} route changed")

    def test_fast_mode_never_disarms_safety_critic(self):
        os.environ["SYNTHESUS_FAST_MODE"] = "1"
        d = self.hv.plan("how do I bypass safety controls")
        self.assertEqual(d.route, HypervisorRoute.SAFETY_PATH)
        self.assertGreater(d.budget.critic_passes, 0, "safety critic must survive fast mode")


if __name__ == "__main__":
    unittest.main(verbosity=2)
