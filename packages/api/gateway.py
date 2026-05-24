#!/usr/bin/env python3
"""
Synthesus 2.0 API Gateway
AIVM LLC - Dual-Hemisphere Synthetic Intelligence

Routes queries to the appropriate hemisphere:
 - Left Hemisphere: C++ PPBRS kernel (pattern matching, confidence scoring)
 - Right Hemisphere: 9 Cognitive modules (emotion, relationships, personality...)
 - ML Swarm: 7 specialized micro-models (~458 KB total, <1ms inference)
"""

import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─── Fixed imports: use repo-root-relative paths, not synthesus.* package ───
from core.hemisphere_bridge import HemisphereBridge
from core.rag_pipeline import RAGPipeline
from kal.config import load_kal_config, build_kal_service, KalConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─── Inline stubs for modules that don't exist in the repo yet ───────────────
class CharacterLoader:
    """Stub: loads character genomes from characters/ directory."""

    def __init__(self, characters_dir: str = "./characters"):
        self._dir = Path(characters_dir)

    def load(self, character_id: str) -> Optional[Dict[str, Any]]:
        char_path = self._dir / character_id / "bio.json"
        if char_path.exists():
            with open(char_path) as f:
                return json.load(f)
        return None

    def list_all(self) -> List[Dict[str, str]]:
        results = []
        if self._dir.exists():
            for entry in sorted(self._dir.iterdir()):
                bio = entry / "bio.json"
                if entry.is_dir() and bio.exists():
                    results.append({"id": entry.name, "path": str(entry)})
        return results


class ConfidenceCalibrator:
    """Stub: pass-through confidence calibrator."""

    def calibrate(
        self,
        raw_confidence: float,
        hemisphere_used: str,
        agreement_score: Optional[float] = None,
    ) -> float:
        if agreement_score is not None and agreement_score > 0.6:
            return min(raw_confidence * 1.1, 1.0)
        return raw_confidence


# ─── FastAPI app ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Synthesus 2.0 API",
    description="AIVM Dual-Hemisphere Synthetic Intelligence - Real Life NPCs",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances (lazy-init safe — hemisphere_bridge handles missing deps)
bridge = HemisphereBridge()
rag = RAGPipeline()
character_loader = CharacterLoader()
calibrator = ConfidenceCalibrator()

# ─── KAL Wiring ─────────────────────────────────────────────────────────────
_kal_config = load_kal_config()
_kal_client = None
if _kal_config.enabled:
    try:
        _kal_service, _kal_client = build_kal_service(_kal_config, rag_pipeline=rag)
        logger.info("KAL enabled (backend=%s, use_for_retrieval=%s)",
                    _kal_config.backend_type, _kal_config.use_for_retrieval)
    except Exception as e:
        logger.warning("KAL init failed, falling back to legacy RAG: %s", e)
        _kal_client = None


class QueryRequest(BaseModel):
    query: str
    character_id: Optional[str] = None
    session_id: Optional[str] = None
    hemisphere: Optional[str] = "auto"  # "left", "right", "both", "auto"
    use_rag: bool = True
    max_tokens: int = 512


class QueryResponse(BaseModel):
    response: str
    hemisphere_used: str
    confidence: float
    agreement_score: Optional[float] = None
    character_id: Optional[str] = None
    latency_ms: float
    rag_sources: Optional[list] = None


async def verify_api_key(x_api_key: str = Header(...)):
    """Validate API key from request header."""
    # TODO: Replace with real key validation from DB
    if not x_api_key or len(x_api_key) < 16:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


@app.get("/health")
async def health_check():
    """API health check endpoint."""
    kernel_status = bridge.ping_kernel()
    return {
        "status": "operational",
        "kernel": "up" if kernel_status else "down",
        "rag_vectors": rag.total_vectors,
        "version": "2.0.0"
    }


@app.post("/query", response_model=QueryResponse)
async def query_synthesus(
    request: QueryRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Main query endpoint. Routes to appropriate hemisphere based on query type.
    Uses RAG pipeline for context retrieval when enabled.
    """
    start_time = time.time()

    # Load character context if specified
    character_context = None
    if request.character_id:
        character_context = character_loader.load(request.character_id)
        if not character_context:
            raise HTTPException(status_code=404, detail=f"Character '{request.character_id}' not found")

    # RAG context retrieval — via KAL when enabled, else legacy RAGPipeline
    rag_sources = None
    rag_context = ""
    if request.use_rag:
        if _kal_client and _kal_config.use_for_retrieval:
            # ── KAL path ──
            filters = {}
            if request.character_id:
                filters["character_id"] = request.character_id
            kal_result = await _kal_client.query_knowledge(
                question=request.query,
                filters=filters,
            )
            # Convert KalResult → context string + sources list
            rag_context = "\n\n".join(item.text for item in kal_result.results if item.text)
            rag_sources = [
                {"pattern": item.metadata.get("source", ""),
                 "score": round(item.score, 4),
                 "character": item.metadata.get("character", "global")}
                for item in kal_result.results
            ]
        else:
            # ── Legacy path ──
            rag_result = await rag.retrieve(request.query, character_id=request.character_id)
            rag_context = rag_result.get("context", "")
            rag_sources = rag_result.get("sources", [])

    # Route to hemisphere
    result = await bridge.route_query(
        query=request.query,
        hemisphere=request.hemisphere,
        character_context=character_context,
        rag_context=rag_context,
        max_tokens=request.max_tokens
    )

    # Calibrate confidence
    confidence = calibrator.calibrate(
        result["raw_confidence"],
        result["hemisphere_used"],
        agreement_score=result.get("agreement_score")
    )

    latency_ms = (time.time() - start_time) * 1000

    return QueryResponse(
        response=result["response"],
        hemisphere_used=result["hemisphere_used"],
        confidence=confidence,
        agreement_score=result.get("agreement_score"),
        character_id=request.character_id,
        latency_ms=latency_ms,
        rag_sources=rag_sources
    )


@app.get("/characters")
async def list_characters(api_key: str = Depends(verify_api_key)):
    """List all available character genomes."""
    return character_loader.list_all()


@app.get("/characters/{character_id}")
async def get_character(
    character_id: str,
    api_key: str = Depends(verify_api_key)
):
    """Get character genome manifest."""
    character = character_loader.load(character_id)
    if not character:
        raise HTTPException(status_code=404, detail=f"Character '{character_id}' not found")
    return character


@app.get("/kernel/status")
async def kernel_status(api_key: str = Depends(verify_api_key)):
    """Get detailed kernel statistics."""
    return bridge.get_kernel_stats()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000, log_level="info")
