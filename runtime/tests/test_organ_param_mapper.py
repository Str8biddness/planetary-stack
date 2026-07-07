# tests/test_organ_param_mapper.py
import unittest
from core.generation.organ_param_mapper import map_organs_to_config, build_response_plan
from core.generation.response_plan import GenerationConfig, ResponsePlan

class TestOrganParamMapper(unittest.TestCase):
    def test_map_organs_to_config_safe(self):
        # High policy prior (S=0.9), Low risk (R=0.1)
        scores = {"policy_prior": 0.9, "risk_outcome": 0.1, "attention": 0.5}
        cfg = map_organs_to_config(scores)
        
        # High safety -> Low temperature
        self.assertLess(cfg.temperature, 0.5)
        self.assertEqual(cfg.top_k, 10)
        
    def test_map_organs_to_config_risky(self):
        # Low policy prior (S=0.1), High risk (R=0.9)
        scores = {"policy_prior": 0.1, "risk_outcome": 0.9, "attention": 0.1}
        cfg = map_organs_to_config(scores)
        
        # Low safety -> Higher temperature
        self.assertGreater(cfg.temperature, 1.0)
        # High risk -> More candidates
        self.assertGreaterEqual(cfg.num_candidates, 4)

    def test_build_response_plan(self):
        event = {
            "intent": "warn",
            "role": "analyst",
            "summary": "System overload detected",
            "domain": "sysops"
        }
        scores = {"policy_prior": 0.8}
        plan = build_response_plan(event, scores)
        
        self.assertEqual(plan.intent, "warn")
        self.assertEqual(plan.domain, "sysops")
        self.assertEqual(plan.decoder_mode, "deterministic")
        self.assertIn("System overload detected", plan.key_points)

if __name__ == '__main__':
    unittest.main()
