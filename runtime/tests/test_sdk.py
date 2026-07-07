"""
Tests for Phase 17: Game Engine Integration SDK

Tests the Python SDK client against a mock server.
Unity and Unreal SDKs are C#/C++ and tested in their respective environments.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

# Import SDK
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent / "sdk" / "python"))
from synthesus_sdk import (
    SynthesusClient,
    NPCResponse,
    CharacterInfo,
    WorldState,
    HealthStatus,
)


# ── Mock HTTP Layer ──

class MockResponse:
    """Simulate requests.Response"""
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def mock_post(url, json=None, headers=None, timeout=None):
    """Route mock POST requests."""
    if "/api/query" in url:
        return MockResponse({
            "response": "Welcome to my shop!",
            "confidence": 0.85,
            "emotion": "friendly",
            "source": "cognitive_engine",
            "debug": {"latency_ms": 5.2, "match_score": 0.85},
        })
    if "/api/batch_query" in url:
        return MockResponse({
            "responses": [
                {"response": "Hello!", "confidence": 0.9, "emotion": "happy",
                 "source": "cognitive_engine", "character_id": "npc_1"},
                {"response": "Go away.", "confidence": 0.7, "emotion": "angry",
                 "source": "cognitive_engine", "character_id": "npc_2"},
            ]
        })
    if "/api/save" in url:
        return MockResponse({"status": "saved", "slot": "default"})
    if "/api/load" in url:
        return MockResponse({"status": "loaded", "slot": "default"})
    if "/api/world/tick" in url:
        return MockResponse({"tick": 42, "events": []})
    if "/characters/" in url and "/load" in url:
        return MockResponse({"status": "loaded"})
    return MockResponse({"error": "not found"}, 404)


def mock_get(url, headers=None, timeout=None):
    """Route mock GET requests."""
    if "/api/characters/" in url:
        return MockResponse({
            "id": "merchant_01", "name": "Tom", "role": "merchant", "pattern_count": 15
        })
    if "/api/characters" in url:
        return MockResponse({
            "characters": [
                {"id": "merchant_01", "name": "Tom", "role": "merchant"},
                {"id": "guard_01", "name": "Anna", "role": "guard"},
            ]
        })
    if "/api/world/state" in url:
        return MockResponse({
            "tick": 100, "weather": "rain", "economy": {"gold_price": 50},
            "active_quests": 3
        })
    if "/api/health" in url:
        return MockResponse({
            "status": "healthy", "active_characters": 5, "total_queries": 1000
        })
    return MockResponse({"error": "not found"}, 404)


@pytest.fixture
def client():
    """Client with mocked HTTP."""
    with patch("synthesus_sdk.requests") as mock_req:
        mock_req.post = mock_post
        mock_req.get = mock_get
        c = SynthesusClient("http://localhost:8000", api_key="test-key")
        yield c


# ══════════════════════════════════════
# Client Initialization
# ══════════════════════════════════════

class TestClientInit:
    def test_default_url(self):
        with patch("synthesus_sdk.requests"):
            c = SynthesusClient()
            assert c.base_url == "http://localhost:8000"

    def test_custom_url(self):
        with patch("synthesus_sdk.requests"):
            c = SynthesusClient("http://myserver:9000/")
            assert c.base_url == "http://myserver:9000"

    def test_api_key_header(self):
        with patch("synthesus_sdk.requests"):
            c = SynthesusClient(api_key="sk-test-123")
            assert c._headers["Authorization"] == "Bearer sk-test-123"

    def test_no_api_key(self):
        with patch("synthesus_sdk.requests"):
            c = SynthesusClient()
            assert "Authorization" not in c._headers


# ══════════════════════════════════════
# Chat Tests
# ══════════════════════════════════════

class TestChat:
    def test_basic_chat(self, client):
        resp = client.chat("merchant_01", "player_1", "Hello!")
        assert isinstance(resp, NPCResponse)
        assert resp.text == "Welcome to my shop!"
        assert resp.confidence == 0.85
        assert resp.emotion == "friendly"
        assert resp.source == "cognitive_engine"
        assert resp.character_id == "merchant_01"

    def test_chat_latency_tracked(self, client):
        resp = client.chat("merchant_01", "player_1", "Hi")
        assert resp.latency_ms >= 0

    def test_batch_chat(self, client):
        responses = client.batch_chat([
            {"character_id": "npc_1", "player_id": "p1", "message": "Hello"},
            {"character_id": "npc_2", "player_id": "p1", "message": "Go away"},
        ])
        assert len(responses) == 2
        assert responses[0].text == "Hello!"
        assert responses[1].text == "Go away."


# ══════════════════════════════════════
# Character Management Tests
# ══════════════════════════════════════

class TestCharacterManagement:
    def test_list_characters(self, client):
        chars = client.list_characters()
        assert len(chars) == 2
        assert isinstance(chars[0], CharacterInfo)
        assert chars[0].name == "Tom"
        assert chars[1].role == "guard"

    def test_get_character(self, client):
        char = client.get_character("merchant_01")
        assert isinstance(char, CharacterInfo)
        assert char.name == "Tom"
        assert char.pattern_count == 15

    def test_load_character(self, client):
        result = client.load_character("merchant_01")
        assert result is True


# ══════════════════════════════════════
# World State Tests
# ══════════════════════════════════════

class TestWorldState:
    def test_get_world_state(self, client):
        state = client.get_world_state()
        assert isinstance(state, WorldState)
        assert state.tick == 100
        assert state.weather == "rain"
        assert state.active_quests == 3

    def test_world_tick(self, client):
        result = client.world_tick()
        assert result["tick"] == 42


# ══════════════════════════════════════
# Save/Load Tests
# ══════════════════════════════════════

class TestSaveLoad:
    def test_save_game(self, client):
        result = client.save_game("slot_1")
        assert result["status"] == "saved"

    def test_load_game(self, client):
        result = client.load_game("slot_1")
        assert result["status"] == "loaded"


# ══════════════════════════════════════
# Health Tests
# ══════════════════════════════════════

class TestHealth:
    def test_health(self, client):
        status = client.health()
        assert isinstance(status, HealthStatus)
        assert status.status == "healthy"
        assert status.active_characters == 5


# ══════════════════════════════════════
# SDK Stats Tests
# ══════════════════════════════════════

class TestStats:
    def test_request_counting(self, client):
        client.chat("npc", "p", "hi")
        client.chat("npc", "p", "bye")
        assert client.stats["total_requests"] == 2

    def test_latency_tracking(self, client):
        client.chat("npc", "p", "hi")
        assert client.stats["avg_latency_ms"] >= 0
        assert client.stats["total_latency_ms"] >= 0


# ══════════════════════════════════════
# Response Types
# ══════════════════════════════════════

class TestResponseTypes:
    def test_npc_response_defaults(self):
        r = NPCResponse(text="hi", confidence=0.5, emotion="neutral",
                        source="test", character_id="npc_1")
        assert r.latency_ms == 0.0
        assert r.debug == {}
        assert r.raw == {}

    def test_character_info_defaults(self):
        c = CharacterInfo(character_id="npc_1", name="Test", role="guard")
        assert c.pattern_count == 0
        assert c.metadata == {}

    def test_world_state_defaults(self):
        w = WorldState()
        assert w.tick == 0
        assert w.weather == "clear"

    def test_health_status_defaults(self):
        h = HealthStatus(status="ok")
        assert h.active_characters == 0
