#!/usr/bin/env python3
"""
Synthesus ML Training Pipeline
Trains sklearn-based models and exports to ONNX format.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from ml.intent_classifier import IntentClassifier
from ml.sentiment_analyzer import SentimentAnalyzer

MODEL_DIR = REPO_ROOT / "models" / "onnx"
LOG_DIR = REPO_ROOT / "logs"
REGISTRY_FILE = REPO_ROOT / "models" / "model_registry.json"

MODEL_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

EXPORT_VERSION = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


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
    entry_lines = [
        f"## {timestamp}",
        "",
        entry,
        "",
        "---",
        "",
    ]
    with open(log_file, "a") as f:
        f.write("\n".join(entry_lines))


def _load_json_if_exists(path: Path):
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        log(f"  Error loading {path}: {e}")
        return None


def load_character_data():
    """Crawl characters directory and extract intent/sentiment samples."""
    intent_data = []
    sentiment_data = []
    char_dir = REPO_ROOT / "characters"

    if not char_dir.exists():
        log(f"  WARNING: Character directory {char_dir} not found")
        return intent_data, sentiment_data

    # Import builders
    from ml.intent_classifier import build_training_data_from_character
    from ml.sentiment_analyzer import build_sentiment_data_from_character

    for char_path in char_dir.iterdir():
        if not char_path.is_dir() or char_path.name == "schema":
            continue

        pat_file = char_path / "patterns.json"
        pers_file = char_path / "personality.json"
        bio_file = char_path / "bio.json"

        patterns = _load_json_if_exists(pat_file) or {}
        personality = _load_json_if_exists(pers_file) or {}
        bio = _load_json_if_exists(bio_file) or {}

        if patterns:
            intent_data.extend(build_training_data_from_character(patterns, char_path.name))

        if patterns or personality or bio:
            sentiment_data.extend(
                build_sentiment_data_from_character(patterns, personality, bio, char_path.name)
            )

    return intent_data, sentiment_data


def load_knowledge_cloud_data(limit: int = 2000):
    """Load a bounded sample of Knowledge Cloud entries for synthetic augmentation."""
    cloud_dir = REPO_ROOT / "data" / "knowledge_cloud"
    if not cloud_dir.exists():
        return [], []

    entries = []
    for name in ["world_lore.json", "evolution.json"]:
        data = _load_json_if_exists(cloud_dir / name)
        if not data:
            continue
        if isinstance(data, list):
            entries.extend([entry for entry in data if isinstance(entry, dict)])
        else:
            entries.extend([entry for entry in data.get("entries", []) if isinstance(entry, dict)])

    if not entries:
        return [], []

    entries = entries[:limit]

    from ml.intent_classifier import build_training_data_from_knowledge_cloud
    from ml.sentiment_analyzer import build_sentiment_data_from_knowledge_cloud

    intent_data = build_training_data_from_knowledge_cloud(entries)
    sentiment_data = build_sentiment_data_from_knowledge_cloud(entries)
    return intent_data, sentiment_data


def evaluate_intent_holdout(samples):
    from ml.intent_classifier import evaluate_training_split

    def factory(extra_data):
        return IntentClassifier(extra_training_data=extra_data)

    return evaluate_training_split(samples, factory, factory)


def evaluate_sentiment_holdout(samples):
    from ml.sentiment_analyzer import evaluate_training_split

    def factory(extra_data):
        return SentimentAnalyzer(extra_training_data=extra_data)

    return evaluate_training_split(samples, factory, factory)


def train_and_export_intent(extra_data=None, holdout_metrics=None):
    """Train intent classifier and export to ONNX."""
    log("Training IntentClassifier...")
    clf = IntentClassifier(extra_training_data=extra_data)
    stats = clf.train(verbose=True)
    log(f"  CV accuracy: {stats['cv_accuracy']:.4f} ± {stats['cv_std']:.4f}")

    if holdout_metrics:
        log(
            f"  Holdout accuracy: {holdout_metrics['holdout_accuracy']:.4f} "
            f"({holdout_metrics['holdout_correct']}/{holdout_metrics['holdout_total']})"
        )

    onnx_path = MODEL_DIR / f"intent_classifier_v{EXPORT_VERSION}.onnx"
    size = clf.export_onnx(str(onnx_path))

    if size > 0:
        log(f"  Exported ONNX: {onnx_path} ({size:,} bytes)")
        return {
            "name": "intent_classifier",
            "version": EXPORT_VERSION,
            "cv_accuracy": stats["cv_accuracy"],
            "cv_std": stats["cv_std"],
            "holdout_accuracy": None if not holdout_metrics else holdout_metrics["holdout_accuracy"],
            "holdout_total": 0 if not holdout_metrics else holdout_metrics["holdout_total"],
            "holdout_correct": 0 if not holdout_metrics else holdout_metrics["holdout_correct"],
            "samples": stats["samples"],
            "classes": stats["classes"],
            "onnx_path": str(onnx_path),
            "onnx_size_bytes": size,
            "export_date": datetime.now(timezone.utc).isoformat(),
        }
    else:
        log("  WARNING: ONNX export failed for intent_classifier")
        return None


def train_and_export_sentiment(extra_data=None, holdout_metrics=None):
    """Train sentiment analyzer and export to ONNX."""
    log("Training SentimentAnalyzer...")
    clf = SentimentAnalyzer(extra_training_data=extra_data)
    stats = clf.train(verbose=True)
    log(f"  CV accuracy: {stats['cv_accuracy']:.4f} ± {stats['cv_std']:.4f}")

    if holdout_metrics:
        log(
            f"  Holdout accuracy: {holdout_metrics['holdout_accuracy']:.4f} "
            f"({holdout_metrics['holdout_correct']}/{holdout_metrics['holdout_total']})"
        )

    onnx_path = MODEL_DIR / f"sentiment_analyzer_v{EXPORT_VERSION}.onnx"
    size = clf.export_onnx(str(onnx_path))

    if size > 0:
        log(f"  Exported ONNX: {onnx_path} ({size:,} bytes)")
        return {
            "name": "sentiment_analyzer",
            "version": EXPORT_VERSION,
            "cv_accuracy": stats["cv_accuracy"],
            "cv_std": stats["cv_std"],
            "holdout_accuracy": None if not holdout_metrics else holdout_metrics["holdout_accuracy"],
            "holdout_total": 0 if not holdout_metrics else holdout_metrics["holdout_total"],
            "holdout_correct": 0 if not holdout_metrics else holdout_metrics["holdout_correct"],
            "samples": stats["samples"],
            "classes": stats["classes"],
            "onnx_path": str(onnx_path),
            "onnx_size_bytes": size,
            "export_date": datetime.now(timezone.utc).isoformat(),
        }
    else:
        log("  WARNING: ONNX export failed for sentiment_analyzer")
        return None


def validate_onnx(model_path: str) -> bool:
    """Quick validation that ONNX model loads correctly."""
    try:
        import onnx
        model = onnx.load(model_path)
        onnx.checker.check_model(model)
        return True
    except Exception as e:
        log(f"  Validation failed: {e}")
        return False


def main():
    log("=== Synthesus ML Training Pipeline ===")

    # Load character and knowledge-cloud data for augmentation
    log("Loading character data for augmentation...")
    intent_extra, sentiment_extra = load_character_data()
    log(f"  Found {len(intent_extra)} intent and {len(sentiment_extra)} sentiment samples from characters.")

    log("Loading knowledge cloud data for augmentation...")
    cloud_intent, cloud_sentiment = load_knowledge_cloud_data(limit=2000)
    log(f"  Found {len(cloud_intent)} intent and {len(cloud_sentiment)} sentiment samples from knowledge cloud.")

    intent_extra.extend(cloud_intent)
    sentiment_extra.extend(cloud_sentiment)

    intent_holdout = evaluate_intent_holdout(intent_extra)
    sentiment_holdout = evaluate_sentiment_holdout(sentiment_extra)

    log(
        f"Intent holdout: {intent_holdout['holdout_accuracy']:.4f} "
        f"({intent_holdout['holdout_correct']}/{intent_holdout['holdout_total']})"
        if intent_holdout["holdout_accuracy"] is not None else "Intent holdout: n/a"
    )
    log(
        f"Sentiment holdout: {sentiment_holdout['holdout_accuracy']:.4f} "
        f"({sentiment_holdout['holdout_correct']}/{sentiment_holdout['holdout_total']})"
        if sentiment_holdout["holdout_accuracy"] is not None else "Sentiment holdout: n/a"
    )

    results = []

    # Train IntentClassifier
    result = train_and_export_intent(intent_extra, intent_holdout)
    if result:
        results.append(result)
        if validate_onnx(result["onnx_path"]):
            log(f"  ONNX validation PASSED")
        else:
            log(f"  ONNX validation FAILED")
            result["validation"] = "FAILED"
    else:
        results.append({"name": "intent_classifier", "status": "EXPORT_FAILED"})

    # Train SentimentAnalyzer
    result = train_and_export_sentiment(sentiment_extra, sentiment_holdout)
    if result:
        results.append(result)
        if validate_onnx(result["onnx_path"]):
            log(f"  ONNX validation PASSED")
        else:
            log(f"  ONNX validation FAILED")
            result["validation"] = "FAILED"
    else:
        results.append({"name": "sentiment_analyzer", "status": "EXPORT_FAILED"})

    # Update registry
    registry = load_registry()
    for r in results:
        name = r.get("name")
        if name and r.get("onnx_path"):
            registry["models"][name] = {
                "version": r["version"],
                "cv_accuracy": r["cv_accuracy"],
                "cv_std": r["cv_std"],
                "holdout_accuracy": r.get("holdout_accuracy"),
                "holdout_total": r.get("holdout_total", 0),
                "holdout_correct": r.get("holdout_correct", 0),
                "samples": r["samples"],
                "classes": r["classes"],
                "onnx_path": r["onnx_path"],
                "onnx_size_bytes": r["onnx_size_bytes"],
                "export_date": r["export_date"],
                "validation": r.get("validation", "PASSED"),
            }

    save_registry(registry)
    log(f"Updated model_registry.json")

    # Build log entry
    log_entries = []
    for r in results:
        if r.get("onnx_path"):
            status = r.get("validation", "PASSED")
            holdout = r.get("holdout_accuracy")
            holdout_text = "n/a" if holdout is None else f"holdout={holdout:.4f}"
            log_entries.append(
                f"- **{r['name']}** v{r['version']}: acc={r['cv_accuracy']:.4f}±{r['cv_std']:.4f}, {holdout_text}, "
                f"{r['samples']} samples, {r['classes']} classes — [{status}]"
            )
        else:
            log_entries.append(f"- **{r['name']}**: EXPORT_FAILED")

    append_log(
        "Synthesus daily training pipeline run.\n\n" +
        "\n".join(log_entries)
    )
    log("Training pipeline complete.")


if __name__ == "__main__":
    main()