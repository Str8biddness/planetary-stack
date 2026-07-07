import argparse
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.metrics import accuracy_score, mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split
    import numpy as np
    import joblib
except ImportError:
    pass  # We will install scikit-learn if missing

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("train_triad")

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
MODELS_DIR = DATA_DIR / "models"
TRACE_FILE = REPO_ROOT / "logs" / "teacher_traces.jsonl"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
ATTENTION_WIDTH = 10

@dataclass
class TraceRecord:
    domain: str
    phase: str
    organ: str
    state_features: list[float]
    action_features: list[list[float]]
    multi_focus_weights: list[float]
    trajectory_features: list[float]
    chosen_index: int
    quality: float
    outcome: dict[str, Any]


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value)
        if isinstance(value, str):
            parsed = float(value)
            return parsed if math.isfinite(parsed) else 0.0
    except Exception:
        return 0.0
    return 0.0


def _vector_from_dense(value: Any, width: int = 12) -> list[float]:
    if isinstance(value, list):
        vector = [_safe_float(v) for v in value[:width]]
    else:
        vector = []
    if len(vector) < width:
        vector.extend([0.0] * (width - len(vector)))
    return vector


def _pad_vector(values: list[float], width: int) -> list[float]:
    padded = [_safe_float(v) for v in values[:width]]
    if len(padded) < width:
        padded.extend([0.0] * (width - len(padded)))
    return padded


def _extract_numeric_features(block: Any, order: list[str], width: int = 12) -> list[float]:
    features = [_safe_float(block.get(key)) if isinstance(block, dict) else 0.0 for key in order]
    if len(features) < width:
        features.extend([0.0] * (width - len(features)))
    return features[:width]


