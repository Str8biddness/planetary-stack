"""Source-plane structural validation for the Knowledge Cloud repository."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

REQUIRED_PATHS = [
    "sources/datasets.yaml",
    "sources/jeopardy.yaml",
    "sources/conceptnet.yaml",
    "pipelines/ingest/kaggle_loader.py",
    "pipelines/build/kn_populator.py",
    "pipelines/build/run_population.py",
    "pipelines/build/swarm_embedder.py",
    "pipelines/publish/cloud_sync.py",
    "pipelines/publish/manifest_manager.py",
    "patterns/global/initial_patterns.json",
    "patterns/characters/registry.json",
    "synthetic/lore_forge/lore_forge.py",
    "synthetic/generation_scripts/learn_transitions.py",
    "synthetic/generation_scripts/mass_generate_entries.py",
    "corpus/hardware_blueprints/INDEX.md",
    "corpus/hardware_blueprints/schema.json",
    "corpus/hardware_blueprints/seeds/wikipedia_seeds.yaml",
    "corpus/hardware_blueprints/seeds/openalex_queries.yaml",
    "corpus/emulation/INDEX.md",
    "corpus/emulation/schema.json",
    "corpus/emulation/seeds/wikipedia_seeds.yaml",
    "corpus/emulation/seeds/arxiv_queries.yaml",
    "pipelines/ingest_corpus/wikipedia_fetcher.py",
    "pipelines/ingest_corpus/papers_fetcher.py",
    "pipelines/ingest_corpus/corpus_loader.py",
]


@dataclass(frozen=True)
class SourcePlaneValidation:
    required_paths: int
    character_pattern_banks: int
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def _validate_license_block(data: dict, rel: str, errors: list[str]) -> None:
    license_block = data.get("license")
    if not isinstance(license_block, dict):
        errors.append(f"source manifest missing license block: {rel}")
        return
    spdx = license_block.get("spdx")
    notes = license_block.get("notes")
    if not isinstance(spdx, str) or not spdx.strip():
        errors.append(f"source manifest missing license.spdx: {rel}")
    if not isinstance(notes, str) or not notes.strip():
        errors.append(f"source manifest missing license.notes: {rel}")


def _validate_source_manifest_yaml(
    path: Path,
    root_path: Path,
    errors: list[str],
    pending_ids: dict[str, str],
) -> None:
    rel = path.relative_to(root_path).as_posix()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid yaml {rel}: {exc}")
        return
    if not isinstance(data, dict):
        errors.append(f"source manifest is not a mapping: {rel}")
        return
    if path.name == "datasets.yaml":
        return

    for field in ("version", "id", "name", "source_type"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"source manifest missing {field}: {rel}")

    _validate_license_block(data, rel, errors)

    loader = data.get("loader")
    if not isinstance(loader, str) or "::" not in loader:
        errors.append(f"source manifest missing loader module path: {rel}")

    if data.get("default_enabled", True) is not False:
        has_fetch_target = any(
            key in data for key in ("url", "repository", "files", "docs")
        )
        if not has_fetch_target:
            errors.append(f"enabled source manifest missing upstream locator: {rel}")

    pending = data.get("pending", [])
    if pending is None:
        pending = []
    if not isinstance(pending, list):
        errors.append(f"source manifest pending field must be a list: {rel}")
        return
    for index, item in enumerate(pending):
        if not isinstance(item, dict):
            errors.append(f"pending source entry is not a mapping: {rel}[{index}]")
            continue
        entry_id = item.get("id")
        if not isinstance(entry_id, str) or not entry_id.strip():
            errors.append(f"pending source entry missing id: {rel}[{index}]")
        else:
            previous = pending_ids.setdefault(entry_id, f"{rel}[{index}]")
            if previous != f"{rel}[{index}]":
                errors.append(
                    f"duplicate pending source id: {entry_id} in {rel}[{index}] "
                    f"already declared in {previous}"
                )
        entry_license = item.get("license")
        if not isinstance(entry_license, dict):
            errors.append(f"pending source entry missing license block: {rel}[{index}]")
            continue
        spdx = entry_license.get("spdx")
        notes = entry_license.get("notes")
        if not isinstance(spdx, str) or not spdx.strip():
            errors.append(f"pending source entry missing license.spdx: {rel}[{index}]")
        if not isinstance(notes, str) or not notes.strip():
            errors.append(f"pending source entry missing license.notes: {rel}[{index}]")
        rebuild_command = item.get("rebuild_command")
        if not isinstance(rebuild_command, str) or not rebuild_command.strip():
            errors.append(f"pending source entry missing rebuild_command: {rel}[{index}]")
        has_pending_locator = any(
            isinstance(item.get(key), str) and item.get(key, "").strip()
            for key in ("repo", "url", "repository", "dataset")
        )
        has_pending_files = isinstance(item.get("files"), list) and bool(item.get("files"))
        if not has_pending_locator and not has_pending_files:
            errors.append(f"pending source entry missing upstream locator: {rel}[{index}]")


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

    sources_dir = root_path / "sources"
    pending_ids: dict[str, str] = {}
    if sources_dir.exists():
        for path in sorted(sources_dir.glob("*.yaml")):
            _validate_source_manifest_yaml(path, root_path, errors, pending_ids)

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
