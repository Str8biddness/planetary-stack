# tests/test_response_plan.py
import unittest
from core.generation.response_plan import ResponsePlan, GenerationConfig, GenerationTrace

class TestResponsePlan(unittest.TestCase):
    def test_response_plan_defaults(self):
        plan = ResponsePlan(intent='inform', style='formal', safety_level=0.5, target_length=50)
        self.assertEqual(plan.intent, 'inform')
        self.assertEqual(plan.style, 'formal')
        self.assertEqual(plan.domain, 'general')
        self.assertEqual(plan.key_points, [])

    def test_generation_config_defaults(self):
        cfg = GenerationConfig()
        self.assertEqual(cfg.temperature, 1.0)
        self.assertEqual(cfg.repetition_penalty, 1.1)
        self.assertEqual(cfg.num_candidates, 1)

    def test_generation_trace_init(self):
        trace = GenerationTrace(text="Hello world")
        self.assertEqual(trace.text, "Hello world")
        self.assertTrue(trace.constraints_satisfied)
        self.assertEqual(trace.decode_attempts, 1)

if __name__ == '__main__':
    unittest.main()