def _load_trace_records() -> list[TraceRecord]:
    if not TRACE_FILE.exists():
        return []

    records: list[TraceRecord] = []
    with open(TRACE_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            domain = str(obj.get("domain") or "")
            phase = str(obj.get("phase") or "")
            organ = str(obj.get("organ") or "")
            state = obj.get("stateFeatures") or {}
            action_list = obj.get("actionFeatures") or []
            traj = obj.get("trajectoryFeatures") or {}
            outcome = obj.get("outcome") or {}
            chosen = int(obj.get("chosenActionIndex") or 0)
            quality = _safe_float(outcome.get("quality", 1.0))
            records.append(TraceRecord(
                domain=domain,
                phase=phase,
                organ=organ,
                state_features=_extract_numeric_features(state, [
                    "topicCount", "lastClarification", "unresolvedQuestions", "confusion", "safety", "frustration",
                    "avgHostErrorRate", "avgServiceLatency", "criticalIncidents", "unresolvedIncidents",
                    "npcCount", "combatActive"
                ]),
                action_features=[_vector_from_dense(a.get("dense") if isinstance(a, dict) else [], 10) for a in action_list if isinstance(a, dict)],
                multi_focus_weights=_vector_from_dense((obj.get("organOutputs") or {}).get("attentionWeights"), ATTENTION_WIDTH),
                trajectory_features=_extract_numeric_features(traj, [
                    "confusionRate", "safetyRate", "resolution", "turnBalance",
                    "incidentRate", "actionRate", "deployRate", "stability",
                    "spawnRate", "combatRate", "npcTickRate"
                ]),
                chosen_index=chosen,
                quality=quality,
                outcome=outcome,
            ))
    return records


def _domain_records(domain: str, organ: str, phase: str) -> list[TraceRecord]:
    return [r for r in _load_trace_records() if r.domain == domain and r.organ == organ and r.phase == phase]


def generate_dummy_data(samples=100, features=10):
    import numpy as np
    X = np.random.rand(samples, features)
    y_class = np.random.randint(0, 2, size=samples)
    y_reg = np.random.rand(samples)
    return X, y_class, y_reg


def _fallback_dataset(domain: str, organ: str):
    return generate_dummy_data(samples=500, features=12)


def _split_data(X, y):
    if len(X) < 5:
        return X, X, y, y
    return train_test_split(X, y, test_size=0.2, random_state=42)


def train_organ(domain: str, organ: str):
    logger.info(f"Starting training for Domain: {domain.upper()} | Organ: {organ.upper()}")

    phase = "planning" if organ in {"policy_prior", "attention"} else "output"
    records = _domain_records(domain, organ, phase)
    if not records:
        logger.info("No trace data found, using synthetic fallback dataset")
        X, y_class, y_reg = _fallback_dataset(domain, organ)
    else:
        if organ == "policy_prior":
            X = []
            y_class = []
            for rec in records:
                feature_vector = rec.state_features + (rec.action_features[0] if rec.action_features else [0.0] * 10) + rec.multi_focus_weights[:4]
                X.append(feature_vector[:24])
                y_class.append(max(0, rec.chosen_index))
            X = np.asarray(X)
            y_class = np.asarray(y_class)
            y_reg = np.asarray([rec.quality for rec in records])
        elif organ == "attention":
            X = []
            y_reg = []
            for rec in records:
                X.append((rec.state_features + rec.trajectory_features)[:24])
                y_reg.append(_pad_vector(rec.multi_focus_weights or [1.0], ATTENTION_WIDTH))
            X = np.asarray(X)
            y_reg = np.asarray(y_reg)
            y_class = np.asarray([0] * len(X))
        else:
            X = []
            y_reg = []
            for rec in records:
                X.append((rec.state_features + rec.trajectory_features)[:24])
                y_reg.append(rec.quality)
            X = np.asarray(X)
            y_reg = np.asarray(y_reg)
            y_class = np.asarray([int(v > 0.5) for v in y_reg])

    model_path = MODELS_DIR / f"{domain}_{organ}.pkl"

    if organ == "policy_prior":
        X_train, X_val, y_train, y_val = _split_data(X, y_class)
        model = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
        model.fit(X_train, y_train)
        train_pred = model.predict(X_train)
        val_pred = model.predict(X_val)
        train_acc = accuracy_score(y_train, train_pred)
        val_acc = accuracy_score(y_val, val_pred)
        logger.info(f"Trained {organ} - Train Accuracy: {train_acc:.2%} | Validation Accuracy: {val_acc:.2%}")
        joblib.dump(model, model_path)

    elif organ == "risk_outcome":
        X_train, X_val, y_train, y_val = _split_data(X, y_reg)
        model = RandomForestRegressor(n_estimators=50, max_depth=5, random_state=42)
        model.fit(X_train, y_train)
        train_pred = model.predict(X_train)
        val_pred = model.predict(X_val)
        train_score = r2_score(y_train, train_pred) if len(set(y_train)) > 1 else 0.0
        val_score = r2_score(y_val, val_pred) if len(set(y_val)) > 1 else 0.0
        logger.info(f"Trained {organ} - Train R2: {train_score:.4f} | Validation R2: {val_score:.4f}")
        joblib.dump(model, model_path)

    elif organ == "attention":
        X_train, X_val, y_train, y_val = _split_data(X, y_reg)
        model = RandomForestRegressor(n_estimators=50, max_depth=5, random_state=42)
        model.fit(X_train, y_train)
        train_pred = model.predict(X_train)
        val_pred = model.predict(X_val)
        train_mse = mean_squared_error(y_train, train_pred)
        val_mse = mean_squared_error(y_val, val_pred)
        logger.info(f"Trained {organ} - Train MSE: {train_mse:.4f} | Validation MSE: {val_mse:.4f}")
        joblib.dump(model, model_path)

    else:
        logger.error(f"Unknown organ type: {organ}")
        return

    logger.info(f"Saved model to {model_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Synthesus ML Organs")
    parser.add_argument("--domain", type=str, required=True, choices=["chat", "sysops", "gm"])
    parser.add_argument("--organ", type=str, required=True, choices=["policy_prior", "risk_outcome", "attention"])

    args = parser.parse_args()

    try:
        import sklearn
    except ImportError:
        logger.error("scikit-learn not installed. Run: pip install scikit-learn joblib")
        exit(1)

    train_organ(args.domain, args.organ)
