#!/usr/bin/env python3
"""
Synthesus ML Organ Training — Enhanced Version
Trains all ML organs on synthetic high-quality datasets and exports to ONNX when applicable.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ml.behavior_predictor import BehaviorPredictor
from ml.dialogue_ranker import DialogueRanker
from ml.emotion_detector import EmotionDetector
from ml.intent_classifier import IntentClassifier
from ml.loot_balancer import LootBalancer
from ml.sentiment_analyzer import SentimentAnalyzer

MODEL_DIR = REPO_ROOT / "models" / "onnx"
LOG_DIR = REPO_ROOT / "logs"
REGISTRY_FILE = REPO_ROOT / "models" / "model_registry.json"
SYNTH_DATA_DIR = REPO_ROOT / "ml" / "synthetic_data"

MODEL_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_VERSION = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_latest_synth_data(name: str):
    files = sorted(SYNTH_DATA_DIR.glob(f"{name}_*.json"))
    if not files:
        return None
    with open(files[-1]) as f:
        return json.load(f)


def load_registry():
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE) as f:
            return json.load(f)
    return {"models": {}}


def save_registry(registry):
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)


def append_log(entry: str):
    log_file = LOG_DIR / "training_log.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(log_file, "a") as f:
        f.write(f"## {timestamp}\n\n{entry}\n\n---\n\n")


def _validation_status(path: str) -> str:
    try:
        if not path:
            return "N/A"
        import onnx
        model = onnx.load(path)
        onnx.checker.check_model(model)
        return "PASSED"
    except Exception:
        return "FAILED"


def train_intent(extra_data):
    log("Training IntentClassifier on enhanced dataset...")
    clf = IntentClassifier(extra_training_data=extra_data)
    stats = clf.train(verbose=True)
    onnx_path = MODEL_DIR / f"intent_classifier_v{EXPORT_VERSION}.onnx"
    size = clf.export_onnx(str(onnx_path))
    status = _validation_status(str(onnx_path)) if size > 0 else "FAILED"
    return {"name": "intent_classifier", "version": EXPORT_VERSION, "samples": stats["samples"], "classes": stats["classes"], "cv_accuracy": stats["cv_accuracy"], "cv_std": stats["cv_std"], "onnx_path": str(onnx_path), "onnx_size_bytes": size, "validation": status, "training_data": "enhanced_synthetic"}


def train_sentiment(extra_data):
    log("Training SentimentAnalyzer on enhanced dataset...")
    clf = SentimentAnalyzer(extra_training_data=extra_data)
    stats = clf.train(verbose=True)
    onnx_path = MODEL_DIR / f"sentiment_analyzer_v{EXPORT_VERSION}.onnx"
    try:
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import StringTensorType
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline

        texts = [t[0] for t in clf._training_data]
        labels = [t[1] for t in clf._training_data]
        onnx_pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), max_features=5000, sublinear_tf=True)),
            ("clf", LogisticRegression(max_iter=1000, C=3.0, class_weight="balanced", solver="lbfgs")),
        ])
        onnx_pipeline.fit(texts, labels)
        onnx_model = convert_sklearn(onnx_pipeline, "sentiment_analyzer", initial_types=[("text", StringTensorType([None, 1]))], target_opset=15)
        with open(onnx_path, "wb") as f:
            f.write(onnx_model.SerializeToString())
        size = os.path.getsize(onnx_path)
    except Exception:
        size = 0
    status = _validation_status(str(onnx_path)) if size > 0 else "FAILED"
    return {"name": "sentiment_analyzer", "version": EXPORT_VERSION, "samples": stats["samples"], "classes": stats["classes"], "cv_accuracy": stats["cv_accuracy"], "cv_std": stats["cv_std"], "onnx_path": str(onnx_path), "onnx_size_bytes": size, "validation": status, "training_data": "enhanced_synthetic"}


def train_behavior(extra_data):
    log("Training BehaviorPredictor on enhanced dataset...")
    predictor = BehaviorPredictor()
    stats = predictor.train(extra_data)
    onnx_path = MODEL_DIR / f"behavior_predictor_v{EXPORT_VERSION}.onnx"
    size = predictor.export_onnx(str(onnx_path))
    return {"name": "behavior_predictor", "version": EXPORT_VERSION, "samples": stats["samples"], "classes": stats["classes"], "cv_accuracy": stats["cv_accuracy"], "cv_std": stats["cv_std"], "onnx_path": str(onnx_path), "onnx_size_bytes": size, "validation": _validation_status(str(onnx_path)) if size > 0 else "N/A", "training_data": "enhanced_synthetic"}


def _expand_dialogue_examples(dialogue_data):
    examples = []
    for scenario in dialogue_data:
        query = scenario.get("query", "")
        candidates = scenario.get("candidates", [])
        ideal_ranks = scenario.get("ideal_ranks", [])
        for idx, response in enumerate(candidates):
            rank = ideal_ranks[idx] if idx < len(ideal_ranks) else len(candidates)
            examples.append({
                "query": query,
                "response": response,
                "label": 1 if rank == 0 else 0,
                "personality": {"friendliness": 0.8, "formality": 0.5, "aggression": 0.1},
                "recent_responses": [],
                "context_keywords": query.split(),
            })
    return examples


def train_dialogue(extra_data):
    log("Training DialogueRanker on enhanced dataset...")
    ranker = DialogueRanker()
    labeled = _expand_dialogue_examples(extra_data)
    stats = ranker.train(labeled)
    onnx_path = MODEL_DIR / f"dialogue_ranker_v{EXPORT_VERSION}.onnx"
    size = ranker.export_onnx(str(onnx_path))
    return {"name": "dialogue_ranker", "version": EXPORT_VERSION, "samples": stats["samples"], "classes": stats["classes"], "cv_accuracy": stats["cv_accuracy"], "cv_std": stats["cv_std"], "onnx_path": str(onnx_path), "onnx_size_bytes": size, "validation": _validation_status(str(onnx_path)) if size > 0 else "N/A", "training_data": "enhanced_synthetic"}


def train_emotion(extra_data):
    log("Training EmotionDetector on enhanced dataset...")
    detector = EmotionDetector()
    stats = detector.train(extra_data)
    onnx_path = MODEL_DIR / f"emotion_detector_v{EXPORT_VERSION}.onnx"
    size = detector.export_onnx(str(onnx_path))
    return {"name": "emotion_detector", "version": EXPORT_VERSION, "samples": stats["samples"], "classes": stats["classes"], "cv_accuracy": stats["cv_accuracy"], "cv_std": stats["cv_std"], "onnx_path": str(onnx_path), "onnx_size_bytes": size, "validation": _validation_status(str(onnx_path)) if size > 0 else "N/A", "training_data": "enhanced_synthetic"}


def train_loot(extra_data):
    log("Training LootBalancer on enhanced dataset...")
    balancer = LootBalancer()
    stats = balancer.train(extra_data)
    onnx_path = MODEL_DIR / f"loot_balancer_v{EXPORT_VERSION}.onnx"
    size = balancer.export_onnx(str(onnx_path))
    return {"name": "loot_balancer", "version": EXPORT_VERSION, "samples": stats["samples"], "classes": stats["classes"], "cv_accuracy": stats["cv_accuracy"], "cv_std": stats["cv_std"], "onnx_path": str(onnx_path), "onnx_size_bytes": size, "validation": _validation_status(str(onnx_path)) if size > 0 else "N/A", "training_data": "enhanced_synthetic"}


def main():
    log("=== Synthesus ML Training Pipeline (Enhanced) ===")

    synth_intent = load_latest_synth_data("intent") or []
    synth_sentiment = load_latest_synth_data("sentiment") or []
    synth_behavior = load_latest_synth_data("behavior") or []
    synth_emotion = load_latest_synth_data("emotion") or []
    synth_dialogue = load_latest_synth_data("dialogue") or []
    synth_loot = load_latest_synth_data("loot") or []

    log(f"  Loaded {len(synth_intent)} intent samples")
    log(f"  Loaded {len(synth_sentiment)} sentiment samples")
    log(f"  Loaded {len(synth_behavior)} behavior samples")
    log(f"  Loaded {len(synth_emotion)} emotion samples")
    log(f"  Loaded {len(synth_dialogue)} dialogue samples")
    log(f"  Loaded {len(synth_loot)} loot samples")

    results = [
        train_intent(synth_intent),
        train_sentiment(synth_sentiment),
        train_behavior(synth_behavior),
        train_dialogue(synth_dialogue),
        train_emotion(synth_emotion),
        train_loot(synth_loot),
    ]

    registry = load_registry()
    for r in results:
        registry["models"][r["name"]] = r
    save_registry(registry)

    lines = ["Synthesus enhanced training pipeline run."]
    for r in results:
        if r.get("cv_accuracy") is not None:
            lines.append(f"- **{r['name']}** v{r['version']}: acc={r['cv_accuracy']:.4f}±{r['cv_std']:.4f}, {r['samples']} samples, {r['classes']} classes — [{r['validation']}]")
        else:
            lines.append(f"- **{r['name']}** v{r['version']}: {r['samples']} samples, {r['classes']} classes — [{r['validation']}]")
    append_log("\n".join(lines))
    log("Training pipeline complete.")


if __name__ == "__main__":
    main()
