import unittest
import sys
import os

# Add the repo root to sys.path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core.reasoning.planner import Planner
from core.reasoning.query_decomposer import QueryDecomposer
from core.reasoning.domain_router import DomainRouter, DomainType
from core.reasoning.verifier import AnswerVerifier, VerificationStatus
from core.reasoning.synthesizer import CrossDomainSynthesizer

class TestReasoningLayer(unittest.TestCase):
    def setUp(self):
        self.planner = Planner()
        self.decomposer = QueryDecomposer()
        self.router = DomainRouter()
        self.verifier = AnswerVerifier()
        self.synthesizer = CrossDomainSynthesizer()

    def test_decomposition(self):
        query = "How does the economy work and what are the NPC emotions?"
        result = self.decomposer.decompose(query)
        self.assertGreaterEqual(len(result.sub_tasks), 2)
        self.assertTrue(any("economy" in t.query.lower() for t in result.sub_tasks))
        self.assertTrue(any("emotion" in t.query.lower() or "npc" in t.query.lower() for t in result.sub_tasks))

    def test_routing(self):
        from core.reasoning.query_decomposer import DecomposedTask
        tasks = [
            DecomposedTask(task_id="t1", description="Economy task", domain="world", query="How does the economy work in the kingdom?"),
            DecomposedTask(task_id="t2", description="Emotion task", domain="emotion", query="I feel very sad and anxious today")
        ]
        result = self.router.route(tasks)
        self.assertEqual(len(result.routes), 2)
        self.assertEqual(result.routes[0].primary_domain, DomainType.WORLD)
        self.assertEqual(result.routes[1].primary_domain, DomainType.EMOTION)

    def test_parallel_groups_with_dependencies(self):
        from core.reasoning.query_decomposer import DecomposedTask
        tasks = [
            DecomposedTask(task_id="t1", description="Task 1", domain="world", query="Q1"),
            DecomposedTask(task_id="t2", description="Task 2", domain="world", query="Q2", dependencies=["t1"])
        ]
        from core.reasoning.domain_router import RouteResult
        routes = [
            RouteResult(task_id="t1", primary_domain=DomainType.WORLD),
            RouteResult(task_id="t2", primary_domain=DomainType.WORLD)
        ]
        groups = self.router._compute_parallel_groups(routes, tasks)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0], ["t1"])
        self.assertEqual(groups[1], ["t2"])

    def test_verification(self):
        query = "Is Paris the capital of France?"
        answer = "Yes, Paris is the capital of France."
        context = ["Paris is the capital and largest city of France."]
        result = self.verifier.verify(answer, query, context)
        self.assertEqual(result.status, VerificationStatus.PASSED)
        self.assertGreater(result.score, 0.7)

    def test_synthesis(self):
        domain_contexts = {
            "world": ["The economy is based on gold."],
            "emotion": ["NPCs feel happy when they have gold."]
        }
        query = "Explain economy and emotions."
        result = self.synthesizer.synthesize(domain_contexts, query)
        self.assertIn("World", result)
        self.assertIn("Emotion", result)
        self.assertIn("gold", result.lower())

if __name__ == "__main__":
    unittest.main()
