"""Re-export the canonical sentiment analyzer and emotion mapping."""
from reasoning.sentiment_analyzer import (  # noqa: F401
    SENTIMENT_TO_EMOTION,
    SentimentAnalyzer,
)

__all__ = ["SENTIMENT_TO_EMOTION", "SentimentAnalyzer"]
