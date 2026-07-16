"""
Synthesus 2.0 — World Systems: ML Swarm Expansion (Phase 11D)
"Intelligence is in selection, not generation"

New specialized ML models for the world systems:

Model 3: Demand Predictor
  - Predicts future demand for resources based on trends
  - Input: recent price/supply/demand history
  - Output: predicted demand shift (up/down/stable)
  - ~30 KB sklearn, <0.5ms inference

Model 4: Route Risk Scorer
  - Scores trade route risk based on world conditions
  - Input: weather, events, route distance, recent disruptions
  - Output: risk score 0-1
  - ~25 KB sklearn, <0.3ms inference

Model 5: Rumor Propagation Classifier
  - Determines how rumors spread between NPCs
  - Input: rumor content features, NPC social graph
  - Output: spread probability, distortion level
  - ~35 KB sklearn, <0.4ms inference

Model 6: Topic Classifier
  - Classifies world events into topic categories for NPC awareness
  - Input: event description text
  - Output: topic category (economy, combat, weather, social, political)
  - ~40 KB sklearn, <0.3ms inference

Model 7: Emotion Predictor
  - Predicts NPC emotional reaction to world events
  - Input: NPC personality features + event features
  - Output: emotion vector (joy, anger, fear, sadness, surprise)
  - ~35 KB sklearn, <0.4ms inference

Total swarm after expansion: 7 models, ~215 KB combined, all <0.5ms inference.
"""

from __future__ import annotations

import json
import os
import pickle
import re
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler


# ══════════════════════════════════════════════════
# Model 3: Demand Predictor
# ══════════════════════════════════════════════════

_DEMAND_TRAINING_DATA = [
    # (supply_trend, demand_trend, price_trend, scarcity, event_active) → shift
    # Supply falling + demand rising → demand increases
    ([-0.5, 0.3, 0.4, 0.7, 1], "increase"),
    ([-0.3, 0.5, 0.6, 0.8, 1], "increase"),
    ([-0.7, 0.2, 0.3, 0.9, 0], "increase"),
    ([-0.4, 0.4, 0.5, 0.6, 1], "increase"),
    ([-0.6, 0.6, 0.7, 0.85, 1], "increase"),
    ([-0.2, 0.1, 0.2, 0.5, 1], "increase"),
    ([-0.8, 0.3, 0.8, 0.95, 0], "increase"),
    ([-0.1, 0.7, 0.4, 0.4, 1], "increase"),
    # Supply rising + demand falling → demand decreases
    ([0.5, -0.3, -0.4, 0.2, 0], "decrease"),
    ([0.3, -0.5, -0.3, 0.15, 0], "decrease"),
    ([0.7, -0.2, -0.5, 0.1, 0], "decrease"),
    ([0.4, -0.4, -0.6, 0.25, 0], "decrease"),
    ([0.6, -0.6, -0.4, 0.3, 1], "decrease"),
    ([0.8, -0.1, -0.7, 0.05, 0], "decrease"),
    ([0.2, -0.3, -0.2, 0.35, 0], "decrease"),
    ([0.9, -0.4, -0.8, 0.1, 0], "decrease"),
    # Balanced → stable
    ([0.0, 0.0, 0.0, 0.5, 0], "stable"),
    ([0.1, -0.1, 0.05, 0.45, 0], "stable"),
    ([-0.1, 0.1, -0.05, 0.55, 0], "stable"),
    ([0.05, 0.05, 0.0, 0.5, 0], "stable"),
    ([-0.05, -0.05, 0.1, 0.48, 0], "stable"),
    ([0.0, 0.0, -0.1, 0.52, 0], "stable"),
    ([0.1, 0.0, 0.0, 0.5, 0], "stable"),
    ([0.0, 0.1, 0.0, 0.47, 0], "stable"),
    # Event-driven spikes
    ([-0.1, 0.8, 0.9, 0.3, 1], "increase"),
    ([0.0, 0.6, 0.7, 0.4, 1], "increase"),
    ([0.3, -0.7, -0.5, 0.2, 1], "decrease"),
    ([0.1, -0.5, -0.3, 0.3, 1], "decrease"),
]


