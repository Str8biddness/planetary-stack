#!/usr/bin/env python3
"""
Synthesus Self-Improvement Pipeline

Complete automated feedback loop:
1. Harvest traces from production query logs and user feedback files
2. Generate synthetic training traces for all 9 organ×domain pairs
3. Train all organs (policy_prior, risk_outcome, attention) for all domains (chat, sysops, gm)
4. Evaluate trained models with trace-driven scorecards
5. Log results to logs/self_improvement_log.json

Usage:
    python scripts/self_improve.py
    python scripts/self_improve.py --skip-synthetic   # Only use real traces
    python scripts/self_improve.py --dry-run           # Preview without training
"""

from __future__ import annotations

import json
import logging
import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("self_improve")

REPO_ROOT = Path(__file__).resolve().parent.parent
TRACE_FILE = REPO_ROOT / "logs" / "teacher_traces.jsonl"
FEEDBACK_DIR = REPO_ROOT / "data" / "feedback"
LOG_FILE = REPO_ROOT / "logs" / "self_improvement_log.json"
MODELS_DIR = REPO_ROOT / "data" / "models"

DOMAINS = ["chat", "sysops", "gm"]
ORGANS = ["policy_prior", "risk_outcome", "attention"]

# ---------------------------------------------------------------------------
# Phase 1: Harvest real feedback into trace format
# ---------------------------------------------------------------------------

def _harvest_feedback() -> list[dict]:
    """Convert data/feedback/*.json files into trace-compatible records."""
    traces: list[dict] = []
    if not FEEDBACK_DIR.exists():
        logger.info("No feedback directory found, skipping feedback harvest.")
        return traces

    files = sorted(FEEDBACK_DIR.glob("*.json"))
    logger.info(f"Found {len(files)} feedback files.")

    for fp in files:
        try:
            fb = json.loads(fp.read_text())
        except Exception:
            continue

        rating = fb.get("rating", 3)
        quality = rating / 5.0 if isinstance(rating, (int, float)) else 0.5
        query = fb.get("query", "")
        session_id = fb.get("session_id", "unknown")

        # Infer domain from query text
        domain = "chat"
        lower_q = query.lower()
        if any(kw in lower_q for kw in ("restart", "deploy", "scale", "latency", "disk", "node", "service")):
            domain = "sysops"
        elif any(kw in lower_q for kw in ("tavern", "npc", "attack", "explore", "dungeon", "quest")):
            domain = "gm"

        # Generate traces for all 3 organs from this feedback
        for organ in ORGANS:
            phase = "planning" if organ in {"policy_prior", "attention"} else "output"
            traces.append({
                "sessionId": session_id,
                "timestamp": fb.get("timestamp", datetime.now(timezone.utc).isoformat()),
                "phase": phase,
                "domain": domain,
                "organ": organ,
                "stateFeatures": {
                    "topicCount": len(query.split()) / 10.0,
                    "lastClarification": 0.0,
                    "unresolvedQuestions": 0.0,
                    "confusion": max(0, 1.0 - quality),
                    "safety": 1.0,
                    "frustration": max(0, 0.5 - quality),
                    "avgHostErrorRate": random.uniform(0, 0.1) if domain == "sysops" else 0.0,
                    "avgServiceLatency": random.uniform(50, 200) / 1000 if domain == "sysops" else 0.0,
                    "criticalIncidents": 0.0,
                    "unresolvedIncidents": 0.0,
                    "npcCount": random.randint(2, 8) / 10.0 if domain == "gm" else 0.0,
                    "combatActive": 0.0,
                },
                "actionFeatures": [
                    {"dense": [random.uniform(0, 1) for _ in range(10)]}
                    for _ in range(random.randint(2, 5))
                ],
                "chosenActionIndex": 0,
                "organOutputs": {
                    "attentionWeights": [random.uniform(0, 1) for _ in range(10)],
                },
                "trajectoryFeatures": {
                    "confusionRate": max(0, 1.0 - quality),
                    "safetyRate": 1.0,
                    "resolution": quality,
                    "turnBalance": 0.5,
                    "incidentRate": 0.0,
                    "actionRate": 0.5,
                    "deployRate": 0.0,
                    "stability": quality,
                    "spawnRate": 0.0,
                    "combatRate": 0.0,
                    "npcTickRate": 0.0,
                },
                "outcome": {
                    "quality": quality,
                    "metrics": {
                        "responseQuality": quality,
                        "safetyScore": 1.0,
                    },
                },
            })

    logger.info(f"Harvested {len(traces)} traces from {len(files)} feedback files.")
    return traces


