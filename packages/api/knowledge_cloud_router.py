#!/usr/bin/env python3
"""
Knowledge Cloud REST API Router
AIVM Synthesus 2.0

Endpoints for managing and querying the shared Knowledge Cloud.
Mounted at /api/v1/knowledge by the production server.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge-cloud"])

# Reference to the global KnowledgeCloud instance (set by production server)
_cloud = None


def set_knowledge_cloud(cloud):
    """Called by production server at startup to inject the KnowledgeCloud instance."""
    global _cloud
    _cloud = cloud


def _get_cloud():
    if _cloud is None:
        raise HTTPException(status_code=503, detail="Knowledge Cloud not initialized")
    return _cloud


# ── Request / Response Models ────────────────────────────────────────

class KnowledgeEntryRequest(BaseModel):
    """Request body for creating/updating a knowledge entry."""
    entity_id: Optional[str] = None
    entity: str = Field(..., description="Display name of the entity")
    entity_type: str = Field("concept", description="creature, location, item, faction, event, concept")
    description: str = Field("", description="Full prose description")
    attributes: Dict[str, Any] = Field(default_factory=dict)
    facts: List[str] = Field(default_factory=list)
    relations: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)
    depth: str = Field("acquainted", description="intimate, familiar, acquainted, rumor")
    trust_threshold: float = Field(0.0, description="Trust level required (0 = public)")
    emotion_variants: Dict[str, str] = Field(default_factory=dict)


class KnowledgeEntryResponse(BaseModel):
    """Response for a single knowledge entry."""
    entity_id: str
    entity: str
    entity_type: str
    description: str
    attributes: Dict[str, Any]
    facts: List[str]
    relations: Dict[str, Any]
    tags: List[str]
    aliases: List[str]
    depth: str
    trust_threshold: float
    emotion_variants: Dict[str, str]


class SearchResult(BaseModel):
    """A single search result."""
    entity_id: str
    entity: str
    entity_type: str
    description: str
    similarity: float
    facts: List[str]
    tags: List[str]


class SearchResponse(BaseModel):
    """Response for a semantic search."""
    query: str
    results: List[SearchResult]
    count: int


class StatsResponse(BaseModel):
    """Knowledge Cloud statistics."""
    enabled: bool
    total_entries: int
    type_breakdown: Dict[str, int]
    total_aliases: int
    total_searches: int
    total_hits: int
    total_misses: int
    hit_rate: float
    build_time_ms: float
    similarity_floor: float


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/search")
async def search_knowledge(
    q: str = Query(..., description="Search query text"),
    top_k: int = Query(5, ge=1, le=50, description="Number of results"),
    tags: Optional[str] = Query(None, description="Comma-separated tag filter"),
    trust: float = Query(50.0, ge=0, le=100, description="Player trust level"),
    emotion: str = Query("neutral", description="Current NPC emotion"),
) -> Dict[str, Any]:
    """Semantic search across the Knowledge Cloud."""
    cloud = _get_cloud()

    tags_filter = [t.strip() for t in tags.split(",")] if tags else None

    results = cloud.search(q, top_k=top_k, tags_filter=tags_filter)

    return {
        "query": q,
        "results": [
            {
                "entity_id": r.entry.entity_id,
                "entity": r.entry.entity,
                "entity_type": r.entry.entity_type,
                "description": r.entry.description,
                "similarity": round(r.similarity, 4),
                "facts": r.entry.facts,
                "tags": r.entry.tags,
            }
            for r in results
            if trust >= r.entry.trust_threshold
        ],
        "count": len(results),
    }


@router.get("/entries")
async def list_entries(
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    tags: Optional[str] = Query(None, description="Comma-separated tag filter"),
) -> Dict[str, Any]:
    """List all knowledge entries with optional filters."""
    cloud = _get_cloud()

    tags_filter = [t.strip() for t in tags.split(",")] if tags else None
    entries = cloud.list_entries(entity_type=entity_type, tags=tags_filter)

    return {
        "entries": [e.to_dict() for e in entries],
        "count": len(entries),
    }


@router.get("/entries/{entity_id}")
async def get_entry(entity_id: str) -> Dict[str, Any]:
    """Get a specific knowledge entry by ID."""
    cloud = _get_cloud()
    entry = cloud.get_entry(entity_id)

    if not entry:
        raise HTTPException(status_code=404, detail=f"Entry '{entity_id}' not found")

    return entry.to_dict()


@router.post("/entries")
async def create_entry(request: KnowledgeEntryRequest) -> Dict[str, Any]:
    """Add a new knowledge entry to the cloud."""
    cloud = _get_cloud()

    from core.knowledge_cloud import KnowledgeEntry

    entity_id = request.entity_id or request.entity.lower().replace(" ", "_")

    # Check for duplicates
    if cloud.get_entry(entity_id):
        raise HTTPException(status_code=409, detail=f"Entry '{entity_id}' already exists")

    entry = KnowledgeEntry(
        entity_id=entity_id,
        entity=request.entity,
        entity_type=request.entity_type,
        description=request.description,
        attributes=request.attributes,
        facts=request.facts,
        relations=request.relations,
        tags=request.tags,
        aliases=request.aliases,
        depth=request.depth,
        trust_threshold=request.trust_threshold,
        emotion_variants=request.emotion_variants,
    )

    cloud.add_entry(entry)

    return {"status": "created", "entity_id": entity_id, "entry": entry.to_dict()}


@router.put("/entries/{entity_id}")
async def update_entry(entity_id: str, request: KnowledgeEntryRequest) -> Dict[str, Any]:
    """Update an existing knowledge entry."""
    cloud = _get_cloud()

    if not cloud.get_entry(entity_id):
        raise HTTPException(status_code=404, detail=f"Entry '{entity_id}' not found")

    updates = {k: v for k, v in request.dict().items() if v is not None and k != "entity_id"}
    cloud.update_entry(entity_id, updates)

    entry = cloud.get_entry(entity_id)
    return {"status": "updated", "entity_id": entity_id, "entry": entry.to_dict()}


@router.delete("/entries/{entity_id}")
async def delete_entry(entity_id: str) -> Dict[str, Any]:
    """Remove a knowledge entry from the cloud."""
    cloud = _get_cloud()

    if not cloud.remove_entry(entity_id):
        raise HTTPException(status_code=404, detail=f"Entry '{entity_id}' not found")

    return {"status": "deleted", "entity_id": entity_id}


@router.post("/rebuild-index")
async def rebuild_index() -> Dict[str, Any]:
    """Force rebuild the FAISS semantic index."""
    cloud = _get_cloud()
    cloud.rebuild_index()
    stats = cloud.get_stats()
    return {
        "status": "rebuilt",
        "entries_indexed": stats["total_entries"],
        "build_time_ms": stats["build_time_ms"],
    }


@router.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Get Knowledge Cloud statistics."""
    cloud = _get_cloud()
    return cloud.get_stats()