class DemandPredictor:
    """
    ML Model 3: Predicts demand shifts from economic indicators.

    Features: [supply_trend, demand_trend, price_trend, scarcity, event_active]
    Labels: "increase", "decrease", "stable"
    """

    def __init__(self, model_dir: Optional[str] = None):
        self._model_dir = Path(model_dir) if model_dir else None
        self._pipeline: Optional[Pipeline] = None
        self._trained = False

    def train(self, extra_data: Optional[List[Tuple]] = None) -> Dict[str, Any]:
        """Train the demand predictor."""
        data = list(_DEMAND_TRAINING_DATA)
        if extra_data:
            data.extend(extra_data)

        X = np.array([d[0] for d in data])
        y = [d[1] for d in data]

        self._pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=500, random_state=42)),
        ])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            scores = cross_val_score(self._pipeline, X, y, cv=3,
                                     scoring="accuracy")
            self._pipeline.fit(X, y)

        self._trained = True

        if self._model_dir:
            self._model_dir.mkdir(parents=True, exist_ok=True)
            with open(self._model_dir / "demand_predictor.pkl", "wb") as f:
                pickle.dump(self._pipeline, f)

        return {
            "model": "demand_predictor",
            "samples": len(data),
            "cv_accuracy": round(float(np.mean(scores)), 4),
            "classes": list(self._pipeline.classes_),
        }

    def predict(
        self,
        supply_trend: float,
        demand_trend: float,
        price_trend: float,
        scarcity: float,
        event_active: bool,
    ) -> Dict[str, Any]:
        """
        Predict demand shift.

        Args:
            supply_trend: -1 to 1, negative = falling
            demand_trend: -1 to 1, negative = falling
            price_trend: -1 to 1, negative = falling
            scarcity: 0 to 1, how scarce (0 = abundant, 1 = critically scarce)
            event_active: whether an economic event is happening

        Returns:
            {"prediction": "increase"|"decrease"|"stable",
             "confidence": float, "probabilities": dict}
        """
        if not self._trained:
            self.train()

        features = np.array([[supply_trend, demand_trend, price_trend,
                               scarcity, float(event_active)]])
        prediction = self._pipeline.predict(features)[0]
        probs = self._pipeline.predict_proba(features)[0]

        return {
            "prediction": prediction,
            "confidence": round(float(max(probs)), 4),
            "probabilities": {
                cls: round(float(p), 4)
                for cls, p in zip(self._pipeline.classes_, probs)
            },
        }


# ══════════════════════════════════════════════════
# Model 4: Route Risk Scorer
# ══════════════════════════════════════════════════

