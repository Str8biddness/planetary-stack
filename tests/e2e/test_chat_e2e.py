"""
E2E Tests — Chat Domain

Validates the /api/v1/query endpoint for the standard chat domain.
Tests are resilient to environments where RAG/FAISS may not be loaded.
"""
import pytest


class TestChatE2E:
    """End-to-end tests for standard chat domain queries."""

    def test_basic_query_returns_200(self, client):
        """A simple chat query must return HTTP 200 with expected keys."""
        payload = {
            "query": "Hello, who are you?",
            "character": "synthesus",
            "session_id": "e2e-chat-1",
        }
        resp = client.post("/api/v1/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        # Must always have these keys
        assert "response" in data or "text" in data
        assert "confidence" in data
        assert "character" in data
        assert "source" in data

    def test_response_is_nonempty(self, client):
        """The system must always generate some text, even on fallback."""
        payload = {
            "query": "Tell me something interesting",
            "character": "synthesus",
            "session_id": "e2e-chat-2",
        }
        resp = client.post("/api/v1/query", json=payload)
        data = resp.json()
        text = data.get("response", data.get("text", ""))
        assert len(text) > 0, "Response text must not be empty"

    def test_source_field_is_valid(self, client):
        """source must be one of the known pipeline sources."""
        payload = {
            "query": "What can you do?",
            "character": "synthesus",
            "session_id": "e2e-chat-3",
        }
        resp = client.post("/api/v1/query", json=payload)
        data = resp.json()
        valid_sources = {"pattern", "rag", "escalated", "fallback", "knowledge_cloud", "generation", "cognitive", "cognitive_engine", "symbolic_core", "cognitive_hypervisor"}
        assert data.get("source") in valid_sources, f"Unexpected source: {data.get('source')}"

    def test_chal_mode_routes_through_cognitive_hypervisor(self, client):
        """Explicit CHAL mode should expose Synthesus 5 hypervisor telemetry."""
        payload = {
            "query": "Compare CHAL memory and cache architecture",
            "character": "synthesus",
            "session_id": "e2e-chat-chal",
            "mode": "chal",
            "include_debug": True,
        }
        resp = client.post("/api/v1/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["source"] == "cognitive_hypervisor"
        assert data["response"]
        hv_debug = data["debug"]["cognitive_hypervisor"]
        assert hv_debug["schema"] == "synthesus.chal.hypervisor_trace.v1"
        assert hv_debug["route"] in {
            "fast_path",
            "grounded_path",
            "deep_reasoning_path",
            "quad_brain_path",
            "safety_path",
        }

    def test_business_bot_mode_routes_through_chal_preset(self, client):
        """Business-bot mode should expose the concise Synthesus 5 CHAL preset."""
        payload = {
            "query": "Tell the operator the safest next step for a flaky worker.",
            "character": "synthesus",
            "session_id": "e2e-chat-business-bot",
            "mode": "business_bot",
            "include_debug": True,
        }
        resp = client.post("/api/v1/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        hv_debug = data["debug"]["cognitive_hypervisor"]
        cgpu_output = hv_debug["quad_brain"]["outputs"][2]

        assert data["source"] == "cognitive_hypervisor"
        assert hv_debug["route"] == "quad_brain_path"
        assert hv_debug["runtime_preset"] == "business_bot"
        assert "business_bot_preset" in hv_debug["reasons"]
        assert cgpu_output["content"]["trace"]["mode"] == "business_bot"
        assert data["response"].startswith(("Direct answer:", "Recommended next step:"))

    def test_debug_info_when_requested(self, client):
        """include_debug=True should add a debug block to the response."""
        payload = {
            "query": "debug test",
            "character": "synthesus",
            "session_id": "e2e-chat-4",
            "include_debug": True,
        }
        resp = client.post("/api/v1/query", json=payload)
        data = resp.json()
        assert "debug" in data, "Debug info must be present when include_debug=True"
        assert isinstance(data["debug"], dict)

    def test_session_persistence(self, client):
        """Two queries in the same session should both succeed."""
        sid = "e2e-chat-persist"
        for q in ["Hi there", "What did I just say?"]:
            payload = {"query": q, "character": "synthesus", "session_id": sid}
            resp = client.post("/api/v1/query", json=payload)
            assert resp.status_code == 200

    def test_empty_query_handled_gracefully(self, client):
        """An empty query should not crash the server."""
        payload = {
            "query": "",
            "character": "synthesus",
            "session_id": "e2e-chat-empty",
        }
        resp = client.post("/api/v1/query", json=payload)
        # Should either return 200 (with fallback) or 4xx (validation)
        assert resp.status_code in (200, 400, 422)

    def test_unknown_character_handled(self, client):
        """Querying a non-existent character should still return 200 with fallback."""
        payload = {
            "query": "Hello?",
            "character": "nonexistent_character_xyz",
            "session_id": "e2e-chat-unknown",
        }
        resp = client.post("/api/v1/query", json=payload)
        # Server should handle gracefully
        assert resp.status_code in (200, 404)
