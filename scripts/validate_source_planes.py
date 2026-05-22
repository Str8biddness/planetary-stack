#!/usr/bin/env python3
"""Validate source/pipeline/pattern/synthetic planes for the Knowledge Cloud repo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_PATHS = [
    "sources/datasets.yaml",
    "sources/jeopardy.yaml",
    "sources/conceptnet.yaml",
    "pipelines/ingest/kaggle_loader.py",
    "pipelines/build/kn_populator.py",
    "pipelines/build/run_population.py",
    "pipelines/build/swarm_embedder.py",
    "pipelines/publish/cloud_sync.py",
    "synthetic/lore_forge/lore_forge.py",
    "synthetic/generation_scripts/learn_transitions.py",
    "patterns/global/initial_patterns.json",
    "patterns/characters/registry.json",
    "grounding_corpus/kaggle_grounding_v1.txt",
    "support_models/vocab_general.pkl",
]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors: list[str] = []

    for rel in REQUIRED_PATHS:
        path = root / rel
        if not path.exists():
            errors.append(f"missing required path: {rel}")
        elif path.is_file() and path.stat().st_size <= 0:
            errors.append(f"empty required file: {rel}")

    # JSON structural smoke checks.
    for rel in ["patterns/global/initial_patterns.json", "patterns/characters/registry.json"]:
        path = root / rel
        if path.exists():
            try:
                load_json(path)
            except Exception as exc:
                errors.append(f"invalid json {rel}: {exc}")

    char_dir = root / "patterns/characters"
    pattern_files = sorted(char_dir.glob("*/patterns.json")) if char_dir.exists() else []
    if not pattern_files:
        errors.append("no character pattern files found under patterns/characters/*/patterns.json")
    for path in pattern_files:
        if path.stat().st_size < 1000:
            errors.append(f"suspiciously small character pattern file: {path.relative_to(root)}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(f"source planes ok: {len(REQUIRED_PATHS)} required paths, {len(pattern_files)} character pattern banks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