_ROUTE_RISK_TRAINING_DATA = [
    # (distance, weather_severity, recent_disruptions, bandit_activity, terrain_difficulty) → risk_label
    # Low risk
    ([1.0, 0.0, 0, 0.0, 0.2], "low"),
    ([1.5, 0.1, 0, 0.1, 0.3], "low"),
    ([2.0, 0.0, 0, 0.0, 0.1], "low"),
    ([1.0, 0.2, 0, 0.0, 0.2], "low"),
    ([0.5, 0.0, 0, 0.1, 0.1], "low"),
    ([1.5, 0.0, 1, 0.0, 0.2], "low"),
    ([2.0, 0.1, 0, 0.05, 0.3], "low"),
    ([1.0, 0.15, 0, 0.0, 0.15], "low"),
    # Medium risk
    ([3.0, 0.3, 1, 0.3, 0.5], "medium"),
    ([2.5, 0.4, 0, 0.2, 0.4], "medium"),
    ([4.0, 0.2, 1, 0.1, 0.6], "medium"),
    ([3.0, 0.5, 0, 0.3, 0.3], "medium"),
    ([2.0, 0.3, 2, 0.2, 0.5], "medium"),
    ([3.5, 0.1, 1, 0.4, 0.4], "medium"),
    ([2.5, 0.4, 1, 0.15, 0.5], "medium"),
    ([3.0, 0.3, 0, 0.25, 0.45], "medium"),
    # High risk
    ([5.0, 0.7, 3, 0.6, 0.8], "high"),
    ([4.0, 0.8, 2, 0.7, 0.7], "high"),
    ([6.0, 0.5, 2, 0.5, 0.9], "high"),
    ([3.0, 0.9, 3, 0.8, 0.6], "high"),
    ([5.0, 0.6, 1, 0.7, 0.8], "high"),
    ([4.5, 0.7, 2, 0.6, 0.7], "high"),
    ([7.0, 0.4, 3, 0.5, 0.9], "high"),
    ([3.5, 0.8, 2, 0.9, 0.7], "high"),
    # Critical risk
    ([8.0, 0.9, 5, 0.9, 0.9], "critical"),
    ([6.0, 1.0, 4, 0.8, 1.0], "critical"),
    ([7.0, 0.8, 3, 1.0, 0.8], "critical"),
    ([5.0, 1.0, 4, 0.9, 0.9], "critical"),
    ([9.0, 0.7, 5, 0.7, 1.0], "critical"),
    ([6.0, 0.9, 4, 0.95, 0.85], "critical"),
]


class RouteRiskScorer:
    """
    ML Model 4: Scores trade route risk.

    Features: [distance, weather_severity, recent_disruptions, bandit_activity, terrain_difficulty]
    Labels: "low", "medium", "high", "critical"
    """

    def __init__(self, model_dir: Optional[str] = None):
        self._model_dir = Path(model_dir) if model_dir else None
        self._pipeline: Optional[Pipeline] = None
        self._trained = False

    def train(self, extra_data: Optional[List[Tuple]] = None) -> Dict[str, Any]:
        data = list(_ROUTE_RISK_TRAINING_DATA)
        if extra_data:
            data.extend(extra_data)

        X = np.array([d[0] for d in data])
        y = [d[1] for d in data]

        self._pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=500, random_state=42)),
        ])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            scores = cross_val_score(self._pipeline, X, y, cv=3, scoring="accuracy")
            self._pipeline.fit(X, y)

        self._trained = True

        if self._model_dir:
            self._model_dir.mkdir(parents=True, exist_ok=True)
            with open(self._model_dir / "route_risk_scorer.pkl", "wb") as f:
                pickle.dump(self._pipeline, f)

        return {
            "model": "route_risk_scorer",
            "samples": len(data),
            "cv_accuracy": round(float(np.mean(scores)), 4),
            "classes": list(self._pipeline.classes_),
        }

    def predict(
        self,
        distance: float,
        weather_severity: float,
        recent_disruptions: int,
        bandit_activity: float,
        terrain_difficulty: float,
    ) -> Dict[str, Any]:
        if not self._trained:
            self.train()

        features = np.array([[distance, weather_severity, recent_disruptions,
                               bandit_activity, terrain_difficulty]])
        prediction = self._pipeline.predict(features)[0]
        probs = self._pipeline.predict_proba(features)[0]

        return {
            "risk_level": prediction,
            "confidence": round(float(max(probs)), 4),
            "probabilities": {
                cls: round(float(p), 4)
                for cls, p in zip(self._pipeline.classes_, probs)
            },
        }


# ══════════════════════════════════════════════════
# Model 5: Rumor Propagation Classifier
# ══════════════════════════════════════════════════