# ---------------------------------------------------------------------------
# Phase 2: Generate synthetic training traces for coverage
# ---------------------------------------------------------------------------

def _generate_synthetic_traces(count_per_pair: int = 30) -> list[dict]:
    """Generate well-distributed synthetic traces for all domain/organ pairs."""
    traces: list[dict] = []
    rng = random.Random(42)

    for domain in DOMAINS:
        for organ in ORGANS:
            phase = "planning" if organ in {"policy_prior", "attention"} else "output"

            for i in range(count_per_pair):
                quality = rng.uniform(0.3, 1.0)
                confusion = max(0, 1.0 - quality + rng.uniform(-0.1, 0.1))

                state = {
                    "topicCount": rng.uniform(0.1, 1.0),
                    "lastClarification": rng.choice([0.0, 1.0]),
                    "unresolvedQuestions": rng.uniform(0, 0.5),
                    "confusion": confusion,
                    "safety": rng.uniform(0.8, 1.0),
                    "frustration": max(0, confusion - 0.3),
                    "avgHostErrorRate": rng.uniform(0, 0.3) if domain == "sysops" else 0.0,
                    "avgServiceLatency": rng.uniform(0.05, 0.5) if domain == "sysops" else 0.0,
                    "criticalIncidents": rng.choice([0.0, 0.0, 0.0, 1.0]) if domain == "sysops" else 0.0,
                    "unresolvedIncidents": rng.uniform(0, 0.3) if domain == "sysops" else 0.0,
                    "npcCount": rng.uniform(0.1, 0.8) if domain == "gm" else 0.0,
                    "combatActive": rng.choice([0.0, 1.0]) if domain == "gm" else 0.0,
                }

                n_actions = rng.randint(2, 6)
                actions = [
                    {"dense": [rng.uniform(0, 1) for _ in range(10)]}
                    for _ in range(n_actions)
                ]

                traj = {
                    "confusionRate": confusion * rng.uniform(0.5, 1.2),
                    "safetyRate": rng.uniform(0.8, 1.0),
                    "resolution": quality * rng.uniform(0.7, 1.0),
                    "turnBalance": rng.uniform(0.3, 0.7),
                    "incidentRate": rng.uniform(0, 0.2) if domain == "sysops" else 0.0,
                    "actionRate": rng.uniform(0.3, 0.8),
                    "deployRate": rng.uniform(0, 0.3) if domain == "sysops" else 0.0,
                    "stability": quality * rng.uniform(0.8, 1.0),
                    "spawnRate": rng.uniform(0, 0.3) if domain == "gm" else 0.0,
                    "combatRate": rng.uniform(0, 0.4) if domain == "gm" else 0.0,
                    "npcTickRate": rng.uniform(0, 0.5) if domain == "gm" else 0.0,
                }

                traces.append({
                    "sessionId": f"synth-{domain}-{organ}-{i}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "phase": phase,
                    "domain": domain,
                    "organ": organ,
                    "stateFeatures": state,
                    "actionFeatures": actions,
                    "chosenActionIndex": rng.randint(0, n_actions - 1),
                    "organOutputs": {
                        "attentionWeights": [rng.uniform(0, 1) for _ in range(10)],
                    },
                    "trajectoryFeatures": traj,
                    "outcome": {
                        "quality": quality,
                        "metrics": {
                            "responseQuality": quality,
                            "safetyScore": rng.uniform(0.85, 1.0),
                        },
                    },
                })

    logger.info(f"Generated {len(traces)} synthetic traces ({count_per_pair} per domain/organ pair).")
    return traces


# ---------------------------------------------------------------------------
# Phase 3: Write traces & train
# ---------------------------------------------------------------------------

def _write_traces(traces: list[dict]) -> int:
    """Write trace records to the JSONL file."""
    TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACE_FILE, "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t) + "\n")
    logger.info(f"Wrote {len(traces)} traces to {TRACE_FILE}")
    return len(traces)


