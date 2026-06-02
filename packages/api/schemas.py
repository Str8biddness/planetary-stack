"""Synthesus 5 CHAL API schemas for request/response validation."""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import time


class ProcessRequest(BaseModel):
    """Request model for the /process endpoint."""
    text: str = Field(..., description="Input text to process", min_length=1)
    character_id: str = Field("default", description="Character profile ID")
    session_id: Optional[str] = Field(None, description="Session ID for continuity")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    stream: bool = Field(False, description="Whether to stream response tokens")


class ProcessResponse(BaseModel):
    """Response model for the /process endpoint."""
    text: str = Field(..., description="Generated response text")
    character_id: str = Field(..., description="Character that responded")
    session_id: str = Field(..., description="Session ID")
    hemisphere_data: Optional[Dict[str, Any]] = Field(None, description="Hemisphere debug info")
    reasoning_trace: Optional[List[str]] = Field(None, description="Reasoning steps")
    timestamp: float = Field(default_factory=time.time)
    processing_ms: Optional[float] = Field(None, description="Processing time in ms")


class SpawnCharacterRequest(BaseModel):
    """Request model for the /api/v1/characters endpoint."""
    name: str = Field(..., description="Character display name")
    id: Optional[str] = Field("", description="Character ID (optional)")
    archetype: str = Field("merchant", description="Archetype name")
    setting: str = Field("medieval_fantasy", description="World setting")
    traits: List[str] = Field(default_factory=list, description="List of traits")
    backstory: str = Field("", description="Custom backstory")
    location: str = Field("", description="Location")
    establishment: str = Field("", description="Establishment name")
    specialty: str = Field("", description="Specialty")
    rank: str = Field("", description="Rank")
    years: int = Field(20, description="Years of experience")
    inventory_desc: str = Field("", description="Inventory description")


class CharacterResponse(BaseModel):
    """Response model for character operations."""
    character_id: str
    name: str
    archetype: str
    traits: Dict[str, float]
    created_at: float = Field(default_factory=time.time)


class HealthResponse(BaseModel):
    """Response model for the /health endpoint."""
    status: str = "ok"
    version: str = "2.0.0"
    uptime_seconds: float
    subsystems: Dict[str, str]


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


# --- Admin API Models ---

class AdminAPIKeyRequest(BaseModel):
    """Request to create a new API key."""
    label: str = Field(..., description="Description for this key")
    expiry_days: Optional[int] = Field(None, description="Days until expiry")

class AdminAPIKeyResponse(BaseModel):
    """Information about an API key."""
    key: str
    label: str
    created_at: str
    last_used: Optional[str] = None
    status: str = "active"

class AdminUsageStatistics(BaseModel):
    """System-wide usage statistics."""
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_latency_ms: float
    organ_usage_breakdown: Dict[str, int]
    daily_traffic: List[Dict[str, Any]]


# --- Query & Chat Models ---

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="The query text")
    character: str = Field(default="synth", description="Character ID to route to")
    mode: str = Field(
        default="auto",
        description=(
            "Processing mode: auto|chal|business_bot|cognitive|rag|pattern. Use "
            "chal to route explicitly through the Synthesus 5 Cognitive Hypervisor; "
            "business_bot is a CHAL preset for concise action-oriented answers; "
            "auto preserves the legacy-compatible production pipeline."
        ),
    )
    runtime_preset: Optional[str] = Field(
        default=None,
        description=(
            "Optional Synthesus 5 runtime preset. The only named preset with "
            "specialized behavior is business_bot; aliases business, "
            "business-bot, and businessbot normalize to business_bot, while "
            "default/none/null means default CHAL routing."
        ),
    )
    session_id: Optional[str] = Field(default=None, description="Session ID for multi-turn")
    player_id: str = Field(default="default", description="Player/user ID for relationship tracking")
    include_sources: bool = Field(default=False, description="Include RAG source citations")
    include_debug: bool = Field(default=False, description="Include debug telemetry")


class LegacyQueryRequest(BaseModel):
    """Legacy clients sometimes use 'text' instead of 'query'"""
    text: Optional[str] = Field(default=None, max_length=2000)
    query: Optional[str] = Field(default=None, max_length=2000)
    character: str = Field(default="synth")
    mode: str = Field(default="auto")
    runtime_preset: Optional[str] = Field(default=None)
    session_id: Optional[str] = Field(default=None)
    player_id: str = Field(default="default")
    include_sources: bool = Field(default=False)
    include_debug: bool = Field(default=False)


class FeedbackRequest(BaseModel):
    session_id: str
    query: str
    response: str
    rating: int = Field(..., ge=1, le=5)
    comments: Optional[str] = None


class QueryResponse(BaseModel):
    response: str
    confidence: float
    character: str
    source: str = Field(
        ...,
        description=(
            "Runtime source that produced the response, such as zo_kernel, "
            "symbolic_core, cognitive_hypervisor, cognitive, synthesus_master, "
            "rag, or fallback."
        ),
    )
    session_id: str
    latency_ms: float
    sources: Optional[List[Dict[str, Any]]] = None
    emotion: Optional[str] = None
    relationship: Optional[Dict[str, Any]] = None
    debug: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional implementation telemetry returned only when include_debug "
            "is true. Current keys include kernel_triggered, symbolic_triggered, "
            "trace, rag, ml_swarm, cognitive_hypervisor, and fallback diagnostics. "
            "For explicit mode=chal calls, cognitive_hypervisor follows the "
            "CognitiveHypervisorTrace OpenAPI component, including typed "
            "QuadBrainArbitration records when route=quad_brain_path. CGPU "
            "candidate-set trace records should also live here as the runtime "
            "wiring expands without changing the stable response envelope."
        ),
    )


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None


class CharacterInfo(BaseModel):
    id: str
    name: str
    role: str
    description: str
    domains: List[str]
    personality_traits: List[str]
    ethics_disclosure: Optional[str] = None


class EvolutionDirective(BaseModel):
    add_knowledge: List[str]
    update_traits: Dict[str, Any]

class CharacterEvolutionResponse(BaseModel):
    status: str
    character_id: str
    directives: EvolutionDirective
    files_updated: List[str]
    message: Optional[str] = None


class PatternIngest(BaseModel):
    """Schema for pattern ingestion."""
    pattern: str
    response: Optional[str] = None
    source: Optional[str] = "manual"
    domain: Optional[str] = "general"
    character_id: Optional[str] = None
    create_character: bool = False
