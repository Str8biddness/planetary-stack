from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.knowledge_cloud import KnowledgeCloud, KnowledgeEntry
from knowledge.runtime_mount import (
    knowledge_root_candidates,
    resolve_knowledge_root,
)


def test_monorepo_artifacts_have_priority(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "apps" / "synthesus" / "runtime"
    runtime_root.mkdir(parents=True)
    artifact_root = tmp_path / "knowledge" / "knowledge-cloud" / "artifacts"
    artifact_root.mkdir(parents=True)
    (artifact_root / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("SYNTHESUS_KNOWLEDGE_ROOT", raising=False)

    assert knowledge_root_candidates(runtime_root)[0] == artifact_root
    assert resolve_knowledge_root(runtime_root, required=True) == artifact_root


def test_invalid_explicit_root_fails_loudly(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configured = tmp_path / "missing-artifacts"
    monkeypatch.setenv("SYNTHESUS_KNOWLEDGE_ROOT", str(configured))

    with pytest.raises(FileNotFoundError, match="manifest.json"):
        resolve_knowledge_root(tmp_path / "runtime", required=False)


def test_read_only_base_persists_only_to_evolution_overlay(tmp_path: Path) -> None:
    base = tmp_path / "artifacts" / "knowledge_cloud"
    base.mkdir(parents=True)
    world_lore = base / "world_lore.json"
    original = {
        "version": "1",
        "entries": [
            {
                "entity_id": "duke_aldric",
                "entity": "Duke Aldric",
                "description": "Duke Aldric rules Ironhaven.",
                "facts": ["Has ruled for 22 years"],
                "aliases": ["the duke"],
            }
        ],
    }
    world_lore.write_text(json.dumps(original), encoding="utf-8")
    overlay = tmp_path / "writeback" / "evolution.json"

    cloud = KnowledgeCloud(
        data_dir=base,
        evolution_path=overlay,
        read_only_base=True,
    )
    entry = cloud.get_entry("duke_aldric")
    assert entry is not None
    entry.facts.append("Met the Shadow Wraiths at midnight")
    cloud.upsert_entry(entry)

    assert json.loads(world_lore.read_text(encoding="utf-8")) == original
    persisted = json.loads(overlay.read_text(encoding="utf-8"))
    assert persisted["entries"][0]["facts"][-1] == "Met the Shadow Wraiths at midnight"

    with pytest.raises(PermissionError, match="immutable"):
        cloud.remove_entry("duke_aldric")


def test_plural_query_selects_matching_evolved_fact(tmp_path: Path) -> None:
    base = tmp_path / "knowledge_cloud"
    base.mkdir()
    (base / "world_lore.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "entity_id": "duke_aldric",
                        "entity": "Duke Aldric",
                        "description": "Duke Aldric rules Ironhaven.",
                        "facts": ["Has ruled for 22 years"],
                        "aliases": ["the duke"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cloud = KnowledgeCloud(data_dir=base)
    entry = cloud.get_entry("duke_aldric")
    assert entry is not None
    entry.facts.append("Observed the Duke meeting with Shadow Wraiths at midnight")
    cloud.upsert_entry(entry)

    result = cloud.lookup("What do you know about Duke Aldric's meetings?", trust=100)

    assert result is not None
    assert "Shadow Wraiths at midnight" in result["response"]
