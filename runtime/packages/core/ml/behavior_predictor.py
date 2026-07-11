"""Re-export real BehaviorPredictor from reasoning/ (core/ml was a pass stub)."""
from reasoning.behavior_predictor import BehaviorPredictor  # noqa: F401

__all__ = ["BehaviorPredictor"]
