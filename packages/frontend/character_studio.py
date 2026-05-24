"""
Character Studio — Web-Based NPC Creator Tool

A FastAPI application that provides:
1. Genome Editor: Adjust personality traits, knowledge, behaviors via sliders
2. Conversation Preview: Live chat with your NPC to test it
3. Character Export: Download character packages (bio.json + patterns.json)
4. Template Gallery: Start from pre-built archetypes

Runs on port 8500. Launch: python studio/character_studio.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from cognitive.cognitive_engine import CognitiveEngine

app = FastAPI(title="AIVM Character Studio", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-Memory State ──
_sessions: Dict[str, Dict[str, Any]] = {}  # session_id → {engine, bio, patterns, ...}
CHARACTERS_DIR = Path(__file__).parent.parent / "characters"
ARCHETYPES_DIR = Path(__file__).parent.parent / "unpc_engine" / "archetypes"


# ── Models ──

class CreateCharacterRequest(BaseModel):
    name: str = "New Character"
    role: str = "merchant"
    archetype: Optional[str] = None
    personality: Dict[str, float] = Field(default_factory=lambda: {
        "chattiness": 0.5,
        "friendliness": 0.5,
        "formality": 0.5,
        "humor": 0.3,
        "aggression": 0.1,
        "curiosity": 0.5,
    })
    backstory: str = ""
    knowledge_domain: str = ""
    greeting: str = "Hello there, traveler."


class UpdateGenomeRequest(BaseModel):
    personality: Optional[Dict[str, float]] = None
    name: Optional[str] = None
    role: Optional[str] = None
    backstory: Optional[str] = None
    greeting: Optional[str] = None
    knowledge_domain: Optional[str] = None
    custom_patterns: Optional[List[Dict[str, Any]]] = None


class ChatRequest(BaseModel):
    message: str
    player_id: str = "studio_user"


# ── Helpers ──

def _generate_patterns(bio: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a starter pattern set from bio data."""
    name = bio.get("name", "Character")
    role = bio.get("role", "npc")
    greeting = bio.get("greeting", "Hello there.")
    backstory = bio.get("backstory", "")
    domain = bio.get("knowledge_domain", "")
    personality = bio.get("personality", {})

    chattiness = personality.get("chattiness", 0.5)
    friendliness = personality.get("friendliness", 0.5)
    humor = personality.get("humor", 0.3)

    patterns = []
    pid = 0

    # Greeting patterns
    patterns.append({
        "id": f"gen_{pid:03d}",
        "triggers": ["hello", "hi", "hey", "greetings"],
        "response_template": greeting,
        "topic": "greeting",
    })
    pid += 1

    # Name patterns
    patterns.append({
        "id": f"gen_{pid:03d}",
        "triggers": ["name", "who are you", "your name", "called"],
        "response_template": f"I'm {name}. {'Pleased to meet you!' if friendliness > 0.5 else 'What do you want?'}",
        "topic": "identity",
    })
    pid += 1

    # Role patterns
    patterns.append({
        "id": f"gen_{pid:03d}",
        "triggers": ["job", "work", "do you do", "occupation", "role"],
        "response_template": f"I'm a {role}. {'I love what I do!' if chattiness > 0.6 else 'It pays the bills.'}",
        "topic": "role",
    })
    pid += 1

    # Backstory patterns
    if backstory:
        patterns.append({
            "id": f"gen_{pid:03d}",
            "triggers": ["story", "past", "background", "where from", "history"],
            "response_template": backstory[:200] + ("..." if len(backstory) > 200 else ""),
            "topic": "backstory",
        })
        pid += 1

    # Knowledge domain patterns
    if domain:
        patterns.append({
            "id": f"gen_{pid:03d}",
            "triggers": [domain.lower(), "tell me about", "know about", "expertise"],
            "response_template": f"Ah, {domain}! That's my area of expertise. What would you like to know?",
            "topic": "knowledge",
        })
        pid += 1

    # Personality-driven patterns
    if humor > 0.5:
        patterns.append({
            "id": f"gen_{pid:03d}",
            "triggers": ["joke", "funny", "laugh", "humor"],
            "response_template": "Ha! You want a joke? Alright, why did the NPC cross the road? Because the player needed a quest!",
            "topic": "humor",
        })
        pid += 1

    if friendliness > 0.7:
        patterns.append({
            "id": f"gen_{pid:03d}",
            "triggers": ["help", "assist", "need help"],
            "response_template": "Of course! I'd love to help. What do you need?",
            "topic": "help",
        })
        pid += 1
    elif personality.get("aggression", 0) > 0.5:
        patterns.append({
            "id": f"gen_{pid:03d}",
            "triggers": ["fight", "battle", "challenge"],
            "response_template": "You dare challenge me? Very well, let's settle this.",
            "topic": "combat",
        })
        pid += 1

    # Farewell
    patterns.append({
        "id": f"gen_{pid:03d}",
        "triggers": ["bye", "goodbye", "farewell", "see you", "later"],
        "response_template": f"{'Safe travels, friend!' if friendliness > 0.5 else 'Yeah, see you around.'}",
        "topic": "farewell",
    })
    pid += 1

    return {
        "synthetic_patterns": patterns,
        "generic_patterns": [],
        "fallback": f"{'Hmm, I am not sure about that.' if friendliness > 0.5 else 'I have nothing to say about that.'}",
    }


