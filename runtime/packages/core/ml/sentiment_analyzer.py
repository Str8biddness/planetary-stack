"""Re-export real SentimentAnalyzer from reasoning/ (core/ml was a pass stub)."""
from reasoning.sentiment_analyzer import SentimentAnalyzer  # noqa: F401

__all__ = ["SentimentAnalyzer"]
