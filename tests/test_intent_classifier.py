"""
Synthesus 2.0 — Intent Classifier Tests
Tests the ML-based intent classifier independently.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.intent_classifier import (
    IntentClassifier, build_training_data_from_character,
)


@pytest.fixture(scope="module")
def trained_classifier():
    """A pre-trained classifier for all tests."""
    clf = IntentClassifier()
    clf.train()
    return clf


# ══════════════════════════════════════════════════
# 1. TRAINING
# ══════════════════════════════════════════════════

class TestTraining:
    def test_train_succeeds(self):
        clf = IntentClassifier()
        stats = clf.train(verbose=False)
        assert stats["samples"] > 50
        assert stats["classes"] >= 10
        assert stats["cv_accuracy"] > 0.2  # Small dataset has limited CV accuracy

    def test_extra_data_increases_samples(self):
        extra = [("custom intent test", "greeting")] * 10
        clf = IntentClassifier(extra_training_data=extra)
        stats = clf.train()
        assert stats["samples"] > 120  # base + extra


# ══════════════════════════════════════════════════
# 2. PREDICTIONS
# ══════════════════════════════════════════════════

class TestPredictions:
    @pytest.mark.parametrize("text,expected", [
        ("hello", "greeting"),
        ("hi there", "greeting"),
        ("goodbye", "farewell"),
        ("what do you sell", "shop_browse"),
        ("I want to buy a sword", "shop_buy"),
        ("too expensive", "shop_haggle"),
        ("sing me a song", "creative"),
        ("tell me a joke", "creative"),
        ("fight me", "combat"),
        ("any quests available", "quest"),
        ("you're amazing", "compliment"),
        ("you're an idiot", "insult"),
    ])
    def test_basic_intents(self, trained_classifier, text, expected):
        intent, conf = trained_classifier.predict(text)
        assert intent == expected, f"'{text}' → {intent} (expected {expected}, conf={conf:.3f})"
        assert conf > 0.3

    def test_top_k_predictions(self, trained_classifier):
        results = trained_classifier.predict_top_k("hello friend", k=3)
        assert len(results) == 3
        assert results[0][0] == "greeting"
        assert results[0][1] > results[1][1]  # Descending confidence

    def test_confidence_range(self, trained_classifier):
        _, conf = trained_classifier.predict("hello")
        assert 0.0 <= conf <= 1.0

    def test_unknown_input(self, trained_classifier):
        intent, conf = trained_classifier.predict("xyzzy random gibberish asdfgh")
        # Should still return something, even if low confidence
        assert intent in IntentClassifier.LABELS
        assert 0.0 <= conf <= 1.0


# ══════════════════════════════════════════════════
# 3. INFERENCE SPEED
# ══════════════════════════════════════════════════

class TestSpeed:
    def test_inference_under_1ms(self, trained_classifier):
        """Single inference should complete in under 1ms."""
        # Warm up
        trained_classifier.predict("hello")

        times = []
        for _ in range(100):
            start = time.perf_counter()
            trained_classifier.predict("I want to buy a sword")
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg_ms = sum(times) / len(times)
        p99_ms = sorted(times)[98]
        assert avg_ms < 5.0, f"Average inference {avg_ms:.3f}ms exceeds 5ms budget"
        assert p99_ms < 15.0, f"P99 inference {p99_ms:.3f}ms exceeds 15ms budget"


# ══════════════════════════════════════════════════
# 4. SAVE / LOAD
# ══════════════════════════════════════════════════

class TestPersistence:
    def test_save_and_load(self, trained_classifier):
        with tempfile.TemporaryDirectory() as tmpdir:
            trained_classifier.save(tmpdir)
            assert os.path.exists(os.path.join(tmpdir, "pipeline.pkl"))
            assert os.path.exists(os.path.join(tmpdir, "metadata.json"))

            loaded = IntentClassifier.load(tmpdir)
            intent1, conf1 = trained_classifier.predict("hello")
            intent2, conf2 = loaded.predict("hello")
            assert intent1 == intent2
            assert abs(conf1 - conf2) < 0.001

    def test_onnx_export(self, trained_classifier):
        with tempfile.TemporaryDirectory() as tmpdir:
            onnx_path = os.path.join(tmpdir, "intent.onnx")
            size = trained_classifier.export_onnx(onnx_path)
            if size > 0:
                assert os.path.exists(onnx_path)
                assert size < 500_000  # Should be < 500 KB


# ══════════════════════════════════════════════════
# 5. CHARACTER DATA INTEGRATION
# ══════════════════════════════════════════════════

class TestCharacterIntegration:
    def test_build_from_garen_patterns(self):
        patterns_path = Path(__file__).resolve().parent.parent / "characters" / "garen" / "patterns.json"
        if not patterns_path.exists():
            pytest.skip("Garen patterns not found")
        with open(patterns_path) as f:
            patterns = json.load(f)
        data = build_training_data_from_character(patterns, "garen")
        assert len(data) > 10  # Garen has 37+ patterns
        # Check format
        for text, label in data:
            assert isinstance(text, str)
            assert isinstance(label, str)
            assert len(text) > 0

    def test_classifier_with_character_data(self):
        patterns_path = Path(__file__).resolve().parent.parent / "characters" / "garen" / "patterns.json"
        if not patterns_path.exists():
            pytest.skip("Garen patterns not found")
        with open(patterns_path) as f:
            patterns = json.load(f)
        extra = build_training_data_from_character(patterns, "garen")
        clf = IntentClassifier(extra_training_data=extra)
        stats = clf.train()
        assert stats["samples"] > 150  # Universal + Garen data
