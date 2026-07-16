#!/usr/bin/env python3
"""
LootBalancer — ML Swarm Micro-Model #5
Balances item/reward distribution for NPC merchants and quest givers.
Uses a learned tier predictor when trained, otherwise deterministic rules.
"""

from __future__ import annotations

import pickle
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class LootBalancer:
    RARITY_TIERS = {
        "common": {"weight": 0.50, "value_mult": 1.0},
        "uncommon": {"weight": 0.25, "value_mult": 2.0},
        "rare": {"weight": 0.15, "value_mult": 5.0},
        "epic": {"weight": 0.07, "value_mult": 15.0},
        "legendary": {"weight": 0.03, "value_mult": 50.0},
    }

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)
        self._model: Optional[Pipeline] = None
        self._is_trained = False

    def _features(self, player_level: float, loyalty_score: float, quest_difficulty: float, merchant_generosity: float, economy_inflation: float) -> np.ndarray:
        return np.array([player_level / 30.0, loyalty_score, quest_difficulty, merchant_generosity, economy_inflation, 1.0], dtype=np.float32)

    def train(self, training_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        X = []
        y = []
        for row in training_data:
            if "tier" not in row:
                continue
            X.append(self._features(
                row.get("player_level", 1),
                row.get("loyalty", 0) / 10.0,
                min(row.get("quest_completions", 0) / 20.0, 1.0),
                row.get("merchant_generosity", 0.5),
                row.get("economy_inflation", 0.0),
            ))
            y.append(row["tier"])
        if not X:
            raise ValueError("LootBalancer.train requires labeled training data")

        self._model = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced")),
        ])
        self._model.fit(X, y)
        self._is_trained = True
        cv = cross_val_score(self._model, X, y, cv=min(5, len(X)))
        return {"samples": len(X), "classes": len(set(y)), "cv_accuracy": float(np.mean(cv)), "cv_std": float(np.std(cv))}

    def calculate_reward_tier(self, player_level: float = 1.0, loyalty_score: float = 0.5, quest_difficulty: float = 0.5, merchant_generosity: float = 0.5, economy_inflation: float = 0.0) -> Dict[str, Any]:
        if self._is_trained and self._model is not None:
            feats = [self._features(player_level, loyalty_score, quest_difficulty, merchant_generosity, economy_inflation)]
            probs = self._model.predict_proba(feats)[0]
            classes = list(self._model.classes_)
            prob_map = {cls: round(float(prob), 4) for cls, prob in zip(classes, probs)}
            tier = classes[int(np.argmax(probs))]
            value_mod = self.RARITY_TIERS[tier]["value_mult"] * (1.0 + merchant_generosity * 0.3) * (1.0 - economy_inflation * 0.2)
            qty_bonus = 1 if loyalty_score > 0.7 else 2 if loyalty_score > 0.9 else 0
            return {"tier": tier, "value_modifier": round(value_mod, 2), "quantity_bonus": qty_bonus, "probabilities": prob_map}

        adjusted = {}
        for tier, info in self.RARITY_TIERS.items():
            base_w = info["weight"]
            boost = (player_level * 0.3 + loyalty_score * 0.2 + quest_difficulty * 0.3 + merchant_generosity * 0.2)
            adjusted[tier] = base_w * (1.0 + boost) if tier in ("rare", "epic", "legendary") else base_w * (1.0 - boost * 0.3)
        total = sum(adjusted.values())
        probs = {k: round(v / total, 4) for k, v in adjusted.items()}
        roll = self._rng.random()
        cumulative = 0.0
        selected_tier = "common"
        for tier, prob in probs.items():
            cumulative += prob
            if roll <= cumulative:
                selected_tier = tier
                break
        value_mod = self.RARITY_TIERS[selected_tier]["value_mult"]
        value_mod *= (1.0 + merchant_generosity * 0.3)
        value_mod *= (1.0 - economy_inflation * 0.2)
        qty_bonus = 0
        if loyalty_score > 0.7:
            qty_bonus = 1
        if loyalty_score > 0.9:
            qty_bonus = 2
        return {"tier": selected_tier, "value_modifier": round(value_mod, 2), "quantity_bonus": qty_bonus, "probabilities": probs}

    def price_adjustment(self, base_price: float, loyalty_score: float = 0.5, merchant_generosity: float = 0.5, is_buying: bool = True) -> Dict[str, Any]:
        discount = 0.0
        if loyalty_score > 0.3:
            discount += (loyalty_score - 0.3) * 0.2
        discount += (merchant_generosity - 0.5) * 0.2
        if not is_buying:
            discount = -abs(discount) * 0.5
        discount = max(-0.3, min(discount, 0.25))
        adjusted = base_price * (1.0 - discount)
        reason = "standard pricing"
        if discount > 0.1:
            reason = "loyal customer discount"
        elif discount > 0.05:
            reason = "friendly pricing"
        elif discount < -0.05:
            reason = "tough bargaining"
        return {"adjusted_price": round(adjusted, 2), "discount_pct": round(discount * 100, 1), "reason": reason}

    def save(self, path: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            pickle.dump({"model": self._model, "trained": self._is_trained}, f)

    @classmethod
    def load(cls, path: str) -> "LootBalancer":
        obj = cls()
        with open(Path(path), "rb") as f:
            payload = pickle.load(f)
        obj._model = payload.get("model")
        obj._is_trained = payload.get("trained", False)
        return obj

    def export_onnx(self, path: str) -> int:
        if not self._is_trained or self._model is None:
            return 0
        try:
            from skl2onnx import convert_sklearn
            from skl2onnx.common.data_types import FloatTensorType
            onnx_model = convert_sklearn(self._model, initial_types=[("features", FloatTensorType([None, 6]))], target_opset=15)
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "wb") as f:
                f.write(onnx_model.SerializeToString())
            return p.stat().st_size
        except Exception:
            return 0

    def get_stats(self) -> Dict[str, Any]:
        return {"model": "LootBalancer", "rarity_tiers": list(self.RARITY_TIERS.keys()), "footprint_kb": 8, "is_trained": self._is_trained}
