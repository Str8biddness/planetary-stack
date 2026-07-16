#!/usr/bin/env python3
"""
EmotionDetector — ML Swarm Micro-Model #7
Classifies the emotional state of player input text.
Uses a lexicon detector plus an optional learned text classifier.
"""

from __future__ import annotations

import json
import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline


class EmotionDetector:
    LEXICON = {
        "happy": ("joy", 0.8), "glad": ("joy", 0.7), "great": ("joy", 0.6),
        "love": ("joy", 0.9), "wonderful": ("joy", 0.8), "awesome": ("joy", 0.8),
        "amazing": ("joy", 0.8), "excited": ("joy", 0.9), "fantastic": ("joy", 0.8),
        "perfect": ("joy", 0.7), "beautiful": ("joy", 0.6), "enjoy": ("joy", 0.7),
        "thanks": ("joy", 0.5), "thank": ("joy", 0.5), "pleased": ("joy", 0.7),
        "fun": ("joy", 0.6), "yay": ("joy", 0.8), "nice": ("joy", 0.5),
        "cool": ("joy", 0.5), "sweet": ("joy", 0.6), "brilliant": ("joy", 0.7),
        "haha": ("joy", 0.6), "lol": ("joy", 0.5), "lmao": ("joy", 0.7),
        "angry": ("anger", 0.9), "furious": ("anger", 1.0), "hate": ("anger", 0.9),
        "stupid": ("anger", 0.7), "idiot": ("anger", 0.8), "annoying": ("anger", 0.6),
        "mad": ("anger", 0.7), "pissed": ("anger", 0.8), "rage": ("anger", 0.9),
        "unfair": ("anger", 0.6), "ridiculous": ("anger", 0.6), "terrible": ("anger", 0.7),
        "worst": ("anger", 0.7), "awful": ("anger", 0.7), "damn": ("anger", 0.5),
        "hell": ("anger", 0.4), "sucks": ("anger", 0.6), "garbage": ("anger", 0.7),
        "sad": ("sadness", 0.8), "sorry": ("sadness", 0.5), "miss": ("sadness", 0.6),
        "lonely": ("sadness", 0.8), "depressed": ("sadness", 0.9), "cry": ("sadness", 0.8),
        "heartbroken": ("sadness", 0.9), "disappointed": ("sadness", 0.7),
        "unfortunate": ("sadness", 0.5), "loss": ("sadness", 0.6), "grief": ("sadness", 0.9),
        "regret": ("sadness", 0.7), "miserable": ("sadness", 0.8),
        "afraid": ("fear", 0.8), "scared": ("fear", 0.8), "fear": ("fear", 0.9),
        "terrified": ("fear", 1.0), "nervous": ("fear", 0.6), "worried": ("fear", 0.6),
        "anxious": ("fear", 0.7), "panic": ("fear", 0.9), "horror": ("fear", 0.8),
        "danger": ("fear", 0.6), "threat": ("fear", 0.6), "creepy": ("fear", 0.5),
        "surprised": ("surprise", 0.8), "shocked": ("surprise", 0.9),
        "wow": ("surprise", 0.7), "whoa": ("surprise", 0.7),
        "unbelievable": ("surprise", 0.7), "unexpected": ("surprise", 0.6),
        "omg": ("surprise", 0.7), "incredible": ("surprise", 0.6),
        "really": ("surprise", 0.3), "seriously": ("surprise", 0.4),
        "disgusting": ("disgust", 0.9), "gross": ("disgust", 0.7),
        "nasty": ("disgust", 0.7), "revolting": ("disgust", 0.9),
        "ew": ("disgust", 0.6), "yuck": ("disgust", 0.6),
        "vile": ("disgust", 0.8), "repulsive": ("disgust", 0.9),
        "trust": ("trust", 0.8), "believe": ("trust", 0.6), "reliable": ("trust", 0.7),
        "honest": ("trust", 0.7), "loyal": ("trust", 0.8), "faith": ("trust", 0.7),
        "promise": ("trust", 0.6), "depend": ("trust", 0.6), "ally": ("trust", 0.7),
        "friend": ("trust", 0.6),
    }

    NEGATORS = {"not", "no", "never", "neither", "nobody", "nothing", "nowhere", "nor", "don't", "doesn't", "didn't", "won't", "wouldn't", "can't", "couldn't", "shouldn't", "isn't", "aren't"}
    INTENSIFIERS = {"very": 1.3, "really": 1.2, "so": 1.2, "extremely": 1.5, "super": 1.3, "incredibly": 1.4, "absolutely": 1.3, "totally": 1.2, "utterly": 1.4}
    OPPOSITES = {"joy": "sadness", "sadness": "joy", "anger": "trust", "trust": "anger", "fear": "trust", "surprise": "neutral", "disgust": "trust"}

    def __init__(self):
        self._model: Optional[Pipeline] = None
        self._is_trained = False

    def train(self, training_data: List[Tuple[str, str]]) -> Dict[str, Any]:
        texts = [t for t, _ in training_data]
        labels = [y for _, y in training_data]
        if not texts:
            raise ValueError("EmotionDetector.train requires labeled training data")

        self._model = Pipeline([
            ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), max_features=4000, sublinear_tf=True)),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced")),
        ])
        self._model.fit(texts, labels)
        self._is_trained = True
        cv = cross_val_score(self._model, texts, labels, cv=min(5, len(texts)))
        return {
            "samples": len(texts),
            "classes": len(set(labels)),
            "cv_accuracy": float(np.mean(cv)),
            "cv_std": float(np.std(cv)),
        }

    def _lexicon_detect(self, text: str) -> Dict[str, Any]:
        words = re.findall(r'\b\w+\b', text.lower())
        if not words:
            return self._neutral_result()

        scores = {"joy": 0.0, "anger": 0.0, "sadness": 0.0, "fear": 0.0, "surprise": 0.0, "disgust": 0.0, "trust": 0.0, "neutral": 0.1}
        for i, word in enumerate(words):
            if word not in self.LEXICON:
                continue
            emotion, weight = self.LEXICON[word]
            negated = i > 0 and words[i - 1] in self.NEGATORS or i > 1 and words[i - 2] in self.NEGATORS
            multiplier = 1.0
            if i > 0 and words[i - 1] in self.INTENSIFIERS:
                multiplier = self.INTENSIFIERS[words[i - 1]]
            if negated:
                opposite = self.OPPOSITES.get(emotion, "neutral")
                scores[opposite] += weight * multiplier * 0.7
            else:
                scores[emotion] += weight * multiplier

        exclamation_count = text.count("!")
        question_count = text.count("?")
        caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
        if exclamation_count > 0:
            max_emo = max(scores, key=scores.get)
            if max_emo != "neutral":
                scores[max_emo] *= 1.0 + min(exclamation_count, 3) * 0.15
        if caps_ratio > 0.5 and len(text) > 3:
            scores["anger"] += 0.3
            max_emo = max(scores, key=scores.get)
            if max_emo != "neutral":
                scores[max_emo] *= 1.2
        if question_count > 0:
            scores["surprise"] += 0.1 * question_count

        total = sum(scores.values())
        if total > 0:
            scores = {k: round(v / total, 4) for k, v in scores.items()}
        sorted_emotions = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_emotions[0][0]
        secondary = sorted_emotions[1][0] if len(sorted_emotions) > 1 and sorted_emotions[1][1] > 0.1 else None
        intensity = 1.0 - scores.get("neutral", 0.0)
        return {"primary": primary, "secondary": secondary, "scores": scores, "intensity": round(max(0.0, min(intensity, 1.0)), 4)}

    def detect(self, text: str) -> Dict[str, Any]:
        rule_result = self._lexicon_detect(text)
        if not self._is_trained or self._model is None:
            return rule_result

        try:
            proba = self._model.predict_proba([text])[0]
            learned = {cls: float(prob) for cls, prob in zip(self._model.classes_, proba)}
            learned = {k: learned.get(k, 0.0) for k in rule_result["scores"].keys()}
            merged = {}
            total = 0.0
            for emo in rule_result["scores"]:
                merged[emo] = 0.65 * rule_result["scores"].get(emo, 0.0) + 0.35 * learned.get(emo, 0.0)
                total += merged[emo]
            if total > 0:
                merged = {k: round(v / total, 4) for k, v in merged.items()}
            sorted_emotions = sorted(merged.items(), key=lambda x: x[1], reverse=True)
            primary = sorted_emotions[0][0]
            secondary = sorted_emotions[1][0] if len(sorted_emotions) > 1 and sorted_emotions[1][1] > 0.1 else None
            return {"primary": primary, "secondary": secondary, "scores": merged, "intensity": round(max(0.0, min(1.0, 1.0 - merged.get("neutral", 0.0))), 4)}
        except Exception:
            return rule_result

    def _neutral_result(self) -> Dict[str, Any]:
        return {"primary": "neutral", "secondary": None, "scores": {"joy": 0.0, "anger": 0.0, "sadness": 0.0, "fear": 0.0, "surprise": 0.0, "disgust": 0.0, "trust": 0.0, "neutral": 1.0}, "intensity": 0.0}

    def save(self, path: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            pickle.dump({"model": self._model, "trained": self._is_trained}, f)

    @classmethod
    def load(cls, path: str) -> "EmotionDetector":
        obj = cls()
        with open(Path(path), "rb") as f:
            payload = pickle.load(f)
        obj._model = payload.get("model")
        obj._is_trained = payload.get("trained", False)
        return obj

    def export_onnx(self, path: str) -> int:
        if not self._is_trained or self._model is None:
            raise ValueError("Model must be trained before ONNX export")
        try:
            from skl2onnx import convert_sklearn
            from skl2onnx.common.data_types import StringTensorType
            onnx_model = convert_sklearn(self._model, initial_types=[("text", StringTensorType([None, 1]))], target_opset=15)
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "wb") as f:
                f.write(onnx_model.SerializeToString())
            return p.stat().st_size
        except Exception:
            return 0

    def get_stats(self) -> Dict[str, Any]:
        return {"model": "EmotionDetector", "emotions": ["joy", "anger", "sadness", "fear", "surprise", "disgust", "trust", "neutral"], "lexicon_size": len(self.LEXICON), "negators": len(self.NEGATORS), "intensifiers": len(self.INTENSIFIERS), "footprint_kb": 18, "is_trained": self._is_trained}