_RUMOR_TRAINING_DATA = [
    # (sensationalism, source_trust, relevance, social_connections, time_freshness) → spread
    # Will spread
    ([0.8, 0.7, 0.9, 5, 0.9], "spread"),
    ([0.9, 0.5, 0.8, 8, 1.0], "spread"),
    ([0.7, 0.8, 0.7, 6, 0.8], "spread"),
    ([0.6, 0.9, 0.9, 4, 0.7], "spread"),
    ([0.9, 0.6, 1.0, 7, 0.9], "spread"),
    ([0.8, 0.4, 0.8, 9, 1.0], "spread"),
    ([0.7, 0.7, 0.6, 6, 0.85], "spread"),
    ([0.85, 0.5, 0.75, 5, 0.95], "spread"),
    # Will fade
    ([0.2, 0.3, 0.2, 1, 0.1], "fade"),
    ([0.1, 0.2, 0.3, 2, 0.2], "fade"),
    ([0.3, 0.1, 0.1, 1, 0.3], "fade"),
    ([0.15, 0.4, 0.2, 2, 0.15], "fade"),
    ([0.2, 0.2, 0.15, 1, 0.1], "fade"),
    ([0.1, 0.3, 0.25, 3, 0.2], "fade"),
    ([0.25, 0.15, 0.1, 1, 0.25], "fade"),
    ([0.3, 0.2, 0.3, 2, 0.1], "fade"),
    # Will distort (spreads but mutates)
    ([0.6, 0.3, 0.5, 4, 0.5], "distort"),
    ([0.5, 0.2, 0.6, 5, 0.6], "distort"),
    ([0.7, 0.3, 0.4, 3, 0.4], "distort"),
    ([0.4, 0.4, 0.5, 6, 0.5], "distort"),
    ([0.6, 0.2, 0.7, 4, 0.6], "distort"),
    ([0.5, 0.3, 0.4, 5, 0.45], "distort"),
    ([0.65, 0.25, 0.55, 3, 0.55], "distort"),
    ([0.55, 0.35, 0.5, 4, 0.5], "distort"),
]


class RumorPropagation:
    """
    ML Model 5: Predicts how rumors spread through the NPC social graph.

    Features: [sensationalism, source_trust, relevance, social_connections, time_freshness]
    Labels: "spread" (intact), "distort" (mutates), "fade" (dies out)
    """

    def __init__(self, model_dir: Optional[str] = None):
        self._model_dir = Path(model_dir) if model_dir else None
        self._pipeline: Optional[Pipeline] = None
        self._trained = False

    def train(self, extra_data: Optional[List[Tuple]] = None) -> Dict[str, Any]:
        data = list(_RUMOR_TRAINING_DATA)
        if extra_data:
            data.extend(extra_data)

        X = np.array([d[0] for d in data])
        y = [d[1] for d in data]

        self._pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=500, random_state=42)),
        ])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            scores = cross_val_score(self._pipeline, X, y, cv=3, scoring="accuracy")
            self._pipeline.fit(X, y)

        self._trained = True

        if self._model_dir:
            self._model_dir.mkdir(parents=True, exist_ok=True)
            with open(self._model_dir / "rumor_propagation.pkl", "wb") as f:
                pickle.dump(self._pipeline, f)

        return {
            "model": "rumor_propagation",
            "samples": len(data),
            "cv_accuracy": round(float(np.mean(scores)), 4),
            "classes": list(self._pipeline.classes_),
        }

    def predict(
        self,
        sensationalism: float,
        source_trust: float,
        relevance: float,
        social_connections: int,
        time_freshness: float,
    ) -> Dict[str, Any]:
        if not self._trained:
            self.train()

        features = np.array([[sensationalism, source_trust, relevance,
                               social_connections, time_freshness]])
        prediction = self._pipeline.predict(features)[0]
        probs = self._pipeline.predict_proba(features)[0]

        return {
            "outcome": prediction,
            "confidence": round(float(max(probs)), 4),
            "probabilities": {
                cls: round(float(p), 4)
                for cls, p in zip(self._pipeline.classes_, probs)
            },
        }


# ══════════════════════════════════════════════════
# Model 6: Topic Classifier (text-based)
# ══════════════════════════════════════════════════

