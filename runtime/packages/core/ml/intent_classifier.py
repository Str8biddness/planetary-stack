"""Re-export real IntentClassifier from reasoning/ (core/ml was a pass stub)."""
from reasoning.intent_classifier import IntentClassifier  # noqa: F401

__all__ = ["IntentClassifier"]
