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
        result = self.synthesizer.synthesize(domain_contexts, "Tell me about Paris")
        # The duplicate capital fact should appear once while the distinct city
        # fact remains in the formatted response.
        self.assertEqual(result.count("The capital of France is Paris."), 1)
        self.assertIn("Paris is the largest city in France.", result)

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