_TOPIC_TRAINING_DATA = [
    # Economy topics
    ("prices are rising in the market", "economy"),
    ("the merchant guild raised taxes", "economy"),
    ("trade route disrupted by bandits", "economy"),
    ("wheat shortage causing bread prices to spike", "economy"),
    ("new mining operation discovered iron deposits", "economy"),
    ("surplus of goods flooding the market", "economy"),
    ("the blacksmith raised his prices", "economy"),
    ("caravan from the south brought luxury goods", "economy"),
    ("gold coin devaluation rumored", "economy"),
    ("harvest season yielded record crops", "economy"),
    ("import tariffs increased on foreign goods", "economy"),
    ("local baker went out of business", "economy"),
    # Combat topics
    ("bandits attacked the northern road", "combat"),
    ("the guard captain is recruiting soldiers", "combat"),
    ("war brewing between rival kingdoms", "combat"),
    ("monster sighting near the forest", "combat"),
    ("the arena is hosting a tournament", "combat"),
    ("patrol found orc tracks near the village", "combat"),
    ("weapons shipment stolen from the armory", "combat"),
    ("mercenaries spotted heading east", "combat"),
    ("dragon spotted near the mountain pass", "combat"),
    ("militia training increased due to threats", "combat"),
    ("raid on the eastern settlement last night", "combat"),
    ("siege weapons being constructed at the fort", "combat"),
    # Weather topics
    ("heavy storm approaching from the west", "weather"),
    ("drought affecting the farmlands", "weather"),
    ("flooding in the river valley", "weather"),
    ("snow blocking the mountain pass", "weather"),
    ("clear skies expected all week", "weather"),
    ("fog making travel dangerous", "weather"),
    ("lightning struck the old tower", "weather"),
    ("harvest threatened by early frost", "weather"),
    ("heat wave causing water shortages", "weather"),
    ("winds too strong for sailing today", "weather"),
    ("rain finally ended the dry season", "weather"),
    ("tornado watch issued for the plains", "weather"),
    # Social topics
    ("the mayor's daughter is getting married", "social"),
    ("festival preparations underway", "social"),
    ("new family moved into the old house", "social"),
    ("tavern brawl broke out last night", "social"),
    ("the healer took on a new apprentice", "social"),
    ("rumors about the innkeeper's past", "social"),
    ("church announced a new holiday", "social"),
    ("local hero returned from adventure", "social"),
    ("mysterious stranger arrived at dawn", "social"),
    ("the elder called a town meeting", "social"),
    ("children playing near the ruins again", "social"),
    ("musician performing at the square tonight", "social"),
    # Political topics
    ("the king issued a new decree", "political"),
    ("tax collectors seen heading this way", "political"),
    ("border dispute with neighboring territory", "political"),
    ("new laws restricting magic use", "political"),
    ("the council voted on the trade agreement", "political"),
    ("ambassador from the east arrived", "political"),
    ("rebellion rumors in the southern provinces", "political"),
    ("noble families feuding over inheritance", "political"),
    ("election for new guild master approaching", "political"),
    ("sanctions imposed on rival kingdom", "political"),
    ("treaty signed ending border conflict", "political"),
    ("governor replaced by royal decree", "political"),
]


class TopicClassifier:
    """
    ML Model 6: Classifies world event descriptions into topic categories.

    Categories: economy, combat, weather, social, political
    """

    def __init__(self, model_dir: Optional[str] = None):
        self._model_dir = Path(model_dir) if model_dir else None
        self._pipeline: Optional[Pipeline] = None
        self._trained = False

    def train(self, extra_data: Optional[List[Tuple]] = None) -> Dict[str, Any]:
        data = list(_TOPIC_TRAINING_DATA)
        if extra_data:
            data.extend(extra_data)

        texts = [d[0] for d in data]
        labels = [d[1] for d in data]

        self._pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                max_features=500,
                ngram_range=(1, 2),
                analyzer="word",
            )),
            ("clf", LogisticRegression(max_iter=500, random_state=42)),
        ])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            scores = cross_val_score(self._pipeline, texts, labels, cv=3,
                                     scoring="accuracy")
            self._pipeline.fit(texts, labels)

        self._trained = True

        if self._model_dir:
            self._model_dir.mkdir(parents=True, exist_ok=True)
            with open(self._model_dir / "topic_classifier.pkl", "wb") as f:
                pickle.dump(self._pipeline, f)

        return {
            "model": "topic_classifier",
            "samples": len(data),
            "cv_accuracy": round(float(np.mean(scores)), 4),
            "classes": list(self._pipeline.classes_),
        }

    def predict(self, text: str) -> Dict[str, Any]:
        if not self._trained:
            self.train()

        prediction = self._pipeline.predict([text])[0]
        probs = self._pipeline.predict_proba([text])[0]

        return {
            "topic": prediction,
            "confidence": round(float(max(probs)), 4),
            "probabilities": {
                cls: round(float(p), 4)
                for cls, p in zip(self._pipeline.classes_, probs)
            },
        }


