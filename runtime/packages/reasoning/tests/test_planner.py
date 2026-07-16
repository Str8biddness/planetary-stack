# core/reasoning/tests/test_planner.py
import unittest
from core.reasoning.planner import TaskDecomposer, DomainRouter, CriticVerifier
from core.reasoning.query_decomposer import DecomposedTask
from core.reasoning.verifier import VerificationStatus

class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.decomposer = TaskDecomposer()
        self.router = DomainRouter()
        self.verifier = CriticVerifier()

    def test_decomposition_simple(self):
        query = "What is the capital of France?"
        result = self.decomposer.decompose(query)
        self.assertEqual(len(result.sub_tasks), 1)
        self.assertEqual(result.sub_tasks[0].query, query)

    def test_decomposition_complex(self):
        query = "What is the capital of France and what is its population?"
        result = self.decomposer.decompose(query)
        self.assertGreaterEqual(len(result.sub_tasks), 2)

    def test_domain_routing(self):
        # Test keyword-based routing
        task = DecomposedTask("1", "Write a python function", "general", "Write a python function")
        plan = self.router.route([task])
        self.assertEqual(plan.routes[0].primary_domain.value, "code")

        # Test domain hint override
        task = DecomposedTask("2", "Calculate 1+1", "math", "Calculate 1+1")
        plan = self.router.route([task])
        self.assertEqual(plan.routes[0].primary_domain.value, "math")

    def test_verification(self):
        answer = "Paris is the capital of France."
        context = ["Paris is the capital of France."]
        query = "What is the capital of France?"
        result = self.verifier.verify(answer, query, context)
        self.assertEqual(result.status, VerificationStatus.PASSED)
        self.assertGreater(result.score, 0.5)

if __name__ == '__main__':
    unittest.main()
