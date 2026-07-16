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
    uptime_seconds: float = 0.0
    subsystems: Dict[str, str] = Field(default_factory=dict)
    # 5.0 detailed health — all optional so the endpoint can report rich status
    # (get_health populates these; the frontend LLM banner reads `llm`).
    ml_swarm_active: bool = False
    ml_models_loaded: Dict[str, Any] = Field(default_factory=dict)
    llm: Dict[str, Any] = Field(default_factory=dict)
    cognitive_engine_active: bool = False
    rag_active: bool = False
    active_sessions: int = 0
    total_requests: int = 0


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
            "CHALReasoningQualityTrace verifier telemetry, "
            "CHALReasoningRevisionRouteHint scheduler-only rewrite pressure, "
            "CHALReasoningRevisionTrace bounded CGPU/critic revision telemetry, "
            "CHALGroundingRerankerTrace context-selection telemetry, "
            "QuadBrainArbitration records when route=quad_brain_path, "
            "including state-contract arbitration_steps, QuadBrainReplayRecord, "
            "and QuadBrainTraceStorage metadata for compact replay/storage traces, "
            "and CHALMemoryWritebackResult records when the API attempts "
            "post-arbitration memory writeback. CGPU candidate-set trace "
            "records should also live here as the runtime wiring expands without "
            "changing the stable response envelope. "
            "Legacy-compatible template exceptions are labeled under "
            "debug.template_surface using the TemplateSurface schema."
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


# --- SI Image Generation (procedural VSA/geometric — not diffusion) ---

class ImageRequest(BaseModel):
    """Request for POST /api/v1/image (SI illustration engine)."""
    prompt: str = Field("", max_length=2000, description="Scene description (optional if scene_id + pass_only)")
    resolution: int = Field(
        512,
        ge=128,
        le=2048,
        description=(
            "Long-edge resolution in pixels (128–2048). Default 512 for interactive SI "
            "renders (CPU geometric pipeline, not diffusion); 1024+ is slower — the "
            "per-object SDF fill is ~O(res^2) until the bbox-restricted fill lands."
        ),
    )
    style: str = Field(
        "soft",
        description="Paint style: flat | soft | night | photo (photo = soft + camera look)",
    )
    look: str = Field(
        "photo",
        description=(
            "Camera/TV ISP finish (not diffusion): raw | photo | cinema | vivid | tv. "
            "Applies AE, WB, bloom, DOF, filmic tonemap, sensor noise."
        ),
    )
    seed: Optional[int] = Field(
        None,
        description="Optional deterministic layout seed; omit for prompt-stable default",
    )
    aspect: float = Field(
        1.0,
        ge=0.5,
        le=2.0,
        description="Width/height aspect ratio (0.5–2.0). 1.0 = square.",
    )
    use_cache: bool = Field(
        True,
        description="Serve from memory+disk cache when prompt+params match",
    )
    detail: str = Field(
        "standard",
        description="Render detail: draft (fast preview) | standard | high (richer trees + atmosphere)",
    )
    variations: int = Field(
        1,
        ge=1,
        le=8,
        description="If >1, return multiple seed variations (see variations[] in response)",
    )
    path_mode: bool = Field(
        True,
        description=(
            "CNC path construction for form (G1/arc/offset math). "
            "Not raw G-code UI — SI uses the math to build contours."
        ),
    )
    preset: Optional[str] = Field(
        None,
        description="Cinematic scene preset id (cottage_dawn, harbor_day, city_dusk, …)",
    )
    yaw_deg: float = Field(
        0.0,
        ge=-60.0,
        le=60.0,
        description="Camera orbit yaw degrees (parallax by depth Z)",
    )
    pitch_deg: float = Field(
        0.0,
        ge=-35.0,
        le=35.0,
        description="Camera pitch (tilt) degrees — vertical parallax + horizon shift",
    )
    time_of_day: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Time axis 0=dawn … 0.5=noon … 1=night (sun path)",
    )
    views: int = Field(
        1,
        ge=1,
        le=8,
        description="If >1, multi-view orbit around scene (same world, different yaw)",
    )
    yaw_span: float = Field(
        30.0,
        ge=0.0,
        le=90.0,
        description="Total yaw span degrees when views>1",
    )
    frames: int = Field(
        1,
        ge=1,
        le=8,
        description="If >1, time-of-day sequence (same world, dawn→night)",
    )
    as_gif: bool = Field(
        False,
        description="When frames>1, also attach animated GIF/WebP of the sequence",
    )
    gif_format: str = Field(
        "gif",
        description="Animation format when as_gif: gif | webp",
    )
    gif_duration_ms: int = Field(
        400,
        ge=50,
        le=2000,
        description="Per-frame duration for animation export",
    )
    return_level: bool = Field(
        False,
        description="Attach SI level JSON (scene graph world dump) for virtual-world use",
    )
    orbit_day: bool = Field(
        False,
        description="If true, render orbiting-day sequence (yaw+time together) and optional GIF",
    )
    orbit_frames: int = Field(
        6,
        ge=2,
        le=12,
        description="Frame count when orbit_day=true",
    )
    async_mode: bool = Field(
        False,
        description=(
            "If true, return 202 + job_id immediately; poll GET /api/v1/image/jobs/{id}. "
            "Auto-forced when resolution>=1024 or multi-frame (views/frames/orbit_day)."
        ),
    )
    compile_plan: bool = Field(
        True,
        description=(
            "Compile language → SI scene plan (synonyms + composite puzzle pieces). "
            "Inner monologue + outer_voice honesty labels. Not diffusion."
        ),
    )
    use_llm_plan: Optional[bool] = Field(
        None,
        description=(
            "Optional LLM enrich of the scene plan (Ollama). "
            "None = env SYNTHESUS_IMAGE_LLM_PLAN; False = rules only."
        ),
    )
    return_plan: bool = Field(
        True,
        description="Include scene_plan / monologue / outer_voice in the response",
    )
    keep_session: bool = Field(
        True,
        description="Store scene graph for multi-pass re-render (returns scene_id)",
    )
    scene_id: Optional[str] = Field(
        None,
        description="Existing scene session id for multi-pass (with pass_only/from_scene)",
    )
    pass_only: bool = Field(
        False,
        description="If true with scene_id, re-render stock graph (no re-prompt compile)",
    )
    from_scene: bool = Field(
        False,
        description="Alias for pass_only — multi-pass from scene_id",
    )
    grade: str = Field(
        "none",
        description="Photoshop-lite grade: none|warm|cool|contrast|fade|vivid",
    )
    edit_text: Optional[str] = Field(
        None,
        description="Optional text overlay (picture_edit, not construction)",
    )
    edit_vignette: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Extra vignette amount for picture_edit pass",
    )
    enhance: str = Field(
        "none",
        description=(
            "Post-raster enhance on SI construction (scene graph stays master stock): "
            "none | si_detail | si_upscale2 | realesrgan. "
            "si_* are pure classical/DSP; realesrgan is optional local ONNX neural upscale "
            "(not open-domain diffusion). Loud fail if realesrgan model missing."
        ),
    )
    enhance_strength: float = Field(
        0.55,
        ge=0.0,
        le=1.5,
        description="Strength for si_detail multi-scale unsharp (ignored by realesrgan)",
    )
    playlist: Optional[str] = Field(
        None,
        description="Named multi-pass job on scene_id: finish | orbit_sample | day_cycle",
    )
    level: Optional[Dict[str, Any]] = Field(
        None,
        description="SI level JSON to import as scene stock (re-render path)",
    )


