"""Re-export real EmotionDetector from reasoning/ (core/ml was a pass stub)."""
from reasoning.emotion_detector import EmotionDetector  # noqa: F401

__all__ = ["EmotionDetector"]
