"""
Synthesus SDK — Python Client

Drop-in client for integrating Synthesus NPC intelligence into any Python
application, game engine, or framework.

Usage:
    from synthesus_sdk import SynthesusClient

    client = SynthesusClient("http://localhost:8000")
    response = client.chat("merchant_01", "player_1", "What do you sell?")
    print(response.text)

Supports:
- Single NPC chat
- Batch NPC queries
- Character management (list, create, load)
- World state queries
- Social fabric interactions
- Save/load game state
- Async support via SynthesusAsyncClient
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


# ── Response Types ──

@dataclass
class NPCResponse:
    """Response from an NPC query."""
    text: str
    confidence: float
    emotion: str
    source: str
    character_id: str
    latency_ms: float = 0.0
    debug: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CharacterInfo:
    """Character metadata."""
    character_id: str
    name: str
    role: str
    pattern_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorldState:
    """Current world state snapshot."""
    tick: int = 0
    weather: str = "clear"
    economy: Dict[str, Any] = field(default_factory=dict)
    active_quests: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthStatus:
    """Server health status."""
    status: str
    uptime_seconds: float = 0.0
    active_characters: int = 0
    total_queries: int = 0
    avg_latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── SDK Client ──

class SynthesusClient:
    """
    Synchronous client for the Synthesus NPC API.

    Args:
        base_url: Base URL of the Synthesus API server (e.g., "http://localhost:8000")
        api_key: Optional API key for authentication
        timeout: Request timeout in seconds (default 30)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

        # Stats
        self._total_requests = 0
        self._total_latency = 0.0

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _post(self, path: str, data: Dict) -> Dict:
        self._total_requests += 1
        start = time.time()
        if HAS_REQUESTS:
            resp = requests.post(
                self._url(path), json=data,
                headers=self._headers, timeout=self.timeout
            )
            resp.raise_for_status()
            result = resp.json()
        elif HAS_HTTPX:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self._url(path), json=data, headers=self._headers)
                resp.raise_for_status()
                result = resp.json()
        else:
            raise RuntimeError("Install 'requests' or 'httpx' to use SynthesusClient")
        self._total_latency += (time.time() - start) * 1000
        return result

    def _get(self, path: str) -> Dict:
        self._total_requests += 1
        start = time.time()
        if HAS_REQUESTS:
            resp = requests.get(
                self._url(path), headers=self._headers, timeout=self.timeout
            )
            resp.raise_for_status()
            result = resp.json()
        elif HAS_HTTPX:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(self._url(path), headers=self._headers)
                resp.raise_for_status()
                result = resp.json()
        else:
            raise RuntimeError("Install 'requests' or 'httpx' to use SynthesusClient")
        self._total_latency += (time.time() - start) * 1000
        return result

    # ── NPC Chat ──

    def chat(
        self,
        character_id: str,
        player_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> NPCResponse:
        """
        Send a message to an NPC and get their response.

        Args:
            character_id: The NPC's character ID
            player_id: The player's unique ID
            message: The player's message
            context: Optional additional context (world state, location, etc.)

        Returns:
            NPCResponse with the NPC's reply, confidence, emotion, etc.
        """
        data = {
            "character_id": character_id,
            "player_id": player_id,
            "query": message,
        }
        if context:
            data["context"] = context

        start = time.time()
        result = self._post("/api/query", data)
        latency = (time.time() - start) * 1000

        return NPCResponse(
            text=result.get("response", ""),
            confidence=result.get("confidence", 0.0),
            emotion=result.get("emotion", "neutral"),
            source=result.get("source", "unknown"),
            character_id=character_id,
            latency_ms=latency,
            debug=result.get("debug", {}),
            raw=result,
        )

    def batch_chat(
        self,
        queries: List[Dict[str, str]],
    ) -> List[NPCResponse]:
        """
        Send multiple NPC queries in one request.

        Args:
            queries: List of {"character_id", "player_id", "message"} dicts

        Returns:
            List of NPCResponse objects
        """
        result = self._post("/api/batch_query", {"queries": queries})
        responses = []
        for r in result.get("responses", []):
            responses.append(NPCResponse(
                text=r.get("response", ""),
                confidence=r.get("confidence", 0.0),
                emotion=r.get("emotion", "neutral"),
                source=r.get("source", "unknown"),
                character_id=r.get("character_id", ""),
                raw=r,
            ))
        return responses

    # ── Character Management ──

    def list_characters(self) -> List[CharacterInfo]:
        """List all available characters."""
        result = self._get("/api/characters")
        return [
            CharacterInfo(
                character_id=c.get("id", ""),
                name=c.get("name", ""),
                role=c.get("role", ""),
                metadata=c,
            )
            for c in result.get("characters", [])
        ]

    def get_character(self, character_id: str) -> CharacterInfo:
        """Get details about a specific character."""
        result = self._get(f"/api/characters/{character_id}")
        return CharacterInfo(
            character_id=result.get("id", character_id),
            name=result.get("name", ""),
            role=result.get("role", ""),
            pattern_count=result.get("pattern_count", 0),
            metadata=result,
        )

    def load_character(self, character_id: str) -> bool:
        """Load a character into memory for faster queries."""
        result = self._post(f"/api/characters/{character_id}/load", {})
        return result.get("status") == "loaded"

    # ── World State ──

    def get_world_state(self) -> WorldState:
        """Get the current world state."""
        result = self._get("/api/world/state")
        return WorldState(
            tick=result.get("tick", 0),
            weather=result.get("weather", "clear"),
            economy=result.get("economy", {}),
            active_quests=result.get("active_quests", 0),
            metadata=result,
        )

    def world_tick(self) -> Dict[str, Any]:
        """Advance the world by one tick."""
        return self._post("/api/world/tick", {})

    # ── Save/Load ──

    def save_game(self, slot: str = "default", metadata: Optional[Dict] = None) -> Dict:
        """Save the current game state."""
        return self._post("/api/save", {"slot": slot, "metadata": metadata or {}})

    def load_game(self, slot: str = "default") -> Dict:
        """Load a saved game state."""
        return self._post("/api/load", {"slot": slot})

    # ── Health ──

    def health(self) -> HealthStatus:
        """Check server health."""
        result = self._get("/api/health")
        return HealthStatus(
            status=result.get("status", "unknown"),
            active_characters=result.get("active_characters", 0),
            total_queries=result.get("total_queries", 0),
            metadata=result,
        )

    # ── SDK Stats ──

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_requests": self._total_requests,
            "total_latency_ms": round(self._total_latency, 2),
            "avg_latency_ms": round(
                self._total_latency / max(1, self._total_requests), 2
            ),
        }
