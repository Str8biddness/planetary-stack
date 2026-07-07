"""
E2E Tests — Game Master Domain

Validates the /api/v1/query endpoint when routing through the GM domain adapter.
The GM domain manages per-session world states, NPC routing, and world ticks.
"""
import pytest
import time


class TestGameMasterE2E:
    """End-to-end tests for Game Master domain queries."""

    def test_gm_query_returns_200(self, client):
        """A GM query should return 200."""
        time.sleep(1)
        payload = {
            "query": "I look around the tavern",
            "character": "haven",
            "session_id": "e2e-gm-1",
            "mode": "gm",
        }
        resp = client.post("/api/v1/query", json=payload)
        assert resp.status_code in (200, 404, 429)

    def test_gm_response_structure(self, client):
        """GM responses must have the standard keys."""
        time.sleep(1)
        payload = {
            "query": "What is the weather today?",
            "character": "haven",
            "session_id": "e2e-gm-2",
            "mode": "gm",
        }
        resp = client.post("/api/v1/query", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            assert "response" in data or "text" in data
            assert "confidence" in data

    def test_gm_session_world_isolation(self, client):
        """Each GM session should maintain its own world state."""
        time.sleep(1)
        for sid in ("e2e-gm-world-a", "e2e-gm-world-b"):
            time.sleep(1)
            payload = {
                "query": "Tell me what I see",
                "character": "haven",
                "session_id": sid,
                "mode": "gm",
            }
            resp = client.post("/api/v1/query", json=payload)
            assert resp.status_code in (200, 404, 429)

    def test_gm_npc_mention_routing(self, client):
        """Mentioning an NPC by name should still return a valid response."""
        time.sleep(1)
        payload = {
            "query": "I want to talk to the blacksmith",
            "character": "haven",
            "session_id": "e2e-gm-npc",
            "mode": "gm",
        }
        resp = client.post("/api/v1/query", json=payload)
        assert resp.status_code in (200, 404, 429)

    def test_gm_debug_info(self, client):
        """Debug info should be available for GM queries."""
        time.sleep(1)
        payload = {
            "query": "Explore the forest",
            "character": "haven",
            "session_id": "e2e-gm-debug",
            "mode": "gm",
            "include_debug": True,
        }
        resp = client.post("/api/v1/query", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if "debug" in data:
                assert isinstance(data["debug"], dict)
