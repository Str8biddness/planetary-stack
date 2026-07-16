from __future__ import annotations

from pathlib import Path

import pytest

from core.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(
        {
            "db_path": str(tmp_path / "memory.db"),
            "working_ttl_seconds": 60,
            "working_limit": 2,
            "semantic_dim": 16,
        }
    )


def test_constructor_accepts_config_dict(tmp_path: Path) -> None:
    store = MemoryStore({"db_path": str(tmp_path / "memory.db"), "working_ttl_seconds": 30})
    assert store.db_path.name == "memory.db"
    assert store.working_ttl_seconds == 30


def test_semantic_recall_prioritizes_relevant_fact(store: MemoryStore) -> None:
    character_id = "npc_1"
    store.store_semantic(character_id, "The capital of France is Paris", tags=["geography"])
    store.store_semantic(character_id, "Tokyo is the capital of Japan", tags=["geography"])
    store.store_semantic(character_id, "Bananas are yellow fruits", tags=["food"])

    results = store.recall_semantic(character_id, "What is the capital of France?", top_k=2)

    assert results
    assert results[0].content == "The capital of France is Paris"
    assert any(mem.content == "Tokyo is the capital of Japan" for mem in results)


def test_working_memory_prunes_by_limit(store: MemoryStore) -> None:
    character_id = "npc_2"
    store.store_working(character_id, "Working note 1")
    store.store_working(character_id, "Working note 2")
    store.store_working(character_id, "Working note 3")

    remaining = store.list(character_id, memory_type="working", limit=10)
    contents = {mem.content for mem in remaining}

    assert len(remaining) == 2
    assert "Working note 1" not in contents
    assert {"Working note 2", "Working note 3"} == contents


def test_working_memory_cleanup_with_zero_ttl(tmp_path: Path) -> None:
    store = MemoryStore(
        {
            "db_path": str(tmp_path / "memory.db"),
            "working_ttl_seconds": 0,
            "working_limit": 2,
        }
    )
    character_id = "npc_3"
    store.store_working(character_id, "ephemeral note")

    results = store.recall_working(character_id, "ephemeral")
    assert results == []
