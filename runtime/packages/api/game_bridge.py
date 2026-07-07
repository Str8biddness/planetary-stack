#!/usr/bin/env python3
"""
Synthesus Game Bridge - Neon Bay 2087
Lightweight FastAPI bridge exposing POST /think for the Tesana game.
Deploy this standalone; it wraps Synthesus cognitive + knowledge cloud.
Runs on port 8765 by default (set PORT env var to override).
CORS: open to all origins so the Tesana iframe can reach it.
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ── bootstrap sys.path so we can import from the synthesus repo root ──
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logger = logging.getLogger("synthesus.game_bridge")
logging.basicConfig(level=logging.INFO)

# ── lazy-import Synthesus internals (graceful fallback if not available) ──
try:
    from cognitive.cognitive_engine import CognitiveEngine
    _engine = CognitiveEngine()
    logger.info("CognitiveEngine loaded OK")
except Exception as e:
    _engine = None
    logger.warning(f"CognitiveEngine unavailable: {e} — using fallback mode")

try:
    from api.parameter_cloud_v2 import ParameterCloudV2
    _kcloud = ParameterCloudV2()
    logger.info("ParameterCloudV2 loaded OK")
except Exception as e:
    _kcloud = None
    logger.warning(f"ParameterCloudV2 unavailable: {e} — skipping cloud sync")

# ──────────────────────────────────────────────────────────────────────
# Pydantic schemas — match the KPC contract the game sends/receives
# ──────────────────────────────────────────────────────────────────────

class GameEvent(BaseModel):
    type: str
    actor: Optional[str] = None
    target: Optional[str] = None
    data: Optional[Dict[str, Any]] = {}

class PlayerState(BaseModel):
    rep: float = 50.0
    zone: str = "unknown"
    last_actions: List[str] = []

class NPCState(BaseModel):
    id: str
    mood: float = 0.5
    fear: float = 0.0
    anger: float = 0.0
    trust_player: float = 0.5
    beliefs: List[str] = []
    intent: Optional[str] = None
    memory_salience: float = 0.5

class KPCNode(BaseModel):
    id: str
    type: str
    label: str
    weight: float = 0.5
    volatility: float = 0.2

class KPCEdge(BaseModel):
    frm: str = Field(..., alias="from")
    to: str
    rel: str
    strength: float = 0.5
    class Config:
        populate_by_name = True

class KPCGraph(BaseModel):
    nodes: List[KPCNode] = []
    edges: List[KPCEdge] = []

class ThinkRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tick: int = 0
    scene: str = "unknown"
    event: GameEvent
    player: PlayerState = PlayerState()
    npcs: List[NPCState] = []
    knowledge_cloud: KPCGraph = KPCGraph()

# ── response schemas ──

class NPCUpdate(BaseModel):
    id: str
    intent: Optional[str] = None
    emotion_delta: Dict[str, float] = {}
    new_beliefs: List[str] = []

class CloudDelta(BaseModel):
    add_nodes: List[KPCNode] = []
    remove_nodes: List[str] = []
    update_edges: List[KPCEdge] = []

class NarrativeAction(BaseModel):
    type: str
    target: Optional[str] = None
    value: Any = None

class ThinkResponse(BaseModel):
    session_id: str
    tick: int
    npc_updates: List[NPCUpdate] = []
    cloud_delta: CloudDelta = CloudDelta()
    narrative_actions: List[NarrativeAction] = []
    synthesus_mode: str = "cognitive"  # "cognitive" | "fallback"

# ──────────────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Synthesus Game Bridge",
    description="POST /think — Neon Bay 2087 <-> Synthesus AIVM",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────
# Core logic helpers
# ──────────────────────────────────────────────────────────────────────

def _cognitive_think(req: ThinkRequest) -> ThinkResponse:
    """Route through CognitiveEngine if available."""
    npc_updates: List[NPCUpdate] = []
    cloud_delta = CloudDelta()
    narrative_actions: List[NarrativeAction] = []

    for npc in req.npcs:
        prompt = (
            f"NPC {npc.id} in scene '{req.scene}'. "
            f"Event: {req.event.type} by {req.event.actor} targeting {req.event.target}. "
            f"NPC mood={npc.mood:.2f}, fear={npc.fear:.2f}, anger={npc.anger:.2f}, "
            f"trust_player={npc.trust_player:.2f}. "
            f"Beliefs: {', '.join(npc.beliefs) if npc.beliefs else 'none'}. "
            f"Player rep={req.player.rep:.1f}. "
            f"Respond with: new intent, emotion deltas (mood/fear/anger/trust_player), "
            f"new beliefs if any, and one narrative action if warranted."
        )
        try:
            raw = _engine.process(prompt)  # type: ignore
            # Parse a structured delta out of whatever the engine returns
            intent = None
            emotion_delta: Dict[str, float] = {}
            new_beliefs: List[str] = []

            if isinstance(raw, dict):
                intent = raw.get("intent")
                emotion_delta = raw.get("emotion_delta", {})
                new_beliefs = raw.get("beliefs", [])
            elif isinstance(raw, str):
                intent = raw[:80]

            npc_updates.append(NPCUpdate(
                id=npc.id,
                intent=intent,
                emotion_delta=emotion_delta,
                new_beliefs=new_beliefs,
            ))
        except Exception as exc:
            logger.debug(f"CognitiveEngine NPC {npc.id} error: {exc}")
            npc_updates.append(_fallback_npc_update(npc, req.event))

    # knowledge cloud sync via ParameterCloudV2 if available
    if _kcloud is not None:
        try:
            for node in req.knowledge_cloud.nodes:
                _kcloud.upsert(node.id, {"label": node.label, "type": node.type,
                                          "weight": node.weight, "volatility": node.volatility})
        except Exception as exc:
            logger.debug(f"KCloud sync error: {exc}")

    return ThinkResponse(
        session_id=req.session_id,
        tick=req.tick,
        npc_updates=npc_updates,
        cloud_delta=cloud_delta,
        narrative_actions=narrative_actions,
        synthesus_mode="cognitive",
    )


def _fallback_npc_update(npc: NPCState, event: GameEvent) -> NPCUpdate:
    """Rule-based fallback when Synthesus engine is offline."""
    delta: Dict[str, float] = {}
    intent = npc.intent or "idle"
    if event.type in ("gunshot", "attack", "death"):
        delta = {"fear": min(1.0, npc.fear + 0.2), "anger": min(1.0, npc.anger + 0.1)}
        intent = "flee" if npc.fear > 0.6 else "watch"
    elif event.type == "dialogue":
        delta = {"trust_player": min(1.0, npc.trust_player + 0.05)}
        intent = "engage"
    return NPCUpdate(id=npc.id, intent=intent, emotion_delta=delta, new_beliefs=[])


def _fallback_think(req: ThinkRequest) -> ThinkResponse:
    """Pure rule-based response — no AI dependency."""
    return ThinkResponse(
        session_id=req.session_id,
        tick=req.tick,
        npc_updates=[_fallback_npc_update(n, req.event) for n in req.npcs],
        cloud_delta=CloudDelta(),
        narrative_actions=[],
        synthesus_mode="fallback",
    )

# ──────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "synthesus_engine": _engine is not None,
        "parameter_cloud": _kcloud is not None,
        "timestamp": time.time(),
    }


@app.post("/think", response_model=ThinkResponse)
async def think(req: ThinkRequest):
    """Main game bridge endpoint — called by Neon Bay 2087 KPC system."""
    try:
        if _engine is not None:
            return _cognitive_think(req)
        else:
            return _fallback_think(req)
    except Exception as exc:
        logger.error(f"/think error: {exc}")
        return _fallback_think(req)


@app.post("/knowledge/search")
async def knowledge_search(body: Dict[str, Any]):
    """Proxy to knowledge_cloud_router search — used by KPC overlay for node discovery."""
    if _kcloud is None:
        return {"results": [], "mode": "offline"}
    try:
        q = body.get("q", "")
        results = _kcloud.search(q, top_k=body.get("top_k", 5))
        return {"results": results, "mode": "online"}
    except Exception as exc:
        return {"results": [], "error": str(exc), "mode": "error"}


@app.get("/")
async def root():
    return {"service": "Synthesus Game Bridge", "version": "1.0.0",
            "game": "Neon Bay 2087", "docs": "/docs"}

# ──────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8765))
    logger.info(f"Starting Synthesus Game Bridge on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
