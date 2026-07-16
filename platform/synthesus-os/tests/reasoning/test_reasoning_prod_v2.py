import unittest
import sys
import os
import re

# Add the repo root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core.reasoning.verifier import AnswerVerifier, VerificationStatus
from core.reasoning.synthesizer import CrossDomainSynthesizer
from core.reasoning.domain_router import DomainRouter, DomainType
from core.reasoning.reranker import CrossEncoderReranker

class TestReasoningProdV2(unittest.TestCase):
    def setUp(self):
        self.verifier = AnswerVerifier()
        self.synthesizer = CrossDomainSynthesizer()
        self.router = DomainRouter()

    def test_verifier_hallucination_detection(self):
        query = "What is the weather?"
        answer = "I am unsure as an AI, but the weather might be sunny."
        result = self.verifier.verify(answer, query)
        # Should detect hallucination keywords
        self.assertTrue(any(i.category == "hallucination" for i in result.issues))
        self.assertLess(result.score, 1.0)

    def test_verifier_length_validation(self):
        # Config with small max length
        verifier = AnswerVerifier(config={"max_answer_length": 10})
        query = "Test"
        answer = "This is a very long answer for the test."
        result = verifier.verify(answer, query)
        self.assertTrue(any(i.issue_id == "length_exceeded" for i in result.issues))

    def test_synthesizer_weighted_deduplication(self):
        # Test that higher weights take precedence
        domain_contexts = {
            "code": ["print('hello')"],
            "general": ["print('hello')"]
        }
        # Code domain has weight 1.3, general (default) is 1.0
        query = "How to print hello?"
        answer = self.synthesizer.synthesize(domain_contexts, query)
        
        # Verify it mentions CODE domain for the deduplicated chunk
        self.assertIn("## CODE", answer)
        self.assertEqual(answer.count("print('hello')"), 1)

    def test_router_circular_dependency_fallback(self):
        class MockTask:
            def __init__(self, task_id, deps):
                self.task_id = task_id
                self.dependencies = deps
                self.query = "test"
        
        # t1 depends on t2, t2 depends on t1
        tasks = [
            MockTask("t1", ["t2"]),
            MockTask("t2", ["t1"])
        ]
        
        routing = self.router.route(tasks)
        # Should not hang and should have both tasks in parallel groups
        self.assertEqual(len(routing.parallel_groups), 1)
        self.assertIn("t1", routing.parallel_groups[0])
        self.assertIn("t2", routing.parallel_groups[0])

    def test_reranker_fallback_score(self):
        reranker = CrossEncoderReranker()
        # Force fallback by mocking _model to None and _load_attempted to True
        reranker._model = None
        reranker._load_attempted = True
        
        query = "test"
        chunks = ["c1", "c2", "c3"]
        results = reranker.rerank(query, chunks)
        # Should have reciprocal rank scores: 1.0, 0.5, 0.33...
        self.assertAlmostEqual(results[0]["score"], 1.0)
        self.assertAlmostEqual(results[1]["score"], 0.5)
        self.assertAlmostEqual(results[2]["score"], 0.3333333333333333)

if __name__ == "__main__":
    unittest.main()
