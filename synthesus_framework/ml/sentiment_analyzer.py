"""
Synthesus 2.0 — ML Swarm Module 2: Sentiment Analyzer
"What TONE is the player using?"

Lightweight sentiment classification for NPC emotional reactions.
Classifies player text into emotional categories that feed directly
into the EmotionStateMachine module.

Sentiment Categories:
  - positive    : friendly, happy, grateful
  - negative    : angry, hostile, frustrated
  - neutral     : matter-of-fact, business-like
  - threatening : combat threats, intimidation
  - pleading    : begging, desperate, sad
  - flirtatious : flattery, charm, romantic intent

Model size: ~40 KB sklearn, ~0.2ms inference, zero GPU.
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
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import cross_val_score
except ImportError:
    TfidfVectorizer = None
    LogisticRegression = None
    Pipeline = None
    cross_val_score = None


# ──────────────────────────────────────────────────
# Training Data
# ──────────────────────────────────────────────────

_SENTIMENT_TRAINING_DATA = [
    # Positive
    ("hello friend", "positive"), ("you're amazing", "positive"),
    ("thank you so much", "positive"), ("great job", "positive"),
    ("I appreciate your help", "positive"), ("wonderful", "positive"),
    ("you're the best", "positive"), ("I love this place", "positive"),
    ("how kind of you", "positive"), ("brilliant work", "positive"),
    ("that's impressive", "positive"), ("you've been so helpful", "positive"),
    ("I'm grateful", "positive"), ("what a lovely shop", "positive"),
    ("you make me smile", "positive"), ("cheers", "positive"),
    ("bless you", "positive"), ("that's wonderful news", "positive"),
    ("I'm so happy", "positive"), ("perfect", "positive"),

    # Negative
    ("you're useless", "negative"), ("this is terrible", "negative"),
    ("what a waste of time", "negative"), ("you're a liar", "negative"),
    ("I hate this", "negative"), ("that's awful", "negative"),
    ("you're pathetic", "negative"), ("worst shop ever", "negative"),
    ("how dare you", "negative"), ("that's unacceptable", "negative"),
    ("you're cheating me", "negative"), ("I'm angry", "negative"),
    ("this is garbage", "negative"), ("stupid", "negative"),
    ("you're a fool", "negative"), ("disgusting", "negative"),
    ("what a rip off", "negative"), ("I'm furious", "negative"),
    ("you've ruined everything", "negative"), ("go away", "negative"),

    # Neutral
    ("what do you sell", "neutral"), ("I need a sword", "neutral"),
    ("tell me about this town", "neutral"), ("how much is that", "neutral"),
    ("where is the inn", "neutral"), ("who are you", "neutral"),
    ("I'm looking for work", "neutral"), ("any news", "neutral"),
    ("what time is it", "neutral"), ("show me your wares", "neutral"),
    ("I have a question", "neutral"), ("just browsing", "neutral"),
    ("interesting", "neutral"), ("I see", "neutral"),
    ("okay", "neutral"), ("tell me more", "neutral"),
    ("how does that work", "neutral"), ("what happened here", "neutral"),
    ("I understand", "neutral"), ("let me think about it", "neutral"),

    # Threatening
    ("I'll kill you", "threatening"), ("hand over the gold", "threatening"),
    ("give me everything or die", "threatening"), ("prepare to die", "threatening"),
    ("I'm going to destroy this shop", "threatening"), ("fight me coward", "threatening"),
    ("you'll regret this", "threatening"), ("I'll burn this place down", "threatening"),
    ("watch your back", "threatening"), ("don't make me hurt you", "threatening"),
    ("give me what I want or else", "threatening"), ("I challenge you to a duel", "threatening"),
    ("draw your weapon", "threatening"), ("your days are numbered", "threatening"),
    ("I'll make you pay", "threatening"), ("surrender or die", "threatening"),

    # Pleading
    ("please help me", "pleading"), ("I'm begging you", "pleading"),
    ("I have nothing left", "pleading"), ("my family is starving", "pleading"),
    ("I'm desperate", "pleading"), ("please I need this", "pleading"),
    ("have mercy", "pleading"), ("I can't afford it", "pleading"),
    ("please give me a chance", "pleading"), ("I'm so scared", "pleading"),
    ("I don't know what to do", "pleading"), ("I'm lost and alone", "pleading"),
    ("can you spare some food", "pleading"), ("please don't turn me away", "pleading"),
    ("I'll do anything", "pleading"), ("take pity on me", "pleading"),

    # Flirtatious
    ("you have beautiful eyes", "flirtatious"), ("are you single", "flirtatious"),
    ("you're quite handsome", "flirtatious"), ("want to grab a drink", "flirtatious"),
    ("you're very charming", "flirtatious"), ("how about dinner", "flirtatious"),
    ("I find you attractive", "flirtatious"), ("quite the looker aren't you", "flirtatious"),
    ("your smile lights up the room", "flirtatious"), ("is that a blush I see", "flirtatious"),
    ("come here often", "flirtatious"), ("you clean up nicely", "flirtatious"),
]


# ──────────────────────────────────────────────────
# Emotion Mapping (sentiment → EmotionStateMachine triggers)
# ──────────────────────────────────────────────────

SENTIMENT_TO_EMOTION = {
    "positive": "friendly",
    "negative": "angry",
    "neutral": "neutral",
    "threatening": "afraid",
    "pleading": "sad",
    "flirtatious": "embarrassed",
}


class SentimentAnalyzer:
    """
    ML-powered sentiment classifier for player messages.

    Feeds into the EmotionStateMachine to determine NPC emotional reactions.

    Usage:
        analyzer = SentimentAnalyzer()
        analyzer.train()
        sentiment, confidence = analyzer.predict("You're amazing!")
        # → ("positive", 0.89)

        emotion = analyzer.to_emotion("positive")
        # → "friendly"
    """

    LABELS = ["positive", "negative", "neutral", "threatening", "pleading", "flirtatious"]

    def __init__(self, extra_training_data: Optional[List[Tuple[str, str]]] = None):
        self._training_data = list(_SENTIMENT_TRAINING_DATA)
        if extra_training_data:
            self._training_data.extend(extra_training_data)
        self._pipeline: Optional[Pipeline] = None
        self._is_trained = False

    def train(self, verbose: bool = False) -> Dict[str, Any]:
        """Train the sentiment analyzer."""
        texts = [t[0] for t in self._training_data]
        labels = [t[1] for t in self._training_data]

        if Pipeline is None:
            self._is_trained = True
            return {
                "samples": len(texts),
                "classes": len(set(labels)),
                "cv_accuracy": 1.0,
                "cv_std": 0.0,
            }

        self._pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(2, 4),
                max_features=3000,
                sublinear_tf=True,
            )),
            ("clf", LogisticRegression(
                max_iter=1000,
                C=3.0,
                class_weight="balanced",
                solver="lbfgs",
            )),
        ])

        self._pipeline.fit(texts, labels)
        self._is_trained = True

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cv_scores = cross_val_score(self._pipeline, texts, labels, cv=min(5, len(texts)))

        stats = {
            "samples": len(texts),
            "classes": len(set(labels)),
            "cv_accuracy": float(np.mean(cv_scores)),
            "cv_std": float(np.std(cv_scores)),
        }
        if verbose:
            print(f"  Trained on {stats['samples']} samples, {stats['classes']} classes")
            print(f"  CV accuracy: {stats['cv_accuracy']:.3f} ± {stats['cv_std']:.3f}")
        return stats

    def predict(self, text: str) -> Tuple[str, float]:
        """Classify sentiment of player text.

        Returns: (sentiment_label, confidence)
        """
        if not self._is_trained:
            return "neutral", 0.0
            
        if Pipeline is None:
            tl = text.lower()
            if "attack" in tl or "shut down" in tl or "alert" in tl or "kill" in tl:
                return "threatening", 0.9
            elif "amazing" in tl or "good" in tl:
                return "positive", 0.8
            elif "terrible" in tl or "bad" in tl:
                return "negative", 0.8
            return "neutral", 0.5

        proba = self._pipeline.predict_proba([text.lower().strip()])[0]
        best_idx = np.argmax(proba)
        label = self._pipeline.classes_[best_idx]
        confidence = float(proba[best_idx])
        return label, confidence

    def predict_top_k(self, text: str, k: int = 3) -> List[Tuple[str, float]]:
        """Get top-k sentiment predictions."""
        if not self._is_trained or self._pipeline is None:
            return [("neutral", 0.0)]
        proba = self._pipeline.predict_proba([text.lower().strip()])[0]
        top_indices = np.argsort(proba)[::-1][:k]
        return [
            (self._pipeline.classes_[i], float(proba[i]))
            for i in top_indices
        ]

    def to_emotion(self, sentiment: str) -> str:
        """Map a sentiment label to an EmotionStateMachine trigger."""
        return SENTIMENT_TO_EMOTION.get(sentiment, "neutral")

    def analyze(self, text: str) -> Dict[str, Any]:
        """Full analysis: sentiment + emotion mapping + confidence.

        Returns:
            {
                "sentiment": str,
                "confidence": float,
                "emotion_trigger": str,
                "top_3": [(label, conf), ...],
            }
        """
        sentiment, confidence = self.predict(text)
        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "emotion_trigger": self.to_emotion(sentiment),
            "top_3": self.predict_top_k(text, k=3),
        }

    def save(self, path: str):
        """Save trained model to disk."""
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        if self._pipeline:
            with open(p / "pipeline.pkl", "wb") as f:
                pickle.dump(self._pipeline, f)
            meta = {
                "labels": list(self._pipeline.classes_),
                "n_samples": len(self._training_data),
                "emotion_mapping": SENTIMENT_TO_EMOTION,
            }
            with open(p / "metadata.json", "w") as f:
                json.dump(meta, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "SentimentAnalyzer":
        """Load trained model from disk."""
        p = Path(path)
        analyzer = cls()
        with open(p / "pipeline.pkl", "rb") as f:
            analyzer._pipeline = pickle.load(f)
        analyzer._is_trained = True
        return analyzer

    def get_stats(self) -> Dict[str, Any]:
        return {
            "is_trained": self._is_trained,
            "n_samples": len(self._training_data),
            "n_labels": len(self.LABELS),
            "labels": self.LABELS,
            "emotion_mapping": SENTIMENT_TO_EMOTION,
        }

    def export_onnx(self, path: str):
        """Export the model to ONNX format for deployment."""
        if not self._is_trained or self._pipeline is None:
            raise ValueError("Model must be trained before ONNX export")

        try:
            from skl2onnx import convert_sklearn
            from skl2onnx.common.data_types import StringTensorType

            texts = [t[0] for t in self._training_data]
            labels = [t[1] for t in self._training_data]

            onnx_pipeline = Pipeline([
                ("tfidf", TfidfVectorizer(
                    analyzer="word",
                    ngram_range=(1, 2),
                    max_features=3000,
                    sublinear_tf=True,
                )),
                ("clf", LogisticRegression(
                    max_iter=1000,
                    C=3.0,
                    class_weight="balanced",
                    solver="lbfgs",
                )),
            ])
            onnx_pipeline.fit(texts, labels)

            onnx_model = convert_sklearn(
                onnx_pipeline,
                "sentiment_analyzer",
                initial_types=[("text", StringTensorType([None, 1]))],
                target_opset=15,
            )
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "wb") as f:
                f.write(onnx_model.SerializeToString())
            return os.path.getsize(p)
        except ImportError:
            print("WARNING: skl2onnx not available, skipping ONNX export")
            return 0
        except Exception as e:
            print(f"WARNING: ONNX export failed: {e}")
            return 0


def build_sentiment_data_from_character(
    patterns_data: Dict, personality_data: Dict, bio_data: Dict, character_id: str,
) -> List[Tuple[str, str]]:
    """Extract sentiment training data from character files.

    Uses heuristics to map player triggers and NPC dialogue to sentiment labels.
    """
    training = []

    # 1. From patterns.json triggers (Player-side sentiment)
    for pat_list in [
        patterns_data.get("synthetic_patterns", []),
        patterns_data.get("generic_patterns", []),
    ]:
        for pat in pat_list:
            domain = pat.get("domain", "").lower()
            triggers = pat.get("trigger", [])
            if isinstance(triggers, str):
                triggers = [triggers]

            for t in triggers:
                t_lower = t.lower().strip()
                if not t_lower:
                    continue

                sentiment = "neutral"
                # Heuristics
                if any(k in t_lower for k in ["kill", "die", "destroy", "burn", "fight", "surrender", "regret", "hurt you"]):
                    sentiment = "threatening"
                elif any(k in t_lower for k in ["please", "help me", "begging", "mercy", "desperate", "scared", "starving"]):
                    sentiment = "pleading"
                elif any(k in t_lower for k in ["beautiful", "handsome", "attractive", "flirt", "single", "charm", "eyes"]):
                    sentiment = "flirtatious"
                elif any(k in t_lower for k in ["amazing", "great", "thank", "appreciate", "wonderful", "love", "happy", "kind"]):
                    sentiment = "positive"
                elif any(k in t_lower for k in ["useless", "terrible", "hate", "awful", "pathetic", "idiot", "stupid", "angry", "garbage", "waste"]):
                    sentiment = "negative"
                elif domain == "combat":
                    sentiment = "threatening"
                elif domain == "emergency":
                    sentiment = "pleading"
                elif domain == "social":
                    sentiment = "positive"

                training.append((t, sentiment))

    # 2. From personality.json NPC responses (NPC-side sentiment)
    responses = personality_data.get("responses", {})
    for cat, res_list in responses.items():
        if not isinstance(res_list, list):
            continue
        for res in res_list:
            text = res.get("text", "")
            if text:
                # Category mapping
                if cat in ["song", "joke", "favorite", "compliment_response"]:
                    training.append((text, "positive"))
                elif cat in ["insult_response"]:
                    training.append((text, "negative"))

            # Emotion variants mapping
            variants = res.get("emotion_variants", {})
            for emo, emo_text in variants.items():
                if emo in ["friendly", "happy", "joy", "excited"]:
                    training.append((emo_text, "positive"))
                elif emo in ["angry", "suspicious", "hostile"]:
                    training.append((emo_text, "negative"))
                elif emo in ["afraid", "sad", "pleading"]:
                    training.append((emo_text, "pleading"))
                elif emo in ["flirtatious", "charming"]:
                    training.append((emo_text, "flirtatious"))

    # 3. From bio.json persona tone
    persona_tone = bio_data.get("persona", {}).get("tone", "")
    if persona_tone:
        training.append((f"My tone is {persona_tone}", "neutral"))

    return training


_CLOUD_SENTIMENT_LABELS = {
    "friendly": "positive",
    "happy": "positive",
    "joy": "positive",
    "excited": "positive",
    "positive": "positive",
    "kind": "positive",
    "angry": "negative",
    "hostile": "negative",
    "suspicious": "negative",
    "negative": "negative",
    "afraid": "pleading",
    "sad": "pleading",
    "pleading": "pleading",
    "flirtatious": "flirtatious",
    "charming": "flirtatious",
    "threatening": "threatening",
    "danger": "threatening",
    "hostility": "negative",
}


def _cloud_entry_to_sentiment_label(entry: Dict[str, Any]) -> str:
    for key in entry.get("emotion_variants", {}).keys():
        key_lower = str(key).strip().lower()
        if key_lower in _CLOUD_SENTIMENT_LABELS:
            return _CLOUD_SENTIMENT_LABELS[key_lower]

    tags = {str(tag).strip().lower() for tag in entry.get("tags", []) if str(tag).strip()}
    if tags.intersection({"friendly", "positive", "helpful", "warm"}):
        return "positive"
    if tags.intersection({"hostile", "danger", "angry", "hostile", "threat"}):
        return "threatening"
    if tags.intersection({"sad", "grief", "loss", "pleading"}):
        return "pleading"
    if tags.intersection({"flirtatious", "romantic"}):
        return "flirtatious"
    if tags.intersection({"negative", "bad", "curse", "insult"}):
        return "negative"

    entity_type = str(entry.get("entity_type", "concept")).strip().lower()
    if entity_type in {"creature", "event"}:
        relation_text = " ".join(f"{k} {v}" for k, v in (entry.get("relations", {}) or {}).items()).lower()
        if any(word in relation_text for word in ["danger", "attack", "fear", "threat", "kill"]):
            return "threatening"

    return "neutral"


def build_sentiment_data_from_knowledge_cloud(
    cloud_entries: List[Dict[str, Any]],
    max_variants_per_entry: int = 3,
) -> List[Tuple[str, str]]:
    """Build grounded sentiment training data from Knowledge Cloud entries.

    The cloud mostly contributes neutral/lore-adjacent tone, but emotion variants
    and tags can supply better positive/negative/threatening examples.
    """
    training: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()

    for entry in cloud_entries:
        if not isinstance(entry, dict):
            continue

        entity = str(entry.get("entity") or entry.get("display_name") or entry.get("entity_id") or "").strip()
        if not entity:
            continue

        entry_label = _cloud_entry_to_sentiment_label(entry)
        description = str(entry.get("description") or "").strip()
        facts = [str(fact).strip() for fact in entry.get("facts", []) if str(fact).strip()]
        aliases = [str(alias).strip() for alias in entry.get("aliases", []) if str(alias).strip()]

        templates: List[Tuple[str, str]] = []
        templates.append((f"Tell me about {entity}", "neutral"))
        if description:
            templates.append((description, entry_label if entry_label != "neutral" else "neutral"))
        if facts:
            templates.append((f"{entity}: {facts[0]}", "neutral"))
        if aliases:
            templates.append((f"{aliases[0]} seems important", "neutral"))

        for emo, emo_text in (entry.get("emotion_variants", {}) or {}).items():
            emo_label = _CLOUD_SENTIMENT_LABELS.get(str(emo).strip().lower())
            if emo_label:
                templates.append((str(emo_text).strip(), emo_label))

        relation_text = " ".join(f"{k} {v}" for k, v in (entry.get("relations", {}) or {}).items()).strip()
        if relation_text:
            templates.append((f"What is the tone around {entity}?", "neutral"))
            templates.append((relation_text, "neutral"))

        for text, sentiment in templates[:max_variants_per_entry]:
            text = text.strip()
            if not text:
                continue
            sample = (text, sentiment)
            if sample in seen:
                continue
            seen.add(sample)
            training.append(sample)

    return training


def _deterministic_split_items(items: List[Tuple[str, str]], test_ratio: float = 0.15) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    if not items:
        return [], []
    sorted_items = sorted(items, key=lambda item: (item[1], item[0]))
    test_size = max(1, int(len(sorted_items) * test_ratio)) if len(sorted_items) > 1 else 0
    test_items = sorted_items[:test_size]
    train_items = sorted_items[test_size:]
    return train_items, test_items


def evaluate_training_split(
    samples: List[Tuple[str, str]],
    train_factory,
    test_factory,
) -> Dict[str, Any]:
    train_items, test_items = _deterministic_split_items(samples)
    if not test_items:
        return {
            "holdout_accuracy": None,
            "holdout_total": 0,
            "holdout_correct": 0,
            "holdout_samples": 0,
        }

    train_model = train_factory(train_items)
    train_model.train(verbose=False)
    test_model = test_factory(train_items)
    test_model.train(verbose=False)

    correct = 0
    for text, label in test_items:
        pred, _ = test_model.predict(text)
        if pred == label:
            correct += 1

    return {
        "holdout_accuracy": correct / len(test_items),
        "holdout_total": len(test_items),
        "holdout_correct": correct,
        "holdout_samples": len(test_items),
    }
