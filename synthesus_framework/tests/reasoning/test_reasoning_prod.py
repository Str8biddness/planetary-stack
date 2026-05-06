import unittest
import sys
import os

# Add the repo root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core.reasoning.planner import Planner
from core.reasoning.query_decomposer import QueryDecomposer
from core.reasoning.domain_router import DomainRouter, DomainType
from core.reasoning.verifier import AnswerVerifier, VerificationStatus
from core.reasoning.synthesizer import CrossDomainSynthesizer
from core.reasoning.reranker import CrossEncoderReranker

class TestReasoningProd(unittest.TestCase):
    def setUp(self):
        self.planner = Planner()
        self.decomposer = QueryDecomposer()
        self.router = DomainRouter()
        self.verifier = AnswerVerifier()
        self.synthesizer = CrossDomainSynthesizer()

    def test_query_decomposition(self):
        query = "How does the economy work in the kingdom and what are the NPC motivations?"
        result = self.decomposer.decompose(query)
        self.assertGreaterEqual(len(result.sub_tasks), 2)
        # Check if domains are inferred correctly via utils
        self.assertTrue(any(t.domain == "world" for t in result.sub_tasks))
        self.assertTrue(any(t.domain == "character" for t in result.sub_tasks))

    def test_domain_routing(self):
        # Create mock tasks
        class MockTask:
            def __init__(self, task_id, query):
                self.task_id = task_id
                self.query = query
                self.dependencies = []

        tasks = [
            MockTask("t1", "Tell me about the economy"),
            MockTask("t2", "How is the weather today?")
        ]
        routing = self.router.route(tasks)
        self.assertEqual(len(routing.routes), 2)
        self.assertEqual(routing.routes[0].primary_domain, DomainType.WORLD)

    def test_synthesis_with_deduplication(self):
        domain_contexts = {
            "world": ["The kingdom is rich in gold.", "The king loves gold."],
            "character": ["The kingdom is rich in gold.", "NPCs want gold."]
        }
        query = "Tell me about gold in the kingdom."
        answer = self.synthesizer.synthesize(domain_contexts, query)
        # "The kingdom is rich in gold." should only appear once (deduplicated)
        self.assertEqual(answer.count("The kingdom is rich in gold."), 1)
        # New format uses ## UPPERCASE
        self.assertIn("## WORLD", answer)
        self.assertIn("## CHARACTER", answer)

    def test_verification_and_revision(self):
        query = "Is Paris in France?"
        answer = "The moon is made of cheese." # Decisively different
        context = ["Paris is the capital of France."]
        result = self.verifier.verify(answer, query, context)
        self.assertEqual(result.status, VerificationStatus.FAILED)
        
        revised = self.verifier.generate_revision(answer, result)
        self.assertIn("[VERIFIED CONTEXT NEEDED]", revised)

    def test_reranker_fallback(self):
        # Test reranker fallback when sentence_transformers is missing or fails
        reranker = CrossEncoderReranker()
        query = "test"
        chunks = ["chunk1", "chunk2"]
        # This should return fallback results instead of crashing if deps missing
        results = reranker.rerank(query, chunks)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["chunk"], "chunk1")

if __name__ == "__main__":
    unittest.main()
