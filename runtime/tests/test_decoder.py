# tests/test_decoder.py
import unittest
import os
import math
from core.generation.decoder import decode_response, get_model
from core.generation.response_plan import ResponsePlan, GenerationConfig
from core.generation.ngram_model import NgramModel

class TestDecoder(unittest.TestCase):
    test_model_path = "data/vocab_test.pkl"

    @classmethod
    def setUpClass(cls):
        # Create a small test model
        os.makedirs("data", exist_ok=True)
        
        model = NgramModel(n=3)
        tables = {
            "unigrams": {"hello": 10, "world": 5, ".": 2},
            "bigrams": {"hello world": 5, "world .": 2},
            "trigrams": {"hello world .": 2}
        }
        model.train_from_tables(tables)
        model.save(cls.test_model_path)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_model_path):
            os.remove(cls.test_model_path)

    def test_decode_simple(self):
        plan = ResponsePlan(
            intent="greet", style="casual", safety_level=0.5, 
            target_length=2, domain="test"
        )
        config = GenerationConfig(temperature=0.1, max_tokens=10)
        
        trace = decode_response(plan, config)
        self.assertIn("hello", trace.text.lower())
        self.assertTrue(len(trace.text) > 0)
        self.assertGreater(trace.mean_logprob, -10.0)

    def test_decode_with_forbidden(self):
        plan = ResponsePlan(
            intent="greet", style="casual", safety_level=0.5, 
            target_length=2, domain="test",
            forbidden_phrases=["world"]
        )
        config = GenerationConfig(temperature=0.1, max_tokens=10)
        
        trace = decode_response(plan, config)
        # Should NOT contain 'world'
        self.assertNotIn("world", trace.text.lower())

    def test_decode_constraint_satisfaction(self):
        plan = ResponsePlan(
            intent="greet", style="casual", safety_level=0.5, 
            target_length=3, domain="test",
            key_points=["hello", "world"]
        )
        config = GenerationConfig(temperature=0.1, max_tokens=10)
        
        trace = decode_response(plan, config)
        # In our simple model, 'hello world .' should be generated and satisfy the points
        self.assertTrue(trace.constraints_satisfied)

if __name__ == '__main__':
    unittest.main()
