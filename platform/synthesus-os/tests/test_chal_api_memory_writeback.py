from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def _import_production_server():
    try:
        return importlib.import_module("api.production_server")
    except Exception as exc:
        pytest.skip(f"production_server import unavailable in this environment: {exc}")


class FakeMemoryStore:
    def __init__(self) -> None:
        self.records = []

    def store_episodic(self, character_id, content, importance=0.5, tags=None, metadata=None):
        record = {
            "id": f"mem-{len(self.records) + 1}",
            "character_id": character_id,
            "content": content,
            "importance": importance,
            "tags": tags or [],
            "metadata": metadata or {},
        }
        self.records.append(record)
        return SimpleNamespace(id=record["id"])


def test_chal_api_writeback_accepts_final_hypervisor_trace(monkeypatch):
    ps = _import_production_server()
    store = FakeMemoryStore()
    monkeypatch.setattr(ps, "HAS_CHAL_MEMORY_WRITEBACK", True)
    monkeypatch.setattr(ps, "_chal_memory_store", store)

    hv_result = SimpleNamespace(
        response="CHAL cache tiers are mounted through KAL.",
        telemetry={
            "trace_id": "api-hv-1",
            "route": "grounded_path",
            "hemisphere_mode": "both",
            "degraded": False,
            "template_guard": {"rewritten": False},
            "knowledge_provenance": {
                "context_used": True,
                "source": "rom_mount:world_lore",
                "confidence": 0.9,
                "mounts": [{"mount_path": "/mnt/rom/world_lore"}],
            },
        },
    )

    payload = ps._apply_chal_memory_writeback(
        hv_result=hv_result,
        query_text="Explain CHAL cache tiers",
        character_id="synth",
    )

    assert payload["schema"] == "synthesus.chal.memory_writeback_result.v1"
    assert payload["decision"]["accepted"] is True
    assert payload["decision"]["target_mount"] == "/mnt/mem/writeback"
    assert payload["stored_memory_id"] == "mem-1"
    assert store.records[0]["content"].startswith("User: Explain CHAL cache tiers")
    assert store.records[0]["metadata"]["trace_id"] == "api-hv-1"
    assert store.records[0]["metadata"]["provenance"][0]["ref"] == "/mnt/rom/world_lore"


def test_chal_api_writeback_rejects_degraded_template_rewritten_trace(monkeypatch):
    ps = _import_production_server()
    store = FakeMemoryStore()
    monkeypatch.setattr(ps, "HAS_CHAL_MEMORY_WRITEBACK", True)
    monkeypatch.setattr(ps, "_chal_memory_store", store)

    hv_result = SimpleNamespace(
        response="Structured degraded CHAL state.",
        telemetry={
            "trace_id": "api-hv-2",
            "route": "fast_path",
            "hemisphere_mode": "both",
            "degraded": True,
            "template_guard": {"rewritten": True},
        },
    )

    payload = ps._apply_chal_memory_writeback(
        hv_result=hv_result,
        query_text="Trigger degraded state",
        character_id="synth",
    )

    assert payload["decision"]["accepted"] is False
    assert payload["decision"]["reason"] == "critic_rejected"
    assert payload["decision"]["target_mount"] == "/mnt/mem/writeback"
    assert store.records == []