def _train_all_organs() -> dict[str, dict]:
    """Train all 9 organ models and return metrics."""
    import importlib.util
    train_triad_spec = importlib.util.spec_from_file_location(
        "train_triad", str(REPO_ROOT / "scripts" / "train_triad.py")
    )
    train_triad_mod = importlib.util.module_from_spec(train_triad_spec)
    train_triad_spec.loader.exec_module(train_triad_mod)
    train_organ = train_triad_mod.train_organ
    results: dict[str, dict] = {}

    for domain in DOMAINS:
        for organ in ORGANS:
            key = f"{domain}_{organ}"
            t0 = time.time()
            try:
                train_organ(domain, organ)
                model_path = MODELS_DIR / f"{key}.pkl"
                results[key] = {
                    "status": "success",
                    "model_size_bytes": model_path.stat().st_size if model_path.exists() else 0,
                    "duration_s": round(time.time() - t0, 2),
                }
            except Exception as e:
                logger.error(f"Training failed for {key}: {e}")
                results[key] = {
                    "status": "error",
                    "error": str(e),
                    "duration_s": round(time.time() - t0, 2),
                }

    return results


# ---------------------------------------------------------------------------
# Phase 4: Evaluate
# ---------------------------------------------------------------------------

def _run_evaluation() -> dict | None:
    """Run the evaluation harness and return the scorecard."""
    try:
        import importlib.util
        eval_spec = importlib.util.spec_from_file_location(
            "evaluate_organs", str(REPO_ROOT / "scripts" / "evaluate_organs.py")
        )
        eval_mod = importlib.util.module_from_spec(eval_spec)
        eval_spec.loader.exec_module(eval_mod)
        eval_mod.main()
        scorecard_path = REPO_ROOT / "logs" / "organ_evaluation_scorecard.json"
        if scorecard_path.exists():
            return json.loads(scorecard_path.read_text())
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
    return None


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_self_improvement(skip_synthetic: bool = False, dry_run: bool = False) -> dict:
    """Execute the full self-improvement pipeline."""
    logger.info("=" * 60)
    logger.info("SYNTHESUS SELF-IMPROVEMENT PIPELINE")
    logger.info("=" * 60)
    t0 = time.time()

    # Phase 1: Harvest real feedback
    real_traces = _harvest_feedback()

    # Phase 2: Generate synthetic traces (for coverage)
    synthetic_traces = [] if skip_synthetic else _generate_synthetic_traces(count_per_pair=50)

    all_traces = real_traces + synthetic_traces
    logger.info(f"Total traces: {len(all_traces)} (real={len(real_traces)}, synthetic={len(synthetic_traces)})")

    if dry_run:
        logger.info("DRY RUN — skipping write/train/evaluate")
        return {
            "status": "dry_run",
            "real_traces": len(real_traces),
            "synthetic_traces": len(synthetic_traces),
        }

    # Phase 3: Write & train
    _write_traces(all_traces)
    training_results = _train_all_organs()

    # Phase 4: Evaluate
    evaluation = _run_evaluation()

    # Phase 5: Log
    elapsed = time.time() - t0
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_s": round(elapsed, 2),
        "real_traces": len(real_traces),
        "synthetic_traces": len(synthetic_traces),
        "total_traces": len(all_traces),
        "training_results": training_results,
        "evaluation_summary": evaluation.get("scorecards", []) if evaluation else [],
        "models_trained": sum(1 for r in training_results.values() if r["status"] == "success"),
        "models_failed": sum(1 for r in training_results.values() if r["status"] == "error"),
    }

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Append to log history
    history: list = []
    if LOG_FILE.exists():
        try:
            history = json.loads(LOG_FILE.read_text())
        except Exception:
            pass
    history.append(log_entry)
    LOG_FILE.write_text(json.dumps(history, indent=2))

    logger.info("=" * 60)
    logger.info(f"Self-improvement complete in {elapsed:.1f}s")
    logger.info(f"  Models trained: {log_entry['models_trained']}/9")
    logger.info(f"  Models failed:  {log_entry['models_failed']}/9")
    logger.info(f"  Log saved to:   {LOG_FILE}")
    logger.info("=" * 60)

    return log_entry


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Synthesus Self-Improvement Pipeline")
    parser.add_argument("--skip-synthetic", action="store_true", help="Only use real traces")
    parser.add_argument("--dry-run", action="store_true", help="Preview without training")
    args = parser.parse_args()
    run_self_improvement(skip_synthetic=args.skip_synthetic, dry_run=args.dry_run)
