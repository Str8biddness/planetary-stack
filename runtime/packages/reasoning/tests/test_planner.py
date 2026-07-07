# core/reasoning/tests/test_planner.py
import unittest
from core.reasoning.planner import TaskDecomposer, DomainRouter, CriticVerifier

class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.decomposer = TaskDecomposer()
        self.router = DomainRouter()
        self.verifier = CriticVerifier()

    def test_decomposition_simple(self):
        query = "What is the capital of France?"
        tasks = self.decomposer.decompose(query)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['description'], "What is the capital of France")

    def test_decomposition_complex(self):
        query = "What is the capital of France and what is its population?"
        tasks = self.decomposer.decompose(query)
        self.assertGreaterEqual(len(tasks), 2)

    def test_domain_routing(self):
        # Test keyword-based routing
        task = {"task_id": "1", "description": "Write a python function", "domain_hint": "general"}
        domain = self.router.route(task)
        self.assertEqual(domain, "code")

        # Test domain hint override
        task = {"task_id": "2", "description": "What is 1+1?", "domain_hint": "math"}
        domain = self.router.route(task)
        self.assertEqual(domain, "math")

    def test_verification(self):
        answer = "Paris is the capital of France."
        context = ["Paris is the capital of France."]
        query = "What is the capital of France?"
        result = self.verifier.verify(answer, context, query)
        self.assertTrue(result['is_valid'])
        self.assertGreater(result['confidence_score'], 0.5)

if __name__ == '__main__':
    unittest.main()
