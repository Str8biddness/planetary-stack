"""Source-plane structural validation for the Knowledge Cloud repository."""

from __future__ import annotations

import json
from dataclasses import dataclass
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


@dataclass(frozen=True)
class SourcePlaneValidation:
    required_paths: int
    character_pattern_banks: int
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_source_planes(root: str | Path = ".") -> SourcePlaneValidation:
    root_path = Path(root).resolve()
    errors: list[str] = []
    for rel in REQUIRED_PATHS:
        path = root_path / rel
        if not path.exists():
            errors.append(f"missing required path: {rel}")
        elif path.is_file() and path.stat().st_size <= 0:
            errors.append(f"empty required file: {rel}")

    for rel in ["patterns/global/initial_patterns.json", "patterns/characters/registry.json"]:
        path = root_path / rel
        if path.exists():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"invalid json {rel}: {exc}")

    char_dir = root_path / "patterns/characters"
    pattern_files = sorted(char_dir.glob("*/patterns.json")) if char_dir.exists() else []
    if not pattern_files:
        errors.append("no character pattern files found under patterns/characters/*/patterns.json")
    for path in pattern_files:
        if path.stat().st_size < 1000:
            errors.append(f"suspiciously small character pattern file: {path.relative_to(root_path)}")

    return SourcePlaneValidation(
        required_paths=len(REQUIRED_PATHS),
        character_pattern_banks=len(pattern_files),
        errors=tuple(errors),
    )
