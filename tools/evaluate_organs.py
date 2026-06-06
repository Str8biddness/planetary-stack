#!/usr/bin/env python3
"""Trace-driven evaluation harness for Synthesus ML organs.

This script reads logs/teacher_traces.jsonl, reconstructs organ-specific
training examples, loads the latest pickled models from data/models/, and
writes a JSON + Markdown scorecard.

Fictional narrative traces are accepted as training input as long as the
scientific / mathematical fields remain numeric, bounded, and internally
consistent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

try:
    import joblib
    import numpy as np
    from sklearn.metrics import accuracy_score, mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split
except ImportError:  # pragma: no cover - environment fallback
    joblib = None
    np = None
    accuracy_score = None
    mean_squared_error = None
    r2_score = None
    train_test_split = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluate_organs")

REPO_ROOT = Path(__file__).resolve().parent.parent
TRACE_FILE = REPO_ROOT / "logs" / "teacher_traces.jsonl"
MODELS_DIR = REPO_ROOT / "data" / "models"
REPORT_JSON = REPO_ROOT / "logs" / "organ_evaluation_scorecard.json"
REPORT_MD = REPO_ROOT / "logs" / "organ_evaluation_scorecard.md"
ATTENTION_WIDTH = 10
CHAL_ACCELERATOR_GENERATOR = "organ-triad-replay-v3"


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
    replay: dict[str, Any]


@dataclass
class OrganScorecard:
    domain: str
    organ: str
    trace_count: int
    model_path: str
    model_exists: bool
    train_metric: float | None
    validation_metric: float | None
    baseline_metric: float | None
    metric_name: str
    scientific_consistency: float
    replay_coverage: float
    replay_identity_coverage: float
    chal_accelerator_coverage: float
    candidate_critic_coverage: float
    consistency_warnings: list[str]
    notes: list[str]


@dataclass
class QualityGateResult:
    passed: bool
    failures: list[str]
    min_replay_coverage: float | None
    min_replay_identity_coverage: float | None
    min_chal_accelerator_coverage: float | None
    min_candidate_critic_coverage: float | None
    min_scientific_consistency: float | None
    fail_under_baseline: bool
    fail_missing_models: bool


@dataclass
class OrganReplayIntegrityResult:
    schema: str
    passed: bool
    total_chal_records: int
    stored_records: int
    failures: list[str]


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


def _pad_vector(values: Any, width: int) -> list[float]:
    if isinstance(values, list):
        padded = [_safe_float(v) for v in values[:width]]
    else:
        padded = []
    if len(padded) < width:
        padded.extend([0.0] * (width - len(padded)))
    return padded


def _extract_numeric_features(block: Any, order: list[str], width: int = 12) -> list[float]:
    features = [_safe_float(block.get(key)) if isinstance(block, dict) else 0.0 for key in order]
    if len(features) < width:
        features.extend([0.0] * (width - len(features)))
    return features[:width]


def _align_features(matrix, width: int):
    if np is None:
        raise RuntimeError("numpy is required for evaluation")
    if matrix.size == 0:
        return matrix
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    current = matrix.shape[1]
    if current == width:
        return matrix
    if current > width:
        return matrix[:, :width]
    pad = np.zeros((matrix.shape[0], width - current), dtype=float)
    return np.concatenate([matrix, pad], axis=1)


def _collapse_to_scalar(values):
    if np is None:
        raise RuntimeError("numpy is required for evaluation")
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return arr.reshape(-1)
    if arr.ndim == 1:
        return arr
    return np.mean(arr, axis=1)


def _load_trace_records() -> list[TraceRecord]:
    if not TRACE_FILE.exists():
        return []

    records: list[TraceRecord] = []
    with TRACE_FILE.open() as f:
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

            records.append(
                TraceRecord(
                    domain=domain,
                    phase=phase,
                    organ=organ,
                    state_features=_extract_numeric_features(
                        state,
                        [
                            "topicCount",
                            "lastClarification",
                            "unresolvedQuestions",
                            "confusion",
                            "safety",
                            "frustration",
                            "avgHostErrorRate",
                            "avgServiceLatency",
                            "criticalIncidents",
                            "unresolvedIncidents",
                            "npcCount",
                            "combatActive",
                        ],
                    ),
                    action_features=[
                        _vector_from_dense(a.get("dense") if isinstance(a, dict) else [], 10)
                        for a in action_list
                        if isinstance(a, dict)
                    ],
                    multi_focus_weights=_vector_from_dense((obj.get("organOutputs") or {}).get("attentionWeights"), ATTENTION_WIDTH),
                    trajectory_features=_extract_numeric_features(
                        traj,
                        [
                            "confusionRate",
                            "safetyRate",
                            "resolution",
                            "turnBalance",
                            "incidentRate",
                            "actionRate",
                            "deployRate",
                            "stability",
                            "spawnRate",
                            "combatRate",
                            "npcTickRate",
                        ],
                    ),
                    chosen_index=chosen,
                    quality=quality,
                    outcome=outcome,
                    replay=obj.get("replay") if isinstance(obj.get("replay"), dict) else {},
                )
            )

    return records


def _domain_records(domain: str, organ: str, phase: str) -> list[TraceRecord]:
    return [r for r in _load_trace_records() if r.domain == domain and r.organ == organ and r.phase == phase]


def _split_data(X, y):
    if train_test_split is None or len(X) < 5:
        return X, X, y, y
    labels = y.tolist() if hasattr(y, "tolist") else list(y)
    if labels:
        first = labels[0]
        if not isinstance(first, (list, tuple)):
            try:
                if len(set(labels)) < 2:
                    return X, X, y, y
            except TypeError:
                pass
    return train_test_split(X, y, test_size=0.2, random_state=42)


def _metric_name(organ: str) -> str:
    if organ == "policy_prior":
        return "accuracy"
    if organ == "attention":
        return "mse"
    return "r2"


def _build_dataset(domain: str, organ: str):
    phase = "planning" if organ in {"policy_prior", "attention"} else "output"
    records = _domain_records(domain, organ, phase)

    if np is None:
        raise RuntimeError("numpy is required for evaluation")

    if not records:
        return records, np.asarray([]), np.asarray([]), np.asarray([])

    if organ == "policy_prior":
        X = []
        y_class = []
        y_reg = []
        for rec in records:
            feature_vector = rec.state_features + (rec.action_features[0] if rec.action_features else [0.0] * 10) + rec.multi_focus_weights[:4]
            X.append(feature_vector[:24])
            y_class.append(max(0, rec.chosen_index))
            y_reg.append(rec.quality)
        return records, np.asarray(X), np.asarray(y_class), np.asarray(y_reg)

    if organ == "attention":
        X = []
        y_reg = []
        for rec in records:
            X.append((rec.state_features + rec.trajectory_features)[:24])
            if rec.multi_focus_weights:
                y_reg.append(_pad_vector(rec.multi_focus_weights, ATTENTION_WIDTH))
            elif rec.action_features:
                y_reg.append(_pad_vector(rec.action_features[0], ATTENTION_WIDTH))
            else:
                y_reg.append(_pad_vector([1.0], ATTENTION_WIDTH))
        return records, np.asarray(X), np.asarray(y_reg), np.asarray(y_reg)

    X = []
    y_reg = []
    for rec in records:
        X.append((rec.state_features + rec.trajectory_features)[:24])
        y_reg.append(rec.quality)
    return records, np.asarray(X), np.asarray(y_reg), np.asarray(y_reg)


def _consistency_check(records: Iterable[TraceRecord]) -> tuple[float, list[str]]:
    warnings: list[str] = []
    total = 0
    consistent = 0
    for rec in records:
        total += 1
        numeric_blocks = [rec.state_features, rec.trajectory_features, rec.multi_focus_weights]
        flat_values = [v for block in numeric_blocks for v in block]
        outcome_values = []
        metrics = rec.outcome.get("metrics") if isinstance(rec.outcome, dict) else None
        if isinstance(metrics, dict):
            outcome_values.extend(_safe_float(v) for v in metrics.values())
        quality = _safe_float(rec.quality)
        outcome_values.append(quality)
        values = flat_values + outcome_values
        if values and all(math.isfinite(v) for v in values) and all(0.0 <= v <= 1.0 for v in outcome_values):
            consistent += 1
        else:
            warnings.append(f"{rec.domain}/{rec.organ}/{rec.phase} session has out-of-range or non-finite scientific values")
    return (consistent / total) if total else 0.0, warnings[:10]


def _replay_coverage(records: Iterable[TraceRecord]) -> float:
    total = 0
    replayable = 0
    for rec in records:
        total += 1
        replay = rec.replay
        if (
            replay.get("generator")
            and isinstance(replay.get("seed"), int)
            and replay.get("scenarioId")
            and isinstance(replay.get("step"), int)
            and replay.get("simulatedTime")
        ):
            replayable += 1
    return (replayable / total) if total else 0.0


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _replay_identity_coverage(records: Iterable[TraceRecord]) -> float:
    total = 0
    covered = 0
    for rec in records:
        replay = rec.replay
        if replay.get("generator") != CHAL_ACCELERATOR_GENERATOR:
            continue
        total += 1
        record = replay.get("record")
        if not isinstance(record, dict):
            continue
        record_hash = record.get("recordHash")
        record_without_hash = {key: value for key, value in record.items() if key != "recordHash"}
        expected_hash = hashlib.sha256(_stable_json(record_without_hash).encode("utf-8")).hexdigest()
        candidate_refs = record_without_hash.get("candidateRefs")
        selected_ref = record_without_hash.get("selectedCandidateRef")
        quality = record_without_hash.get("quality")
        if (
            record_without_hash.get("schema") == "organ_training_replay.v1"
            and record_without_hash.get("generator") == CHAL_ACCELERATOR_GENERATOR
            and record_without_hash.get("domain") == rec.domain
            and record_without_hash.get("organ") == rec.organ
            and record_without_hash.get("phase") == rec.phase
            and record_without_hash.get("device") == f"chal://organs/{rec.domain}/{rec.organ}"
            and record_without_hash.get("route") == "organ_training_replay"
            and isinstance(candidate_refs, list)
            and bool(candidate_refs)
            and all(isinstance(ref, str) and ref for ref in candidate_refs)
            and isinstance(selected_ref, str)
            and selected_ref in candidate_refs
            and isinstance(record_without_hash.get("accepted"), bool)
            and isinstance(quality, (int, float))
            and math.isfinite(float(quality))
            and isinstance(record_hash, str)
            and record_hash == expected_hash
        ):
            covered += 1
    return (covered / total) if total else 0.0


def _valid_replay_identity(rec: TraceRecord) -> tuple[bool, str]:
    replay = rec.replay
    if replay.get("generator") != CHAL_ACCELERATOR_GENERATOR:
        return False, "not current CHAL accelerator generator"
    record = replay.get("record")
    if not isinstance(record, dict):
        return False, "missing replay.record"
    record_hash = record.get("recordHash")
    record_without_hash = {key: value for key, value in record.items() if key != "recordHash"}
    expected_hash = hashlib.sha256(_stable_json(record_without_hash).encode("utf-8")).hexdigest()
    candidate_refs = record_without_hash.get("candidateRefs")
    selected_ref = record_without_hash.get("selectedCandidateRef")
    quality = record_without_hash.get("quality")
    if record_without_hash.get("schema") != "organ_training_replay.v1":
        return False, "invalid replay record schema"
    if record_without_hash.get("generator") != CHAL_ACCELERATOR_GENERATOR:
        return False, "invalid replay record generator"
    if record_without_hash.get("domain") != rec.domain:
        return False, "domain mismatch"
    if record_without_hash.get("organ") != rec.organ:
        return False, "organ mismatch"
    if record_without_hash.get("phase") != rec.phase:
        return False, "phase mismatch"
    if record_without_hash.get("device") != f"chal://organs/{rec.domain}/{rec.organ}":
        return False, "device mismatch"
    if record_without_hash.get("route") != "organ_training_replay":
        return False, "route mismatch"
    if not isinstance(candidate_refs, list) or not candidate_refs:
        return False, "missing candidate refs"
    if not all(isinstance(ref, str) and ref for ref in candidate_refs):
        return False, "invalid candidate ref"
    if not isinstance(selected_ref, str) or selected_ref not in candidate_refs:
        return False, "selected candidate ref mismatch"
    if not isinstance(record_without_hash.get("accepted"), bool):
        return False, "missing accepted flag"
    if not isinstance(quality, (int, float)) or not math.isfinite(float(quality)):
        return False, "invalid quality"
    if not isinstance(record_hash, str) or record_hash != expected_hash:
        return False, "record hash mismatch"
    return True, ""


def _valid_chal_accelerator(rec: TraceRecord) -> tuple[bool, str]:
    replay = rec.replay
    if replay.get("generator") != CHAL_ACCELERATOR_GENERATOR:
        return False, "not current CHAL accelerator generator"
    chal = replay.get("chal") if isinstance(replay, dict) else None
    if not isinstance(chal, dict):
        return False, "missing replay.chal"
    expected_device = f"chal://organs/{rec.domain}/{rec.organ}"
    if not chal.get("frameId"):
        return False, "missing CHAL frame id"
    if not chal.get("parentFrameId"):
        return False, "missing CHAL parent frame id"
    if chal.get("device") != expected_device:
        return False, "CHAL device mismatch"
    if chal.get("role") != "organ_accelerator":
        return False, "CHAL role mismatch"
    if chal.get("route") != "organ_training_replay":
        return False, "CHAL route mismatch"
    if chal.get("outputRef") != f"{rec.domain}.{rec.organ}.{rec.phase}":
        return False, "CHAL output ref mismatch"
    return True, ""


def _valid_candidate_critic(rec: TraceRecord) -> tuple[bool, str]:
    replay = rec.replay
    if replay.get("generator") != CHAL_ACCELERATOR_GENERATOR:
        return False, "not current CHAL accelerator generator"
    chal = replay.get("chal") if isinstance(replay, dict) else None
    if not isinstance(chal, dict):
        return False, "missing replay.chal"
    candidate_refs = chal.get("candidateRefs")
    selected_ref = chal.get("selectedCandidateRef")
    critic = chal.get("criticFeedback")
    if not isinstance(candidate_refs, list) or not candidate_refs:
        return False, "missing CHAL candidate refs"
    if not all(isinstance(ref, str) and ref for ref in candidate_refs):
        return False, "invalid CHAL candidate ref"
    if not isinstance(selected_ref, str) or selected_ref not in candidate_refs:
        return False, "CHAL selected candidate mismatch"
    if not isinstance(critic, dict):
        return False, "missing critic feedback"
    if critic.get("source") != "teacher_trace_outcome":
        return False, "critic feedback source mismatch"
    if not isinstance(critic.get("feedbackRef"), str):
        return False, "missing critic feedback ref"
    if not isinstance(critic.get("accepted"), bool):
        return False, "missing critic accepted flag"
    if not isinstance(critic.get("quality"), (int, float)) or not math.isfinite(float(critic.get("quality"))):
        return False, "invalid critic quality"
    return True, ""


def _chal_accelerator_coverage(records: Iterable[TraceRecord]) -> float:
    total = 0
    bounded = 0
    for rec in records:
        if rec.replay.get("generator") != CHAL_ACCELERATOR_GENERATOR:
            continue
        total += 1
        chal = rec.replay.get("chal") if isinstance(rec.replay, dict) else None
        if not isinstance(chal, dict):
            continue
        device = chal.get("device")
        expected_device = f"chal://organs/{rec.domain}/{rec.organ}"
        if (
            chal.get("frameId")
            and chal.get("parentFrameId")
            and device == expected_device
            and chal.get("role") == "organ_accelerator"
            and chal.get("route") == "organ_training_replay"
            and chal.get("outputRef") == f"{rec.domain}.{rec.organ}.{rec.phase}"
        ):
            bounded += 1
    return (bounded / total) if total else 0.0


def _candidate_critic_coverage(records: Iterable[TraceRecord]) -> float:
    total = 0
    covered = 0
    for rec in records:
        if rec.replay.get("generator") != CHAL_ACCELERATOR_GENERATOR:
            continue
        total += 1
        chal = rec.replay.get("chal") if isinstance(rec.replay, dict) else None
        if not isinstance(chal, dict):
            continue
        candidate_refs = chal.get("candidateRefs")
        selected_ref = chal.get("selectedCandidateRef")
        critic = chal.get("criticFeedback")
        if (
            isinstance(candidate_refs, list)
            and bool(candidate_refs)
            and all(isinstance(ref, str) and ref for ref in candidate_refs)
            and isinstance(selected_ref, str)
            and selected_ref in candidate_refs
            and isinstance(critic, dict)
            and critic.get("source") == "teacher_trace_outcome"
            and isinstance(critic.get("feedbackRef"), str)
            and isinstance(critic.get("accepted"), bool)
            and isinstance(critic.get("quality"), (int, float))
            and math.isfinite(float(critic.get("quality")))
        ):
            covered += 1
    return (covered / total) if total else 0.0


def build_organ_replay_records(records: Iterable[TraceRecord]) -> list[dict[str, Any]]:
    replay_records: list[dict[str, Any]] = []
    for rec in records:
        if rec.replay.get("generator") != CHAL_ACCELERATOR_GENERATOR:
            continue
        identity_ok, _ = _valid_replay_identity(rec)
        chal_ok, _ = _valid_chal_accelerator(rec)
        candidate_ok, _ = _valid_candidate_critic(rec)
        if not (identity_ok and chal_ok and candidate_ok):
            continue
        source_record = rec.replay["record"]
        chal = rec.replay["chal"]
        critic = chal["criticFeedback"]
        compact = {
            "schema": "synthesus.organ_replay_trace.v1",
            "generator": CHAL_ACCELERATOR_GENERATOR,
            "sourceRecordHash": source_record["recordHash"],
            "seed": source_record["seed"],
            "scenarioId": source_record["scenarioId"],
            "step": source_record["step"],
            "simulatedTime": rec.replay.get("simulatedTime"),
            "domain": rec.domain,
            "organ": rec.organ,
            "phase": rec.phase,
            "device": chal["device"],
            "role": chal["role"],
            "route": chal["route"],
            "frameId": chal["frameId"],
            "parentFrameId": chal["parentFrameId"],
            "outputRef": chal["outputRef"],
            "candidateRefs": list(chal["candidateRefs"]),
            "selectedCandidateRef": chal["selectedCandidateRef"],
            "criticFeedbackRef": critic["feedbackRef"],
            "accepted": bool(critic["accepted"]),
            "quality": float(critic["quality"]),
        }
        compact["recordHash"] = hashlib.sha256(_stable_json(compact).encode("utf-8")).hexdigest()
        replay_records.append(compact)
    return replay_records


def build_organ_replay_integrity_scorecard(records: Iterable[TraceRecord]) -> OrganReplayIntegrityResult:
    failures: list[str] = []
    total = 0
    source_records = list(records)
    for idx, rec in enumerate(source_records):
        if rec.replay.get("generator") != CHAL_ACCELERATOR_GENERATOR:
            continue
        total += 1
        label = f"{idx}:{rec.domain}/{rec.organ}/{rec.phase}"
        for ok, reason in (
            _valid_replay_identity(rec),
            _valid_chal_accelerator(rec),
            _valid_candidate_critic(rec),
        ):
            if not ok:
                failures.append(f"{label}: {reason}")
    compact_records = build_organ_replay_records(source_records)
    for idx, record in enumerate(compact_records):
        record_hash = record.get("recordHash")
        record_without_hash = {key: value for key, value in record.items() if key != "recordHash"}
        expected_hash = hashlib.sha256(_stable_json(record_without_hash).encode("utf-8")).hexdigest()
        if record_hash != expected_hash:
            failures.append(f"compact:{idx}: record hash mismatch")
        if "state_features" in record or "action_features" in record or "trajectory_features" in record:
            failures.append(f"compact:{idx}: raw training features leaked into replay storage")
    if total != len(compact_records):
        failures.append(f"stored compact records {len(compact_records)} did not cover current CHAL records {total}")
    return OrganReplayIntegrityResult(
        schema="synthesus.organ_replay_integrity_scorecard.v1",
        passed=not failures,
        total_chal_records=total,
        stored_records=len(compact_records),
        failures=failures,
    )


def assert_organ_replay_integrity(scorecard: OrganReplayIntegrityResult) -> None:
    if not scorecard.passed:
        raise AssertionError("; ".join(scorecard.failures))


def _load_model(domain: str, organ: str):
    if joblib is None:
        raise RuntimeError("joblib is required to load trained models")
    model_path = MODELS_DIR / f"{domain}_{organ}.pkl"
    if not model_path.exists():
        return None, model_path
    return joblib.load(model_path), model_path


def evaluate_organ(domain: str, organ: str) -> OrganScorecard:
    records, X, y_primary, y_secondary = _build_dataset(domain, organ)
    model, model_path = _load_model(domain, organ)
    metric_name = _metric_name(organ)
    sci_consistency, warnings = _consistency_check(records)
    replay_coverage = _replay_coverage(records)
    replay_identity_coverage = _replay_identity_coverage(records)
    chal_accelerator_coverage = _chal_accelerator_coverage(records)
    candidate_critic_coverage = _candidate_critic_coverage(records)
    notes: list[str] = []

    if len(records) == 0:
        return OrganScorecard(
            domain=domain,
            organ=organ,
            trace_count=0,
            model_path=str(model_path),
            model_exists=model is not None,
            train_metric=None,
            validation_metric=None,
            baseline_metric=None,
            metric_name=metric_name,
            scientific_consistency=sci_consistency,
            replay_coverage=replay_coverage,
            replay_identity_coverage=replay_identity_coverage,
            chal_accelerator_coverage=chal_accelerator_coverage,
            candidate_critic_coverage=candidate_critic_coverage,
            consistency_warnings=warnings,
            notes=["No matching traces found."],
        )

    if model is None:
        notes.append("Model file missing; training trace exists but model not found.")
        return OrganScorecard(
            domain=domain,
            organ=organ,
            trace_count=len(records),
            model_path=str(model_path),
            model_exists=False,
            train_metric=None,
            validation_metric=None,
            baseline_metric=None,
            metric_name=metric_name,
            scientific_consistency=sci_consistency,
            replay_coverage=replay_coverage,
            replay_identity_coverage=replay_identity_coverage,
            chal_accelerator_coverage=chal_accelerator_coverage,
            candidate_critic_coverage=candidate_critic_coverage,
            consistency_warnings=warnings,
            notes=notes,
        )

    expected_width = int(getattr(model, "n_features_in_", X.shape[1] if len(records) else 0) or X.shape[1])
    X = _align_features(X, expected_width)

    if organ == "policy_prior":
        X_train, X_val, y_train, y_val = _split_data(X, y_primary)
        train_pred = model.predict(X_train)
        val_pred = model.predict(X_val)
        train_metric = float(accuracy_score(y_train, train_pred)) if accuracy_score is not None else None
        val_metric = float(accuracy_score(y_val, val_pred)) if accuracy_score is not None else None
        labels = y_train.tolist() if hasattr(y_train, "tolist") else list(y_train)
        baseline = None
        if labels and len(set(labels)) > 0:
            majority = max(set(labels), key=labels.count)
            baseline = float(sum(1 for label in labels if label == majority) / len(labels))
        if baseline is not None and val_metric is not None and val_metric < baseline:
            notes.append("Validation under baseline; trace diversity or feature quality should improve.")
        return OrganScorecard(
            domain=domain,
            organ=organ,
            trace_count=len(records),
            model_path=str(model_path),
            model_exists=True,
            train_metric=train_metric,
            validation_metric=val_metric,
            baseline_metric=baseline,
            metric_name=metric_name,
            scientific_consistency=sci_consistency,
            replay_coverage=replay_coverage,
            replay_identity_coverage=replay_identity_coverage,
            chal_accelerator_coverage=chal_accelerator_coverage,
            candidate_critic_coverage=candidate_critic_coverage,
            consistency_warnings=warnings,
            notes=notes,
        )

    if organ == "attention":
        X_train, X_val, y_train, y_val = _split_data(X, y_primary)
        train_pred = _collapse_to_scalar(model.predict(X_train))
        val_pred = _collapse_to_scalar(model.predict(X_val))
        train_target = _collapse_to_scalar(y_train)
        val_target = _collapse_to_scalar(y_val)
        train_metric = float(mean_squared_error(train_target, train_pred)) if mean_squared_error is not None else None
        val_metric = float(mean_squared_error(val_target, val_pred)) if mean_squared_error is not None else None
        baseline_pred = np.full_like(val_target, float(np.mean(train_target)) if len(train_target) else 0.0, dtype=float)
        baseline = float(mean_squared_error(val_target, baseline_pred)) if mean_squared_error is not None else None
        if baseline is not None and val_metric is not None and val_metric > baseline:
            notes.append("Validation above mean baseline; further trace variety may still be useful.")
        return OrganScorecard(
            domain=domain,
            organ=organ,
            trace_count=len(records),
            model_path=str(model_path),
            model_exists=True,
            train_metric=train_metric,
            validation_metric=val_metric,
            baseline_metric=baseline,
            metric_name=metric_name,
            scientific_consistency=sci_consistency,
            replay_coverage=replay_coverage,
            replay_identity_coverage=replay_identity_coverage,
            chal_accelerator_coverage=chal_accelerator_coverage,
            candidate_critic_coverage=candidate_critic_coverage,
            consistency_warnings=warnings,
            notes=notes,
        )

    X_train, X_val, y_train, y_val = _split_data(X, y_primary)
    train_pred = model.predict(X_train)
    val_pred = model.predict(X_val)
    train_metric = float(r2_score(y_train, train_pred)) if r2_score is not None and len(set(y_train.tolist())) > 1 else 0.0
    val_metric = float(r2_score(y_val, val_pred)) if r2_score is not None and len(set(y_val.tolist())) > 1 else 0.0
    baseline_pred = np.full_like(y_val, float(np.mean(y_train)) if len(y_train) else 0.0, dtype=float)
    baseline = float(r2_score(y_val, baseline_pred)) if r2_score is not None and len(set(y_val.tolist())) > 1 else 0.0
    if val_metric < baseline:
        notes.append("Validation under mean baseline; further trace variety may still be useful.")

    return OrganScorecard(
        domain=domain,
        organ=organ,
        trace_count=len(records),
        model_path=str(model_path),
        model_exists=True,
        train_metric=train_metric,
        validation_metric=val_metric,
        baseline_metric=baseline,
        metric_name=metric_name,
        scientific_consistency=sci_consistency,
        replay_coverage=replay_coverage,
        replay_identity_coverage=replay_identity_coverage,
        chal_accelerator_coverage=chal_accelerator_coverage,
        candidate_critic_coverage=candidate_critic_coverage,
        consistency_warnings=warnings,
        notes=notes,
    )


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def render_markdown(scorecards: list[OrganScorecard]) -> str:
    lines = [
        "# Synthesus ML Organ Evaluation Scorecard",
        "",
        "Fictional narrative traces are acceptable input as long as scientific/math fields are numeric, bounded, and internally consistent.",
        "",
        "| Domain | Organ | Traces | Metric | Train | Validation | Baseline | Consistency | Replay / Identity / CHAL / Candidate-Critic |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in scorecards:
        lines.append(
            f"| {s.domain} | {s.organ} | {s.trace_count} | {s.metric_name} | {_format_metric(s.train_metric)} | {_format_metric(s.validation_metric)} | {_format_metric(s.baseline_metric)} | {s.scientific_consistency:.2%} | {s.replay_coverage:.2%} / ID {s.replay_identity_coverage:.2%} / CHAL {s.chal_accelerator_coverage:.2%} / CC {s.candidate_critic_coverage:.2%} |"
        )
    lines.append("")
    for s in scorecards:
        lines.append(f"## {s.domain}/{s.organ}")
        lines.append(f"- Model: `{s.model_path}`")
        lines.append(f"- Model exists: {'yes' if s.model_exists else 'no'}")
        lines.append(f"- Scientific consistency: {s.scientific_consistency:.2%}")
        lines.append(f"- Replay metadata coverage: {s.replay_coverage:.2%}")
        lines.append(f"- Replay identity coverage: {s.replay_identity_coverage:.2%}")
        lines.append(f"- CHAL accelerator frame coverage: {s.chal_accelerator_coverage:.2%}")
        lines.append(f"- Candidate/critic feedback coverage: {s.candidate_critic_coverage:.2%}")
        if s.consistency_warnings:
            lines.append("- Warnings:")
            for warning in s.consistency_warnings:
                lines.append(f"  - {warning}")
        if s.notes:
            lines.append("- Notes:")
            for note in s.notes:
                lines.append(f"  - {note}")
        lines.append("")
    return "\n".join(lines)


def evaluate_quality_gate(
    scorecards: list[OrganScorecard],
    *,
    min_replay_coverage: float | None = None,
    min_replay_identity_coverage: float | None = None,
    min_chal_accelerator_coverage: float | None = None,
    min_candidate_critic_coverage: float | None = None,
    min_scientific_consistency: float | None = None,
    fail_under_baseline: bool = False,
    fail_missing_models: bool = False,
) -> QualityGateResult:
    failures: list[str] = []

    for scorecard in scorecards:
        label = f"{scorecard.domain}/{scorecard.organ}"

        if fail_missing_models and not scorecard.model_exists:
            failures.append(f"{label} model is missing: {scorecard.model_path}")

        if min_replay_coverage is not None and scorecard.replay_coverage < min_replay_coverage:
            failures.append(
                f"{label} replay coverage {scorecard.replay_coverage:.2%} is below required {min_replay_coverage:.2%}"
            )

        if (
            min_replay_identity_coverage is not None
            and scorecard.replay_identity_coverage < min_replay_identity_coverage
        ):
            failures.append(
                f"{label} replay identity coverage {scorecard.replay_identity_coverage:.2%} is below required {min_replay_identity_coverage:.2%}"
            )

        if (
            min_chal_accelerator_coverage is not None
            and scorecard.chal_accelerator_coverage < min_chal_accelerator_coverage
        ):
            failures.append(
                f"{label} CHAL accelerator coverage {scorecard.chal_accelerator_coverage:.2%} is below required {min_chal_accelerator_coverage:.2%}"
            )

        if (
            min_candidate_critic_coverage is not None
            and scorecard.candidate_critic_coverage < min_candidate_critic_coverage
        ):
            failures.append(
                f"{label} candidate/critic coverage {scorecard.candidate_critic_coverage:.2%} is below required {min_candidate_critic_coverage:.2%}"
            )

        if min_scientific_consistency is not None and scorecard.scientific_consistency < min_scientific_consistency:
            failures.append(
                f"{label} scientific consistency {scorecard.scientific_consistency:.2%} is below required {min_scientific_consistency:.2%}"
            )

        if (
            fail_under_baseline
            and scorecard.validation_metric is not None
            and scorecard.baseline_metric is not None
        ):
            if scorecard.metric_name == "mse":
                under_baseline = scorecard.validation_metric > scorecard.baseline_metric
            else:
                under_baseline = scorecard.validation_metric < scorecard.baseline_metric
            if under_baseline:
                failures.append(
                    f"{label} validation {scorecard.validation_metric:.4f} failed baseline {scorecard.baseline_metric:.4f} ({scorecard.metric_name})"
                )

    return QualityGateResult(
        passed=not failures,
        failures=failures,
        min_replay_coverage=min_replay_coverage,
        min_replay_identity_coverage=min_replay_identity_coverage,
        min_chal_accelerator_coverage=min_chal_accelerator_coverage,
        min_candidate_critic_coverage=min_candidate_critic_coverage,
        min_scientific_consistency=min_scientific_consistency,
        fail_under_baseline=fail_under_baseline,
        fail_missing_models=fail_missing_models,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate trace-trained Synthesus ML organs")
    parser.add_argument("--domain", type=str, choices=["chat", "sysops", "gm"], default="", help="Optional domain filter")
    parser.add_argument("--write-json", action="store_true", default=True, help="Write JSON scorecard")
    parser.add_argument("--write-md", action="store_true", default=True, help="Write Markdown scorecard")
    parser.add_argument("--min-replay-coverage", type=float, default=None, help="Fail if any organ replay metadata coverage is below this 0.0-1.0 threshold")
    parser.add_argument("--min-replay-identity-coverage", type=float, default=None, help="Fail if any organ replay trace lacks a valid compact identity hash")
    parser.add_argument("--min-chal-accelerator-coverage", type=float, default=None, help="Fail if any organ replay trace lacks CHAL accelerator frame metadata")
    parser.add_argument("--min-candidate-critic-coverage", type=float, default=None, help="Fail if any CHAL organ replay trace lacks candidate references and critic feedback metadata")
    parser.add_argument("--min-scientific-consistency", type=float, default=None, help="Fail if any organ numeric consistency is below this 0.0-1.0 threshold")
    parser.add_argument("--fail-under-baseline", action="store_true", help="Fail when validation performance is worse than the relevant baseline")
    parser.add_argument("--fail-missing-models", action="store_true", help="Fail when traces exist but a trained model file is missing")
    parser.add_argument("--replay-jsonl", type=Path, default=None, help="Write compact CHAL organ replay records to this JSONL path")
    parser.add_argument("--replay-integrity-json", type=Path, default=None, help="Write compact CHAL organ replay integrity scorecard JSON")
    parser.add_argument("--fail-on-organ-replay-integrity", action="store_true", help="Fail when compact CHAL organ replay storage is incomplete or malformed")
    args = parser.parse_args()

    if np is None or joblib is None or accuracy_score is None or r2_score is None or train_test_split is None or mean_squared_error is None:
        logger.error("Missing evaluation dependencies. Install numpy, scikit-learn, and joblib.")
        return 1

    if not TRACE_FILE.exists():
        logger.error(f"Missing trace file: {TRACE_FILE}")
        return 1

    organs = ["policy_prior", "risk_outcome", "attention"]
    domains = [args.domain] if args.domain else ["chat", "sysops", "gm"]
    scorecards = [evaluate_organ(domain, organ) for domain in domains for organ in organs]
    trace_records = [
        rec
        for domain in domains
        for organ in organs
        for rec in _domain_records(domain, organ, "planning" if organ in {"policy_prior", "attention"} else "output")
    ]
    organ_replay_records = build_organ_replay_records(trace_records)
    organ_replay_integrity = build_organ_replay_integrity_scorecard(trace_records)

    payload = {
        "trace_file": str(TRACE_FILE),
        "model_dir": str(MODELS_DIR),
        "fiction_policy": "Narrative fiction is accepted; scientific/math fields must stay bounded and internally consistent.",
        "scorecards": [asdict(s) for s in scorecards],
        "organ_replay_integrity": asdict(organ_replay_integrity),
    }

    quality_gate = evaluate_quality_gate(
        scorecards,
        min_replay_coverage=args.min_replay_coverage,
        min_replay_identity_coverage=args.min_replay_identity_coverage,
        min_chal_accelerator_coverage=args.min_chal_accelerator_coverage,
        min_candidate_critic_coverage=args.min_candidate_critic_coverage,
        min_scientific_consistency=args.min_scientific_consistency,
        fail_under_baseline=args.fail_under_baseline,
        fail_missing_models=args.fail_missing_models,
    )
    payload["quality_gate"] = asdict(quality_gate)

    if args.write_json:
        REPORT_JSON.write_text(json.dumps(payload, indent=2))
    if args.write_md:
        REPORT_MD.write_text(render_markdown(scorecards))
    if args.replay_jsonl:
        args.replay_jsonl.parent.mkdir(parents=True, exist_ok=True)
        args.replay_jsonl.write_text(
            "\n".join(json.dumps(record, sort_keys=True) for record in organ_replay_records) + "\n"
            if organ_replay_records
            else ""
        )
    if args.replay_integrity_json:
        args.replay_integrity_json.parent.mkdir(parents=True, exist_ok=True)
        args.replay_integrity_json.write_text(json.dumps(asdict(organ_replay_integrity), indent=2, sort_keys=True))

    logger.info(f"Wrote {REPORT_JSON}")
    logger.info(f"Wrote {REPORT_MD}")
    for s in scorecards:
        logger.info(
            f"{s.domain}/{s.organ}: train={_format_metric(s.train_metric)} validation={_format_metric(s.validation_metric)} baseline={_format_metric(s.baseline_metric)} consistency={s.scientific_consistency:.2%} replay={s.replay_coverage:.2%} replay_identity={s.replay_identity_coverage:.2%} chal_accelerator={s.chal_accelerator_coverage:.2%} candidate_critic={s.candidate_critic_coverage:.2%}"
        )
    if not quality_gate.passed:
        for failure in quality_gate.failures:
            logger.error(f"Quality gate failed: {failure}")
        return 1
    if args.fail_on_organ_replay_integrity and not organ_replay_integrity.passed:
        for failure in organ_replay_integrity.failures:
            logger.error(f"Organ replay integrity failed: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