# ══════════════════════════════════════════════════
# Model 7: Emotion Predictor
# ══════════════════════════════════════════════════

_EMOTION_TRAINING_DATA = [
    # (personality_warmth, personality_bravery, personality_greed,
    #  event_severity, event_is_positive, event_is_threatening) → emotion
    # Joy
    ([0.8, 0.5, 0.2, 0.3, 1, 0], "joy"),
    ([0.9, 0.3, 0.1, 0.5, 1, 0], "joy"),
    ([0.7, 0.6, 0.3, 0.2, 1, 0], "joy"),
    ([0.6, 0.4, 0.2, 0.4, 1, 0], "joy"),
    ([0.85, 0.5, 0.15, 0.1, 1, 0], "joy"),
    ([0.75, 0.3, 0.25, 0.3, 1, 0], "joy"),
    # Anger
    ([0.3, 0.7, 0.5, 0.7, 0, 0], "anger"),
    ([0.2, 0.8, 0.6, 0.8, 0, 1], "anger"),
    ([0.4, 0.6, 0.7, 0.6, 0, 0], "anger"),
    ([0.1, 0.9, 0.4, 0.9, 0, 1], "anger"),
    ([0.3, 0.75, 0.55, 0.7, 0, 0], "anger"),
    ([0.25, 0.8, 0.5, 0.65, 0, 1], "anger"),
    # Fear
    ([0.5, 0.1, 0.3, 0.8, 0, 1], "fear"),
    ([0.4, 0.2, 0.2, 0.9, 0, 1], "fear"),
    ([0.6, 0.1, 0.4, 0.7, 0, 1], "fear"),
    ([0.3, 0.15, 0.3, 0.85, 0, 1], "fear"),
    ([0.5, 0.2, 0.25, 0.75, 0, 1], "fear"),
    ([0.45, 0.1, 0.35, 0.9, 0, 1], "fear"),
    # Sadness
    ([0.7, 0.3, 0.2, 0.6, 0, 0], "sadness"),
    ([0.8, 0.2, 0.1, 0.7, 0, 0], "sadness"),
    ([0.6, 0.4, 0.3, 0.5, 0, 0], "sadness"),
    ([0.75, 0.25, 0.15, 0.8, 0, 0], "sadness"),
    ([0.65, 0.3, 0.2, 0.55, 0, 0], "sadness"),
    ([0.8, 0.2, 0.15, 0.65, 0, 0], "sadness"),
    # Surprise
    ([0.5, 0.5, 0.5, 0.9, 1, 0], "surprise"),
    ([0.6, 0.4, 0.3, 0.8, 0, 0], "surprise"),
    ([0.4, 0.6, 0.4, 0.95, 1, 0], "surprise"),
    ([0.5, 0.5, 0.5, 1.0, 0, 1], "surprise"),
    ([0.55, 0.45, 0.4, 0.85, 1, 0], "surprise"),
    ([0.45, 0.55, 0.35, 0.9, 0, 0], "surprise"),
]


