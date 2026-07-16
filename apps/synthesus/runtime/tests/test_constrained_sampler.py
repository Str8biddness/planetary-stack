# tests/test_constrained_sampler.py
import unittest
from core.generation.constrained_sampler import (
    apply_temperature, top_k_filter, top_p_filter, 
    apply_repetition_penalty, mask_forbidden_tokens
)

class TestConstrainedSampler(unittest.TestCase):
    def test_apply_temperature(self):
        dist = {"a": 0.5, "b": 0.5}
        # T=0.1 should sharpen: 'a' and 'b' should remain equal if equal, 
        # but let's test with unequal
        dist = {"a": 0.7, "b": 0.3}
        sharp = apply_temperature(dist, 0.1)
        self.assertGreater(sharp["a"], 0.9)
        
        flat = apply_temperature(dist, 2.0)
        self.assertLess(flat["a"], 0.7)

    def test_top_k_filter(self):
        dist = {"a": 0.4, "b": 0.3, "c": 0.2, "d": 0.1}
        filtered = top_k_filter(dist, 2)
        self.assertEqual(len(filtered), 2)
        self.assertIn("a", filtered)
        self.assertIn("b", filtered)
        self.assertAlmostEqual(sum(filtered.values()), 1.0)

    def test_top_p_filter(self):
        dist = {"a": 0.4, "b": 0.3, "c": 0.2, "d": 0.1}
        # top_p=0.5 should keep 'a' (0.4) and 'b' (0.3) -> 0.7
        filtered = top_p_filter(dist, 0.5)
        self.assertEqual(len(filtered), 2)
        self.assertIn("a", filtered)
        self.assertIn("b", filtered)

    def test_repetition_penalty(self):
        dist = {"apple": 0.5, "banana": 0.5}
        penalized = apply_repetition_penalty(dist, ["apple"], 2.0)
        # apple: 0.5 / 2.0 = 0.25
        # banana: 0.5
        # total: 0.75 -> apple: 0.33, banana: 0.66
        self.assertLess(penalized["apple"], penalized["banana"])

    def test_mask_forbidden(self):
        dist = {"bad": 0.5, "good": 0.5}
        masked = mask_forbidden_tokens(dist, ["bad word"], ["this", "is", "a"])
        # 'bad' should be masked if 'bad word' is forbidden and context is 'this is a'
        # Wait, candidate is 'this is a bad'. Not 'bad word' yet.
        
        # Let's test with exact match
        masked = mask_forbidden_tokens(dist, ["bad"], ["this", "is"])
        self.assertEqual(masked["bad"], 0.0)
        self.assertEqual(masked["good"], 1.0)

if __name__ == '__main__':
    unittest.main()
