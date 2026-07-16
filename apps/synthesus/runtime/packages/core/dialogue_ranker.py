#!/usr/bin/env python3
"""
DialogueRanker — ML Swarm Micro-Model #6
Ranks candidate NPC responses by contextual relevance, personality fit, and flow quality.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class DialogueRanker:
    TONE_KEYWORDS = {
        "friendly": ["welcome", "friend", "glad", "happy", "please", "love", "great", "wonderful"],
        "hostile": ["leave", "get out", "fool", "dare", "challenge", "fight", "enemy"],
        "formal": ["greetings", "indeed", "certainly", "shall", "permit", "acknowledge"],
        "casual": ["hey", "yo", "sup", "cool", "yeah", "nah", "gonna", "wanna"],
        "mysterious": ["perhaps", "secrets", "whisper", "shadow", "hidden", "ancient", "unknown"],
        "humorous": ["ha", "joke", "funny", "laugh", "ridiculous", "hilarious"],
    }

    def __init__(self, relevance_weight: float = 0.35, personality_weight: float = 0.25, flow_weight: float = 0.20, variety_weight: float = 0.20):
        self.relevance_weight = relevance_weight
        self.personality_weight = personality_weight
        self.flow_weight = flow_weight
        self.variety_weight = variety_weight
        self._ranker: Optional[Pipeline] = None
        self._is_trained = False

    def _features(self, response: str, query: str, personality: Dict[str, float], recent_responses: List[str], context_keywords: List[str]) -> List[float]:
        relevance = self._score_relevance(response, query, context_keywords)
        personality_fit = self._score_personality(response, personality)
        flow = self._score_flow(response, query)
        variety = self._score_variety(response, recent_responses)
        return [relevance, personality_fit, flow, variety]

    def train(self, training_examples: List[Dict[str, Any]]) -> Dict[str, Any]:
        X = []
        y = []
        for ex in training_examples:
            if "query" not in ex or "response" not in ex or "label" not in ex:
                continue
            X.append(self._features(
                ex["response"],
                ex["query"],
                ex.get("personality", {}),
                ex.get("recent_responses", []),
                ex.get("context_keywords", []),
            ))
            y.append(int(ex["label"]))
        if not X:
            raise ValueError("DialogueRanker.train requires labeled training examples")

        self._ranker = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced")),
        ])
        self._ranker.fit(X, y)
        self._is_trained = True
        cv = cross_val_score(self._ranker, X, y, cv=min(5, len(X)))
        return {
            "samples": len(X),
            "classes": len(set(y)),
            "cv_accuracy": float(np.mean(cv)),
            "cv_std": float(np.std(cv)),
        }

    def rank(self, candidates: List[str], query: str = "", personality: Optional[Dict[str, float]] = None, recent_responses: Optional[List[str]] = None, context_keywords: Optional[List[str]] = None) -> List[Tuple[str, float]]:
        if not candidates:
            return []
        personality = personality or {}
        recent_responses = recent_responses or []
        context_keywords = context_keywords or []

        scored = []
        for resp in candidates:
            relevance = self._score_relevance(resp, query, context_keywords)
            personality_fit = self._score_personality(resp, personality)
            flow = self._score_flow(resp, query)
            variety = self._score_variety(resp, recent_responses)
            composite = relevance * self.relevance_weight + personality_fit * self.personality_weight + flow * self.flow_weight + variety * self.variety_weight
            if self._is_trained and self._ranker is not None:
                features = self._features(resp, query, personality, recent_responses, context_keywords)
                prob = float(self._ranker.predict_proba([features])[0][1])
                composite = 0.65 * composite + 0.35 * prob
            scored.append((resp, round(float(composite), 4)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _score_relevance(self, response: str, query: str, context_keywords: List[str]) -> float:
        if not query:
            return 0.5
        resp_words = set(response.lower().split())
        query_words = set(query.lower().split())
        overlap = len(resp_words & query_words)
        base_score = min(overlap / max(len(query_words), 1), 1.0)
        if context_keywords:
            ctx_set = set(w.lower() for w in context_keywords)
            ctx_overlap = len(resp_words & ctx_set)
            base_score += min(ctx_overlap / max(len(ctx_set), 1), 0.5) * 0.3
        return min(base_score, 1.0)

    def _score_personality(self, response: str, personality: Dict[str, float]) -> float:
        if not personality:
            return 0.5
        resp_lower = response.lower()
        score = 0.5
        friendliness = personality.get("friendliness", 0.5)
        formality = personality.get("formality", 0.5)
        aggression = personality.get("aggression", 0.1)
        friendly_hits = sum(1 for kw in self.TONE_KEYWORDS["friendly"] if kw in resp_lower)
        hostile_hits = sum(1 for kw in self.TONE_KEYWORDS["hostile"] if kw in resp_lower)
        if friendliness > 0.6:
            score += friendly_hits * 0.1
            score -= hostile_hits * 0.15
        elif aggression > 0.5:
            score += hostile_hits * 0.1
            score -= friendly_hits * 0.05
        formal_hits = sum(1 for kw in self.TONE_KEYWORDS["formal"] if kw in resp_lower)
        casual_hits = sum(1 for kw in self.TONE_KEYWORDS["casual"] if kw in resp_lower)
        if formality > 0.6:
            score += formal_hits * 0.08
            score -= casual_hits * 0.1
        elif formality < 0.4:
            score += casual_hits * 0.08
            score -= formal_hits * 0.1
        return max(0.0, min(score, 1.0))

    def _score_flow(self, response: str, query: str) -> float:
        if not query:
            return 0.5
        is_question = query.strip().endswith("?")
        resp_len = len(response.split())
        if is_question:
            if resp_len < 3:
                return 0.2
            elif resp_len < 8:
                return 0.6
            else:
                return 0.8
        else:
            if resp_len < 15:
                return 0.7
            else:
                return 0.5

    def _score_variety(self, response: str, recent_responses: List[str]) -> float:
        if not recent_responses:
            return 1.0
        resp_lower = response.lower().strip()
        for recent in recent_responses:
            if resp_lower == recent.lower().strip():
                return 0.0
            resp_words = set(resp_lower.split())
            recent_words = set(recent.lower().split())
            if resp_words and recent_words:
                overlap = len(resp_words & recent_words) / len(resp_words)
                if overlap > 0.8:
                    return 0.2
        return 1.0

    def save(self, path: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            pickle.dump({"model": self._ranker, "trained": self._is_trained}, f)

    @classmethod
    def load(cls, path: str) -> "DialogueRanker":
        p = Path(path)
        obj = cls()
        with open(p, "rb") as f:
            payload = pickle.load(f)
        obj._ranker = payload.get("model")
        obj._is_trained = payload.get("trained", False)
        return obj

    def export_onnx(self, path: str) -> int:
        if not self._is_trained or self._ranker is None:
            raise ValueError("Model must be trained before ONNX export")
        try:
            from skl2onnx import convert_sklearn
            from skl2onnx.common.data_types import FloatTensorType
            onnx_model = convert_sklearn(self._ranker, initial_types=[("features", FloatTensorType([None, 4]))], target_opset=15)
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "wb") as f:
                f.write(onnx_model.SerializeToString())
            return p.stat().st_size
        except Exception:
            return 0

    def get_stats(self) -> Dict[str, Any]:
        return {
            "model": "DialogueRanker",
            "scoring_dimensions": ["relevance", "personality", "flow", "variety"],
            "tone_categories": list(self.TONE_KEYWORDS.keys()),
            "footprint_kb": 12,
            "is_trained": self._is_trained,
        }
