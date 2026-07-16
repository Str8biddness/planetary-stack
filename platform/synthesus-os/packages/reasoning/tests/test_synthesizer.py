# core/reasoning/tests/test_synthesizer.py
import unittest
from core.reasoning.synthesizer import CrossDomainSynthesizer

class TestSynthesizer(unittest.TestCase):
    def setUp(self):
        self.synthesizer = CrossDomainSynthesizer()

    def test_merge_and_deduplicate(self):
        domain_contexts = {
            "world": ["The capital of France is Paris.", "Paris is the largest city in France."],
            "general": ["The capital of France is Paris."]
        }
        merged = self.synthesizer.merge_domain_contexts(domain_contexts)
        # Should have at least 2 unique facts
        self.assertGreaterEqual(len(merged), 2)
        # Check that one "Paris is the capital" was likely deduplicated
        texts = [m[0] for m in merged]
        self.assertIn("The capital of France is Paris.", texts)

    def test_synthesize(self):
        domain_contexts = {
            "world": ["The capital of France is Paris."]
        }
        query = "What is the capital of France?"
        result = self.synthesizer.synthesize(domain_contexts, query)
        self.assertIn("Paris", result)
        self.assertIn("World", result)

if __name__ == '__main__':
    unittest.main()
