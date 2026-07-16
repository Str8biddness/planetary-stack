"""Re-export the canonical intent classifier and training-data helper."""
from reasoning.intent_classifier import (  # noqa: F401
    IntentClassifier,
    build_training_data_from_character,
)

__all__ = ["IntentClassifier", "build_training_data_from_character"]