def _create_engine(bio: Dict, patterns: Dict) -> CognitiveEngine:
    """Create a CognitiveEngine from bio and patterns."""
    char_id = bio.get("character_id", f"studio_{uuid.uuid4().hex[:8]}")
    return CognitiveEngine(
        character_id=char_id,
        bio=bio,
        patterns=patterns,
    )


# ── API Endpoints ──

@app.get("/", response_class=HTMLResponse)
async def studio_ui():
    """Serve the Character Studio single-page app."""
    html_path = Path(__file__).parent / "studio_ui.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>Character Studio</h1><p>UI not found. Use the API endpoints.</p>")


@app.get("/api/archetypes")
async def list_archetypes():
    """List available character archetypes."""
    archetypes = []
    if ARCHETYPES_DIR.exists():
        for f in sorted(ARCHETYPES_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                archetypes.append({
                    "id": f.stem,
                    "name": data.get("archetype_name", f.stem),
                    "description": data.get("description", ""),
                    "default_role": data.get("default_role", "npc"),
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return {"archetypes": archetypes}


@app.get("/api/characters")
async def list_characters():
    """List saved characters."""
    characters = []
    if CHARACTERS_DIR.exists():
        for d in sorted(CHARACTERS_DIR.iterdir()):
            if d.is_dir():
                bio_path = d / "bio.json"
                if bio_path.exists():
                    try:
                        bio = json.loads(bio_path.read_text())
                        characters.append({
                            "id": d.name,
                            "name": bio.get("name", d.name),
                            "role": bio.get("role", "unknown"),
                        })
                    except json.JSONDecodeError:
                        continue
    return {"characters": characters}


@app.post("/api/session/create")
async def create_session(req: CreateCharacterRequest):
    """Create a new character editing session."""
    session_id = f"session_{uuid.uuid4().hex[:12]}"

    bio = {
        "character_id": f"studio_{uuid.uuid4().hex[:8]}",
        "name": req.name,
        "role": req.role,
        "personality": req.personality,
        "backstory": req.backstory,
        "knowledge_domain": req.knowledge_domain,
        "greeting": req.greeting,
    }

    patterns = _generate_patterns(bio)
    engine = _create_engine(bio, patterns)

    _sessions[session_id] = {
        "engine": engine,
        "bio": bio,
        "patterns": patterns,
        "created_at": time.time(),
    }

    return {
        "session_id": session_id,
        "character_id": bio["character_id"],
        "bio": bio,
        "pattern_count": len(patterns["synthetic_patterns"]),
    }


@app.put("/api/session/{session_id}/genome")
async def update_genome(session_id: str, req: UpdateGenomeRequest):
    """Update the character genome and regenerate the engine."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    bio = session["bio"]

    # Apply updates
    if req.personality is not None:
        bio["personality"] = req.personality
    if req.name is not None:
        bio["name"] = req.name
    if req.role is not None:
        bio["role"] = req.role
    if req.backstory is not None:
        bio["backstory"] = req.backstory
    if req.greeting is not None:
        bio["greeting"] = req.greeting
    if req.knowledge_domain is not None:
        bio["knowledge_domain"] = req.knowledge_domain

    # Regenerate patterns (merge custom if provided)
    patterns = _generate_patterns(bio)
    if req.custom_patterns:
        patterns["synthetic_patterns"].extend(req.custom_patterns)

    # Rebuild engine
    engine = _create_engine(bio, patterns)
    session["engine"] = engine
    session["bio"] = bio
    session["patterns"] = patterns

    return {
        "bio": bio,
        "pattern_count": len(patterns["synthetic_patterns"]),
        "status": "regenerated",
    }


@app.post("/api/session/{session_id}/chat")
async def chat_with_character(session_id: str, req: ChatRequest):
    """Chat with the character in the current session."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    engine = session["engine"]
    result = await engine.process_query(req.player_id, req.message)

    return {
        "response": result["response"],
        "confidence": result["confidence"],
        "emotion": result["emotion"],
        "source": result["source"],
        "debug": result.get("debug", {}),
    }


@app.get("/api/session/{session_id}/export")
async def export_character(session_id: str):
    """Export the character as a downloadable package."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    return {
        "bio": session["bio"],
        "patterns": session["patterns"],
        "export_format": "synthesus_v2",
        "instructions": "Save bio.json and patterns.json to characters/<id>/ directory",
    }


@app.post("/api/session/{session_id}/save")
async def save_character(session_id: str):
    """Save the character to disk in the characters directory."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    bio = session["bio"]
    char_id = bio["character_id"]
    char_dir = CHARACTERS_DIR / char_id
    char_dir.mkdir(parents=True, exist_ok=True)

    (char_dir / "bio.json").write_text(json.dumps(bio, indent=2))
    (char_dir / "patterns.json").write_text(json.dumps(session["patterns"], indent=2))

    return {
        "saved_to": str(char_dir),
        "character_id": char_id,
        "files": ["bio.json", "patterns.json"],
    }


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    if session_id in _sessions:
        del _sessions[session_id]
        return {"status": "deleted"}
    raise HTTPException(404, "Session not found")


@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "active_sessions": len(_sessions),
        "characters_on_disk": len(list(CHARACTERS_DIR.iterdir())) if CHARACTERS_DIR.exists() else 0,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8500)