class EmotionPredictor:
    """
    ML Model 7: Predicts NPC emotional reaction to world events.

    Features: [personality_warmth, personality_bravery, personality_greed,
               event_severity, event_is_positive, event_is_threatening]
    Labels: "joy", "anger", "fear", "sadness", "surprise"
    """

    def __init__(self, model_dir: Optional[str] = None):
        self._model_dir = Path(model_dir) if model_dir else None
        self._pipeline: Optional[Pipeline] = None
        self._trained = False

    def train(self, extra_data: Optional[List[Tuple]] = None) -> Dict[str, Any]:
        data = list(_EMOTION_TRAINING_DATA)
        if extra_data:
            data.extend(extra_data)

        X = np.array([d[0] for d in data])
        y = [d[1] for d in data]

        self._pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=500, random_state=42)),
        ])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            scores = cross_val_score(self._pipeline, X, y, cv=3, scoring="accuracy")
            self._pipeline.fit(X, y)

        self._trained = True

        if self._model_dir:
            self._model_dir.mkdir(parents=True, exist_ok=True)
            with open(self._model_dir / "emotion_predictor.pkl", "wb") as f:
                pickle.dump(self._pipeline, f)

        return {
            "model": "emotion_predictor",
            "samples": len(data),
            "cv_accuracy": round(float(np.mean(scores)), 4),
            "classes": list(self._pipeline.classes_),
        }

    def predict(
        self,
        personality_warmth: float,
        personality_bravery: float,
        personality_greed: float,
        event_severity: float,
        event_is_positive: bool,
        event_is_threatening: bool,
    ) -> Dict[str, Any]:
        if not self._trained:
            self.train()

        features = np.array([[personality_warmth, personality_bravery,
                               personality_greed, event_severity,
                               float(event_is_positive),
                               float(event_is_threatening)]])
        prediction = self._pipeline.predict(features)[0]
        probs = self._pipeline.predict_proba(features)[0]

        return {
            "emotion": prediction,
            "confidence": round(float(max(probs)), 4),
            "probabilities": {
                cls: round(float(p), 4)
                for cls, p in zip(self._pipeline.classes_, probs)
            },
        }


# ══════════════════════════════════════════════════
# ML Swarm Manager (coordinates all models)
# ══════════════════════════════════════════════════

class MLSwarmManager:
    """
    Coordinates the full ML model swarm.

    Current swarm:
    - Model 1: Intent Classifier (ml/intent_classifier.py)
    - Model 2: Sentiment Analyzer (ml/sentiment_analyzer.py)
    - Model 3: Demand Predictor (this file)
    - Model 4: Route Risk Scorer (this file)
    - Model 5: Rumor Propagation (this file)
    - Model 6: Topic Classifier (this file)
    - Model 7: Emotion Predictor (this file)

    All models: ~215 KB combined, <0.5ms inference each, zero GPU.
    """

    def __init__(self, model_dir: Optional[str] = None):
        self._model_dir = model_dir
        self.demand_predictor = DemandPredictor(model_dir)
        self.route_risk_scorer = RouteRiskScorer(model_dir)
        self.rumor_propagation = RumorPropagation(model_dir)
        self.topic_classifier = TopicClassifier(model_dir)
        self.emotion_predictor = EmotionPredictor(model_dir)
        self._training_results: Dict[str, Any] = {}

    def train_all(self) -> Dict[str, Any]:
        """Train all models in the swarm."""
        results = {}
        results["demand_predictor"] = self.demand_predictor.train()
        results["route_risk_scorer"] = self.route_risk_scorer.train()
        results["rumor_propagation"] = self.rumor_propagation.train()
        results["topic_classifier"] = self.topic_classifier.train()
        results["emotion_predictor"] = self.emotion_predictor.train()
        self._training_results = results
        return results

    def get_swarm_status(self) -> Dict[str, Any]:
        """Get status of all models."""
        return {
            "total_models": 7,  # 2 existing + 5 new
            "new_models": {
                "demand_predictor": self.demand_predictor._trained,
                "route_risk_scorer": self.route_risk_scorer._trained,
                "rumor_propagation": self.rumor_propagation._trained,
                "topic_classifier": self.topic_classifier._trained,
                "emotion_predictor": self.emotion_predictor._trained,
            },
            "training_results": self._training_results,
        }
