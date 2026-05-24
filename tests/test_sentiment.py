"""
Synthesus 2.0 — Sentiment Analyzer Tests
"""

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.sentiment_analyzer import SentimentAnalyzer, SENTIMENT_TO_EMOTION


@pytest.fixture(scope="module")
def trained_analyzer():
    analyzer = SentimentAnalyzer()
    analyzer.train()
    return analyzer


class TestTraining:
    def test_train_succeeds(self):
        analyzer = SentimentAnalyzer()
        stats = analyzer.train()
        assert stats["samples"] > 50
        assert stats["classes"] == 6

    def test_extra_data(self):
        extra = [("super amazing fantastic", "positive")] * 5
        analyzer = SentimentAnalyzer(extra_training_data=extra)
        stats = analyzer.train()
        assert stats["samples"] > 100


class TestPredictions:
    @pytest.mark.parametrize("text,expected", [
        ("hello friend, you're great", "positive"),
        ("thank you so much", "positive"),
        ("you're useless garbage", "negative"),
        ("I hate you", "negative"),
        ("what do you sell", "neutral"),
        ("how much is a sword", "neutral"),
        ("I'll kill you", "threatening"),
        ("prepare to die", "threatening"),
        ("please help me I'm desperate", "pleading"),
        ("I have nothing left please", "pleading"),
        ("you have beautiful eyes", "flirtatious"),
    ])
    def test_basic_sentiments(self, trained_analyzer, text, expected):
        sentiment, conf = trained_analyzer.predict(text)
        assert sentiment == expected, f"'{text}' → {sentiment} (expected {expected}, conf={conf:.3f})"
        assert conf > 0.25

    def test_confidence_range(self, trained_analyzer):
        _, conf = trained_analyzer.predict("hello")
        assert 0.0 <= conf <= 1.0

    def test_top_k(self, trained_analyzer):
        results = trained_analyzer.predict_top_k("I'll destroy you", k=3)
        assert len(results) == 3
        assert results[0][1] >= results[1][1]


class TestEmotionMapping:
    def test_sentiment_to_emotion(self, trained_analyzer):
        for sentiment, emotion in SENTIMENT_TO_EMOTION.items():
            assert trained_analyzer.to_emotion(sentiment) == emotion

    def test_analyze_returns_emotion(self, trained_analyzer):
        result = trained_analyzer.analyze("you're amazing")
        assert "sentiment" in result
        assert "emotion_trigger" in result
        assert "confidence" in result
        assert "top_3" in result
        assert result["emotion_trigger"] in SENTIMENT_TO_EMOTION.values()


class TestSpeed:
    def test_inference_under_5ms(self, trained_analyzer):
        trained_analyzer.predict("warmup")
        times = []
        for _ in range(100):
            start = time.perf_counter()
            trained_analyzer.predict("I want to buy a sword")
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        avg_ms = sum(times) / len(times)
        assert avg_ms < 5.0, f"Average inference {avg_ms:.3f}ms exceeds 5ms"


class TestPersistence:
    def test_save_and_load(self, trained_analyzer):
        with tempfile.TemporaryDirectory() as tmpdir:
            trained_analyzer.save(tmpdir)
            assert os.path.exists(os.path.join(tmpdir, "pipeline.pkl"))
            loaded = SentimentAnalyzer.load(tmpdir)
            s1, c1 = trained_analyzer.predict("hello")
            s2, c2 = loaded.predict("hello")
            assert s1 == s2
            assert abs(c1 - c2) < 0.001