class ImageResponse(BaseModel):
    """Response envelope for SI image generation."""
    ok: bool = True
    engine: str = "synthesus_vsa_geometric"
    prompt: str
    resolution: int
    width: Optional[int] = None
    height: Optional[int] = None
    style: str = "soft"
    detail: str = "standard"
    look: str = "photo"
    seed: Optional[int] = None
    aspect: float = 1.0
    entities: List[str] = Field(default_factory=list)
    entity_count: int = 0
    roles: List[str] = Field(default_factory=list)
    renderable_vocabulary: List[str] = Field(default_factory=list)
    cache_hit: bool = False
    cache_source: Optional[str] = None
    latency_ms: float = 0.0
    image_base64: str = ""
    mime_type: str = "image/png"
    vocab_version: Optional[str] = None
    variations: Optional[List[Dict[str, Any]]] = None
    isp: Optional[Dict[str, Any]] = None
    path_mode: bool = True
    path_entities: Optional[int] = None
    path_ops_sample: Optional[List[str]] = None
    scene_plan: Optional[Dict[str, Any]] = None
    outer_voice: Optional[str] = None
    monologue: Optional[str] = None
    construction: Optional[str] = None
    si_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    composite_parts: Optional[int] = None
    not_diffusion: bool = True
    engine_version: Optional[str] = None
    scene_id: Optional[str] = None
    lathe_parts: Optional[int] = None
    extrude_parts: Optional[int] = None
    picture_edit: Optional[Dict[str, Any]] = None
    stock: Optional[str] = "scene_graph"
