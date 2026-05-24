#!/usr/bin/env python3
"""
BehaviorPredictor — ML Swarm Micro-Model #4
AIVM Synthesus 2.0

Predicts player behavior patterns to enable proactive NPC responses.
Uses a learned classifier when trained, otherwise falls back to a deterministic score model.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class BehaviorPredictor:
    ACTIONS = ["buy", "sell", "leave", "fight", "ask_question", "explore", "negotiate", "idle"]
    FEATURE_NAMES = ["turn_count", "avg_msg_length", "sentiment_trend", "topic_switches", "time_between_msgs", "question_ratio"]

    DEFAULT_WEIGHTS = {
        "buy": np.array([0.1, 0.2, 0.3, -0.1, -0.2, 0.1]),
        "sell": np.array([0.1, 0.1, 0.2, 0.0, -0.1, 0.0]),
        "leave": np.array([-0.3, -0.2, -0.4, 0.3, 0.5, -0.3]),
        "fight": np.array([0.0, -0.1, -0.6, 0.2, 0.0, -0.2]),
        "ask_question": np.array([0.2, 0.3, 0.1, 0.1, -0.1, 0.6]),
        "explore": np.array([0.0, 0.1, 0.1, 0.4, 0.0, 0.2]),
        "negotiate": np.array([0.2, 0.4, 0.2, 0.1, -0.1, 0.3]),
        "idle": np.array([-0.1, -0.3, -0.1, -0.1, 0.6, -0.2]),
    }

    def __init__(self):
        self._weights = {k: v.copy() for k, v in self.DEFAULT_WEIGHTS.items()}
        self._model: Optional[Pipeline] = None
        self._is_trained = False

    def _vectorize(self, features: Dict[str, float]) -> np.ndarray:
        return np.array([
            features.get("turn_count", 0) / 20.0,
            features.get("avg_msg_length", 10) / 50.0,
            features.get("sentiment_trend", 0.0),
            features.get("topic_switches", 0) / 5.0,
            features.get("time_between_msgs", 5.0) / 30.0,
            features.get("question_ratio", 0.5),
        ], dtype=np.float32)

    def _heuristic_predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        feat_vec = self._vectorize(features)
        scores = {action: float(np.dot(weights, feat_vec)) for action, weights in self._weights.items()}
        max_score = max(scores.values())
        exp_scores = {k: np.exp(v - max_score) for k, v in scores.items()}
        total = sum(exp_scores.values()) or 1.0
        probs = {k: round(v / total, 4) for k, v in exp_scores.items()}
        predicted = max(probs, key=probs.get)
        engagement = 1.0 - probs.get("leave", 0.0)
        escalation = probs.get("fight", 0.0) + probs.get("leave", 0.0) * 0.5
        return {
            "predicted_action": predicted,
            "action_probabilities": probs,
            "engagement_score": round(min(engagement, 1.0), 4),
            "escalation_risk": round(min(escalation, 1.0), 4),
        }

    def train(self, training_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        X = []
        y = []
        for row in training_data:
            if "action" not in row:
                continue
            X.append(self._vectorize(row))
            y.append(row["action"])
        if not X:
            raise ValueError("BehaviorPredictor.train requires labeled training data")

        self._model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced")),
        ])
        self._model.fit(X, y)
        self._is_trained = True

        with np.errstate(all="ignore"):
            cv = cross_val_score(self._model, X, y, cv=min(5, len(X)))

        return {
            "samples": len(X),
            "classes": len(set(y)),
            "cv_accuracy": float(np.mean(cv)),
            "cv_std": float(np.std(cv)),
        }

    def predict(self, features: Dict[str, float]) -> Dict[str, Any]:
        if not self._is_trained or self._model is None:
            return self._heuristic_predict(features)

        X = [self._vectorize(features)]
        probs = self._model.predict_proba(X)[0]
        classes = list(self._model.classes_)
        prob_map = {cls: round(float(prob), 4) for cls, prob in zip(classes, probs)}
        predicted = classes[int(np.argmax(probs))]
        engagement = 1.0 - prob_map.get("leave", 0.0)
        escalation = prob_map.get("fight", 0.0) + prob_map.get("leave", 0.0) * 0.5
        return {
            "predicted_action": predicted,
            "action_probabilities": prob_map,
            "engagement_score": round(min(engagement, 1.0), 4),
            "escalation_risk": round(min(escalation, 1.0), 4),
        }

    def save(self, path: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            pickle.dump({"model": self._model, "trained": self._is_trained, "weights": self._weights}, f)

    @classmethod
    def load(cls, path: str) -> "BehaviorPredictor":
        p = Path(path)
        obj = cls()
        with open(p, "rb") as f:
            payload = pickle.load(f)
        obj._model = payload.get("model")
        obj._is_trained = payload.get("trained", False)
        obj._weights = payload.get("weights", obj._weights)
        return obj

    def export_onnx(self, path: str) -> int:
        if not self._is_trained or self._model is None:
            raise ValueError("Model must be trained before ONNX export")
        try:
            from skl2onnx import convert_sklearn
            from skl2onnx.common.data_types import FloatTensorType

            onnx_model = convert_sklearn(
                self._model,
                initial_types=[("features", FloatTensorType([None, 6]))],
                target_opset=15,
            )
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "wb") as f:
                f.write(onnx_model.SerializeToString())
            return p.stat().st_size
        except Exception:
            return 0

    def get_stats(self) -> Dict[str, Any]:
        return {
            "model": "BehaviorPredictor",
            "actions": self.ACTIONS,
            "features": len(self.FEATURE_NAMES),
            "footprint_kb": 15,
            "is_trained": self._is_trained,
        }
