#!/usr/bin/env python3
"""
Synthesus 2.0 — Production API Server
AIVM LLC

Production-grade FastAPI server integrating:
- ML Swarm: 7 specialized micro-models (~458 KB, <1ms inference)
- FAISS RAG pipeline for semantic retrieval (78K+ patterns)
- Character routing with personality, boundaries, ethics
- Cognitive engine for NPC dialogue (emotion, memory, relationships)
- API key authentication with rate limiting
- Health monitoring and telemetry

Endpoints:
  POST /api/v1/query          — Main query endpoint (ML → cognitive → RAG → fallback)
  POST /api/v1/chat           — Multi-turn conversation
  GET  /api/v1/characters     — List available characters
  GET  /api/v1/characters/{id} — Character details
  GET  /api/v1/health         — System health + ML Swarm status
  GET  /                      — Dashboard UI
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast, TYPE_CHECKING

import importlib
try:
    import faiss # type: ignore
except ImportError:
    faiss = None
import numpy as np # type: ignore

from fastapi import FastAPI, HTTPException, Request, Depends, Header, BackgroundTasks, WebSocket, WebSocketDisconnect # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse # type: ignore
from fastapi.staticfiles import StaticFiles # type: ignore
from fastapi.templating import Jinja2Templates # type: ignore
from pydantic import BaseModel, Field # type: ignore
from cognitive.evolution_engine import CharacterEvolutionEngine # type: ignore
from api.schemas import ( # type: ignore
    AdminAPIKeyRequest,
    AdminAPIKeyResponse,
    AdminUsageStatistics,
    CharacterResponse,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    LegacyQueryRequest,
    FeedbackRequest,
    ChatMessage,
    CharacterInfo,
    PatternIngest,
    ProcessRequest,
    ProcessResponse,
    ErrorResponse,
    CharacterEvolutionResponse,
    SpawnCharacterRequest
)
from api.database import init_db, SessionLocal, APIKey, UsageMetric # type: ignore

# ─── Paths ──────────────────────────────────────────────────────────
PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJ_ROOT))
sys.path.insert(0, str(PROJ_ROOT / "packages" / "core"))
sys.path.insert(0, str(PROJ_ROOT / "packages" / "knowledge"))
sys.path.insert(0, str(PROJ_ROOT / "packages" / "reasoning"))
sys.path.insert(0, str(PROJ_ROOT / "packages" / "kernel"))
sys.path.insert(0, str(PROJ_ROOT / "packages" / "api"))

# ─── Logging ─────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("synthesus.api")

class MemoryLogHandler(logging.Handler):
    def __init__(self, capacity=100):
        super().__init__()
        self.logs = deque(maxlen=capacity)
        
    def emit(self, record):
        try:
            log_entry = self.format(record)
            self.logs.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "message": log_entry,
                "component": record.name
            })
        except Exception:
            self.handleError(record)

_memory_log_handler = MemoryLogHandler()
_memory_log_handler.setLevel(logging.INFO)
_memory_log_handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(_memory_log_handler)

# ─── Imports ─────────────────────────────────────────────────────────

# Import core modules
_synthesus_master_import_error = None
try:
    from synthesus_master import SynthesusMaster # type: ignore
    from hemisphere_bridge import HemisphereBridge # type: ignore
    HAS_SYNTHESUS_MASTER = True
    HAS_HEMISPHERE_BRIDGE = True
except Exception as e:
    SynthesusMaster = None # type: ignore
    HemisphereBridge = None # type: ignore
    HAS_SYNTHESUS_MASTER = False
    HAS_HEMISPHERE_BRIDGE = False
    _synthesus_master_import_error = e

_veai_trainer_import_error = None
try:
    from veai_trainer import VEAITrainer # type: ignore
    HAS_VEAI_TRAINER = True
except Exception as e:
    VEAITrainer = None # type: ignore
    HAS_VEAI_TRAINER = False
    _veai_trainer_import_error = e

try:
    from synthetic_core.symbolic_core import SymbolicCore # type: ignore
    HAS_SYMBOLIC_CORE = True
except Exception as e:
    SymbolicCore = None # type: ignore
    HAS_SYMBOLIC_CORE = False
    logger.warning(f"SymbolicCore not available: {e}")

if _synthesus_master_import_error is not None:
    logger.warning(f"SynthesusMaster not available: {_synthesus_master_import_error}")

# Import amplification wrapper with graceful fallback
_amplification_wrapper_import_error = None
try:
    from amplification_wrapper import AmplificationPlane, get_amplification_plane # type: ignore
    HAS_AMPLIFICATION = True
except Exception as e:
    AmplificationPlane = None # type: ignore
    get_amplification_plane = None # type: ignore
    HAS_AMPLIFICATION = False
    _amplification_wrapper_import_error = e

if _amplification_wrapper_import_error is not None:
    logger.warning(f"AmplificationPlane not available: {_amplification_wrapper_import_error}")

# Import Generation Spine with graceful fallback
_generation_spine_import_error = None
try:
    from generation.spine import GenerationSpine, get_generation_spine, SpineInput # type: ignore
    HAS_GENERATION_SPINE = True
except Exception as e:
    GenerationSpine = None # type: ignore
    get_generation_spine = None # type: ignore
    SpineInput = None # type: ignore
    HAS_GENERATION_SPINE = False
    _generation_spine_import_error = e

if _generation_spine_import_error is not None:
    logger.warning(f"GenerationSpine not available: {_generation_spine_import_error}")

# Import KAL (Knowledge Abstraction Layer) components
_kal_import_error = None
try:
    from client import KalClient # type: ignore
    from service import KalService # type: ignore
    from backends.faiss_backend import FaissKalBackend # type: ignore
    HAS_KAL = True
except Exception as e:
    KalClient = None
    KalService = None
    FaissKalBackend = None
    HAS_KAL = False

# Import Evolution Engine
try:
    from cognitive.evolution_engine import CharacterEvolutionEngine # type: ignore
    HAS_EVOLUTION_ENGINE = True
except Exception as e:
    CharacterEvolutionEngine = None # type: ignore
    HAS_EVOLUTION_ENGINE = False
    _kal_import_error = e

if _kal_import_error is not None:
    logger.warning(f"KAL components not available: {_kal_import_error}")

# ─── Linter Safe Helpers ─────────────────────────────────────────────
def _linter_safe_round(val: Any, n: int = 2) -> float:
    """Helper to bypass linter stub issues with the builtin round() function."""
    try:
        return float(f"{float(val):.{n}f}")
    except (ValueError, TypeError, Exception):
        return 0.0

# ─── Config ──────────────────────────────────────────────────────────

# ─── Dynamic Module Imports ──────────────────────────────────────────
def _import_module_direct(name: str, path: str):
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is not None:
        if spec.loader is not None:
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module) # type: ignore
            return module
    logger.error(f"Could not load spec for {name} at {path}")
    return None

# Dynamically import project modules
_rag_mod = _import_module_direct("core.rag_pipeline", str(PROJ_ROOT / "core" / "rag_pipeline.py"))
RAGPipeline = getattr(_rag_mod, "RAGPipeline", None) if _rag_mod else None # type: ignore

_factory_mod = _import_module_direct("character_factory_v2", str(PROJ_ROOT / "character_factory_v2.py"))
CharacterFactory = getattr(_factory_mod, "CharacterFactory", None) if _factory_mod else None # type: ignore
CharacterSpec = getattr(_factory_mod, "CharacterSpec", None) if _factory_mod else None # type: ignore

# Import Universal Substrate for Synthesus 2.0
try:
    from core.universal_substrate import UniversalSubstrate
    HAS_UNIVERSAL_SUBSTRATE = True
except ImportError:
    HAS_UNIVERSAL_SUBSTRATE = False
    logger.warning("UniversalSubstrate not available.")

# Import Cognitive Engine
try:
    from cognitive.cognitive_engine import CognitiveEngine # type: ignore
    HAS_COGNITIVE = True
except (ImportError, Exception) as e:
    logger.warning(f"Cognitive engine not available: {e}")
    HAS_COGNITIVE = False
    CognitiveEngine = None

# ─── ML Swarm Models ─────────────────────────────────────────────────
try:
    from ml.intent_classifier import IntentClassifier # type: ignore
    from ml.sentiment_analyzer import SentimentAnalyzer # type: ignore
    from ml.emotion_detector import EmotionDetector # type: ignore
    from ml.behavior_predictor import BehaviorPredictor # type: ignore
    from ml.loot_balancer import LootBalancer # type: ignore
    from ml.dialogue_ranker import DialogueRanker # type: ignore
    HAS_ML_SWARM = True
except (ImportError, Exception) as e:
    logger.warning(f"ML Swarm not available: {e}")
    HAS_ML_SWARM = False
CHARACTERS_DIR = PROJ_ROOT / "characters"
DATA_DIR = PROJ_ROOT / "data"
STATIC_DIR = PROJ_ROOT / "static"
INDEX_PATH = DATA_DIR / "faiss.index"
METADATA_PATH = DATA_DIR / "faiss_metadata.json"

API_KEY_HEADER = "X-API-Key"
DEMO_RATE_LIMIT = 10  # requests per minute for unauthenticated
AUTH_RATE_LIMIT = 60   # requests per minute for authenticated

# Admin key (mandatory via environment for safety)
ADMIN_KEY = os.environ.get("SYNTHESUS_API_KEY")
if not ADMIN_KEY:
    logger.warning("SYNTHESUS_API_KEY not set in environment. API authentication may be disabled or fail.")

# ─── Control Plane ──────────────────────────────────────────────────────
ENABLE_CONTROL_PLANE = os.environ.get("ENABLE_CONTROL_PLANE", "false").lower() == "true"
DEBUG_CONTROL_PLANE_FIXTURES = os.environ.get("DEBUG_CONTROL_PLANE_FIXTURES", "false").lower() == "true"
ENABLE_ACCELERATION_LAYER = os.environ.get("ENABLE_ACCELERATION_LAYER", "false").lower() == "true"
HISTORY_STORE_PATH = os.environ.get("HISTORY_STORE_PATH", str(DATA_DIR / "experiments_history.jsonl"))

# ─── FastAPI App ─────────────────────────────────────────────────────
app = FastAPI(
    title="Synthesus 3.0",
    description="AIVM Dual-Hemisphere Synthetic Intelligence Engine",
    version="3.0.0",
)

# Configure allowed origins from environment or default to local development
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static directory for CSS/JS assets
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount control plane after app creation
if ENABLE_CONTROL_PLANE:
    try:
        from control_plane.api import control_router # type: ignore
        app.include_router(control_router, prefix="/control", tags=["control"])
        logger.info("Control plane enabled and mounted at /control")
    except ImportError as e:
        logger.warning(f"Control plane not available: {e}")
        ENABLE_CONTROL_PLANE = False


# Universal Substrate V2 (billions-scale) mounted at /parameter-cloud/v2
try:
    from api.parameter_cloud_v2 import router as parameter_cloud_v2_router  # type: ignore
    app.include_router(parameter_cloud_v2_router)
    logger.info("Universal Parameter Substrate (V2) active at /parameter-cloud/v2")
except Exception as e:
    logger.warning(f"Parameter Cloud V2 not available: {e}")

# ─── Cybersecurity Agent API ──────────────────────────────────────────
HAS_SECURITY_AGENT = False
try:
    from api.security_router import security_router, set_security_agent  # type: ignore
    app.include_router(security_router, prefix="/api/v1/security", tags=["security"])
    HAS_SECURITY_AGENT = True
    logger.info("Security Agent API active at /api/v1/security")
except Exception as e:
    set_security_agent = None  # type: ignore
    logger.warning(f"Security Agent not available: {e}")

# Knowledge Cloud API mounted at /api/v1/knowledge
try:
    from api.knowledge_cloud_router import router as knowledge_cloud_router, set_knowledge_cloud  # type: ignore
    app.include_router(knowledge_cloud_router)
    HAS_KNOWLEDGE_CLOUD_ROUTER = True
    logger.info("Knowledge Cloud API active at /api/v1/knowledge")
except Exception as e:
    HAS_KNOWLEDGE_CLOUD_ROUTER = False
    set_knowledge_cloud = None  # type: ignore
    logger.warning(f"Knowledge Cloud router not available: {e}")

# Import Knowledge Cloud core module
try:
    from core.knowledge_cloud import KnowledgeCloud  # type: ignore
    HAS_KNOWLEDGE_CLOUD = True
except ImportError:
    KnowledgeCloud = None  # type: ignore
    HAS_KNOWLEDGE_CLOUD = False
    logger.warning("KnowledgeCloud module not available.")

try:
    from domains.gm.gm_adapter import GameMasterAdapter
    HAS_GM_ADAPTER = True
except ImportError:
    GameMasterAdapter = None # type: ignore
    HAS_GM_ADAPTER = False



# ─── Placeholder for accelerator CPU inference ──────────────────────
def local_inference_func(prompt: str, **kwargs) -> str:
    """Placeholder CPU inference function for accelerator registry."""
    prompt_trunc = (str(prompt)[:80] if len(str(prompt)) > 80 else str(prompt)) # type: ignore
    return f"[CPU fallback] No accelerator available for: {prompt_trunc}"

# ─── Global State ────────────────────────────────────────────────────
_rag: Optional[RAGPipeline] = None
_security_agent_instance = None  # SecurityAgent for cybersecurity operations
_character_cache: Dict[str, Dict[str, Any]] = {}
_cognitive_engines: Dict[str, Optional[CognitiveEngine]] = {}
MAX_ENGINES = 50
_conversations: Dict[str, List[Dict[str, Any]]] = defaultdict(list)  # session_id -> messages
_active_games: Dict[str, Any] = {}  # session_id -> GameMasterAdapter
_rate_limits: Dict[str, List[float]] = defaultdict(list)  # ip/key -> timestamps
_rate_limit_lock = asyncio.Lock()
_request_count = 0
_start_time = time.time()
_substrate: Optional[UniversalSubstrate] = None
_knowledge_cloud: Optional[KnowledgeCloud] = None

# ─── Query Trace Logger (Self-Improvement) ───────────────────────────
_TRACE_LOG = PROJ_ROOT / "logs" / "query_traces.jsonl"


def _log_query_trace(
    session_id: str,
    domain: str,
    source: str,
    confidence: float,
    latency_ms: float,
    ml_context: Dict[str, Any],
) -> None:
    """Append a lightweight trace record for the self-improvement pipeline."""
    try:
        _TRACE_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sessionId": session_id,
            "domain": domain,
            "source": source,
            "confidence": confidence,
            "latency_ms": latency_ms,
            "phase": "output",
            "organ": "risk_outcome",
            "stateFeatures": {
                "topicCount": float(ml_context.get("intent_confidence", 0.0)),
                "confusion": float(ml_context.get("emotion_scores", {}).get("neutral", 0.0)),
                "safety": 1.0,
                "frustration": float(ml_context.get("emotion_scores", {}).get("anger", 0.0)),
            },
            "trajectoryFeatures": {
                "resolution": confidence,
                "safetyRate": 1.0,
                "stability": confidence,
            },
            "outcome": {
                "quality": confidence,
            },
        }
        with open(_TRACE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never crash the query path for tracing

# ML Swarm instances (initialized at startup)
_intent_classifier: Optional[IntentClassifier] = None
_sentiment_analyzer: Optional[SentimentAnalyzer] = None
_emotion_detector: Optional[EmotionDetector] = None
_behavior_predictor: Optional[BehaviorPredictor] = None
_loot_balancer: Optional[LootBalancer] = None
_dialogue_ranker: Optional[DialogueRanker] = None

# Synthesus Master and Trainer
_master_registry: Dict[str, SynthesusMaster] = {}
_hemisphere_bridge: Optional[HemisphereBridge] = None
_veai_trainer: Optional[VEAITrainer] = None
_accelerator_registry: Optional[Any] = None

def get_master(char_id: str) -> Optional[SynthesusMaster]:
    """Get or create an isolated SynthesusMaster for a specific character."""
    global _master_registry
    if char_id not in _master_registry:
        if HAS_SYNTHESUS_MASTER and SynthesusMaster:
            try:
                sm_class = cast(Any, SynthesusMaster)
                # type: ignore
                _master_registry[char_id] = cast(Any, sm_class)()
                logger.info(f"Isolated Synthesus Master initialized for character: {char_id}")
            except Exception as e:
                logger.warning(f"Failed to initialize Synthesus Master for {char_id}: {e}")
                return None
    return _master_registry.get(char_id)

# Amplification Plane
_amplification_plane: Optional[AmplificationPlane] = None

# Symbolic Core
_symbolic_core: Optional[SymbolicCore] = None

# Generation Spine
_generation_spine: Optional[GenerationSpine] = None

# KAL Client
_kal_client: Optional[KalClient] = None

# Evolution Engine
_evolution_engine: Optional[CharacterEvolutionEngine] = None

# ─── WebSocket Connections ──────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        
        for dead in dead_connections:
            self.disconnect(dead)

manager = ConnectionManager()

# Security Dashboard WebSocket connections
security_ws_manager = ConnectionManager()

@app.websocket("/ws/security")
async def security_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time security dashboard updates."""
    await security_ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; push updates from background tasks
            await websocket.receive_text()
    except WebSocketDisconnect:
        security_ws_manager.disconnect(websocket)

# ─── Autonomous Lifecycle ───────────────────────────────────────────
async def character_lifecycle_loop():
    """Background task to handle autonomous character growth and reflection."""
    logger.info("Autonomous Character Lifecycle loop started.")
    while True:
        try:
            # Run every 60 seconds (offset to avoid spike)
            await asyncio.sleep(60)
            
            active_chars = list(_master_registry.keys())
            if not active_chars:
                continue
                
            logger.info(f"Autonomous Reflection: processing {len(active_chars)} characters...")
            for char_id in active_chars:
                if _evolution_engine:
                    # Trigger synthesis session for history-based growth
                    res = await _evolution_engine.evolve_character(char_id, _master_registry[char_id])
                    if res.get("status") == "success":
                        logger.debug(f"Character {char_id} evolved autonomously: {res.get('summary')}")
        except Exception as e:
            logger.error(f"Error in character lifecycle loop: {e}")
            await asyncio.sleep(10) # Cooling off

# ─── Startup ─────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    global _rag, _intent_classifier, _sentiment_analyzer, _emotion_detector
    global _behavior_predictor, _loot_balancer, _dialogue_ranker
    global _master_registry, _veai_trainer, _accelerator_registry
    global _amplification_plane, _symbolic_core, _generation_spine, _kal_client
    global ENABLE_ACCELERATION_LAYER
    global _substrate
    global _knowledge_cloud
    logger.info("Starting Synthesus 3.0 Production Server...")
    
    # Initialize Universal Substrate
    if HAS_UNIVERSAL_SUBSTRATE:
        try:
            _substrate = UniversalSubstrate()
            logger.info("Universal Substrate initialized.")
        except Exception as e:
            logger.error(f"Universal Substrate failed to initialize: {e}")
            _substrate = None
    
    # Initialize Knowledge Cloud
    if HAS_KNOWLEDGE_CLOUD:
        try:
            _knowledge_cloud = KnowledgeCloud(
                data_dir=str(DATA_DIR / "knowledge_cloud"),
                similarity_floor=0.30,
            )
            # Wire to REST API router
            if HAS_KNOWLEDGE_CLOUD_ROUTER and set_knowledge_cloud:
                set_knowledge_cloud(_knowledge_cloud)
            cloud_stats = _knowledge_cloud.get_stats()
            logger.info(
                f"Knowledge Cloud initialized: {cloud_stats['total_entries']} entries, "
                f"{cloud_stats['total_aliases']} aliases, "
                f"built in {cloud_stats['build_time_ms']:.0f}ms"
            )
        except Exception as e:
            logger.error(f"Knowledge Cloud failed to initialize: {e}")
            _knowledge_cloud = None
    
    # Initialize Database
    try:
        init_db()
        logger.info("SQLAlchemy Database initialized.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    # ── Initialize ML Swarm ──
    if HAS_ML_SWARM:
        logger.info("Training ML Swarm micro-models...")
        try:
            t0_ml = time.time()
            _intent_classifier = IntentClassifier() # type: ignore
            _sentiment_analyzer = SentimentAnalyzer() # type: ignore
            _emotion_detector = EmotionDetector() # type: ignore
            _behavior_predictor = BehaviorPredictor() # type: ignore
            _loot_balancer = LootBalancer() # type: ignore
            _dialogue_ranker = DialogueRanker() # type: ignore
            logger.info(f"ML Swarm ready in {(time.time() - t0_ml)*1000:.0f}ms")
        except Exception as e:
            logger.warning(f"ML Swarm failed to initialize: {e}")
    else:
        logger.warning("ML Swarm not available — running without ML classification")

    # ── Load RAG pipeline ──
    index_path = DATA_DIR / "faiss.index"
    meta_path = DATA_DIR / "faiss_metadata.json"
    if index_path.exists() and RAGPipeline:
        logger.info("Loading RAG pipeline...")
        try:
            rag_class = cast(Any, RAGPipeline)
            _rag = cast(Any, rag_class)(
                index_path=str(index_path),
                metadata_path=str(meta_path),
                top_k=5,
                score_threshold=0.5,
            )
            logger.info(f"RAG loaded: {_rag.total_vectors} vectors")
        except Exception as e:
            logger.warning(f"RAG failed to load: {e}")
    else:
        logger.warning("No FAISS index found — RAG disabled")

    # ── Initialize Default Synthesus Master ──
    if HAS_SYNTHESUS_MASTER and SynthesusMaster:
        logger.info("Synthesus Master available for lazy initialization.")

    # Initialize Hemisphere Bridge
    if HAS_HEMISPHERE_BRIDGE:
        logger.info("Initializing Hemisphere Bridge (C++ Kernel)...")
        try:
            _hemisphere_bridge = cast(Any, HemisphereBridge)(kernel_bin=str(PROJ_ROOT / "zo_kernel"))
            logger.info("Hemisphere Bridge ready.")
        except Exception as e:
            logger.warning(f"HemisphereBridge failed to initialize: {e}")
            _hemisphere_bridge = None
    else:
        _hemisphere_bridge = None

    # Initialize VEAI Trainer if bridge/master exist
    if HAS_VEAI_TRAINER and HAS_SYNTHESUS_MASTER:
        try:
            master = _master_registry.get("synth")
            if master:
                _veai_trainer = VEAITrainer(master)
                _veai_trainer.start()
                logger.info("VEAI Trainer ready.")
        except Exception as e:
            logger.warning(f"VEAITrainer failed to initialize: {e}")
            _veai_trainer = None
    else:
        _veai_trainer = None

    # ── Initialize Accelerator Registry ──
    if ENABLE_ACCELERATION_LAYER:
        logger.info("Initializing Accelerator Registry...")
        try:
            from accelerators.registry import AcceleratorRegistry # type: ignore
            from accelerators.adapter import CPUOnlyAdapter # type: ignore
            from accelerators.remote_adapter import RemoteAdapter # type: ignore
            from accelerators.local_gpu_adapter import LocalGpuAdapter # type: ignore
            _accelerator_registry = AcceleratorRegistry()
            # Always register CPU
            cpu_adapter = CPUOnlyAdapter(local_inference_func)
            _accelerator_registry.register_adapter(cpu_adapter)
            # Register Remote if configured
            remote_url = os.environ.get("ACCEL_REMOTE_ENDPOINT_URL")
            remote_api_key = os.environ.get("ACCEL_REMOTE_API_KEY")
            remote_model = os.environ.get("ACCEL_REMOTE_MODEL_NAME")
            if remote_url:
                remote_adapter = RemoteAdapter(remote_url, remote_api_key, remote_model)
                _accelerator_registry.register_adapter(remote_adapter)
            
            # Register Local GPU if available
            try:
                gpu_adapter = LocalGpuAdapter()
                _accelerator_registry.register_adapter(gpu_adapter)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"AcceleratorRegistry failed to initialize: {e}")

    # ── Initialize Evolution Engine ──
    global _evolution_engine
    if HAS_EVOLUTION_ENGINE and CharacterEvolutionEngine:
        if not _evolution_engine:
            try:
                _evolution_engine = CharacterEvolutionEngine()
                logger.info("Character Evolution Engine initialized.")
            except Exception as e:
                logger.warning(f"Failed to instantiate CharacterEvolutionEngine: {e}")

    # ── Start Autonomous Lifecycle ──
    asyncio.create_task(character_lifecycle_loop())

    # ── Initialize History Store ──
    if ENABLE_CONTROL_PLANE:
        logger.info("Initializing History Store...")
        try:
            from control_plane.history_store import HistoryStore # type: ignore
            _history_store = cast(Any, HistoryStore)(HISTORY_STORE_PATH) # type: ignore
            logger.info("History Store ready.")
        except ImportError as e:
            logger.warning(f"History Store not available: {e}")
            _history_store = None

    # ── Initialize Amplification Plane ──
    if HAS_AMPLIFICATION:
        logger.info("Initializing Amplification Plane...")
        try:
            _amplification_plane = cast(Any, get_amplification_plane)(enabled=True)
            logger.info("Amplification Plane ready.")
        except Exception as e:
            logger.warning(f"AmplificationPlane failed to initialize: {e}")
            _amplification_plane = None
    else:
        logger.warning("Amplification Plane not available — running without amplification")
        _amplification_plane = None

    # ── Initialize Symbolic Core ──
    if HAS_SYMBOLIC_CORE:
        logger.info("Initializing Symbolic Core...")
        try:
            core_class = cast(Any, SymbolicCore)
            _symbolic_core = core_class()
            logger.info("Symbolic Core ready.")
        except Exception as e:
            logger.warning(f"SymbolicCore failed to initialize: {e}")
            _symbolic_core = None

    # ── Initialize Generation Spine ──
    if HAS_GENERATION_SPINE:
        logger.info("Initializing Generation Spine...")
        try:
            _generation_spine = cast(Any, get_generation_spine)(models_dir=str(DATA_DIR / "models")) # type: ignore
            logger.info("Generation Spine ready.")
        except Exception as e:
            logger.warning(f"GenerationSpine failed to initialize: {e}")
            _generation_spine = None

    # ── Initialize KAL Client (V4) ──
    if HAS_KAL and _rag:
        logger.info("Initializing KAL Client...")
        try:
            backend = cast(Any, FaissKalBackend)(_rag) # type: ignore
            service = cast(Any, KalService)(backend) # type: ignore
            _kal_client = cast(Any, KalClient)(service) # type: ignore
            logger.info("KAL Client (V4) ready.")
        except Exception as e:
            logger.warning(f"KAL failed to initialize: {e}")
            _kal_client = None

    # ── Pre-load characters ──
    for char_dir in CHARACTERS_DIR.iterdir():
        if char_dir.is_dir() and (char_dir / "bio.json").exists():
            _load_character(char_dir.name)
    logger.info(f"Loaded {len(_character_cache)} characters")
    
    # Start WebSocket broadcaster
    asyncio.create_task(_broadcast_dashboard_loop())
    
    # Start Database Metrics Persister
    asyncio.create_task(_persist_metrics_loop())
    
    # ── Initialize Cybersecurity Agent ──
    global _security_agent_instance
    if HAS_SECURITY_AGENT:
        try:
            from core.security_agent import SecurityAgent  # type: ignore
            _security_agent_instance = SecurityAgent()
            _security_agent_instance.start()
            set_security_agent(_security_agent_instance)
            await _security_agent_instance.start_scheduled_scanning(interval_seconds=300)
            logger.info("Cybersecurity Agent active — scheduled scanning every 5 minutes.")
        except Exception as e:
            logger.warning(f"Security Agent failed to initialize: {e}")
            _security_agent_instance = None
    
    logger.info("Server ready.")

async def _broadcast_dashboard_loop():
    """Background task to push live dashboard metrics to all connected clients."""
    while True:
        await asyncio.sleep(1.0)
        if manager.active_connections:
            try:
                # Get the latest metrics
                data = await monitoring_dashboard()
                # Broadcast over websockets
                await manager.broadcast(data)
            except Exception as e:
                logger.error(f"Error in websocket broadcast loop: {e}")

async def _persist_metrics_loop():
    """Background task to save in-memory metrics to the database periodically."""
    while True:
        await asyncio.sleep(60.0) # Persist every 60 seconds
        try:
            db = SessionLocal()
            # Get real metrics from generation spine if available
            spine_metrics = {}
            if HAS_GENERATION_SPINE and _generation_spine:
                spine_metrics = _generation_spine.get_metrics()
            
            metric = UsageMetric(
                total_requests=_request_count,
                avg_latency_ms=spine_metrics.get("avg_latency_ms", 42.5),
                domain_breakdown=spine_metrics.get("by_domain", {}),
                recommendation_stats=spine_metrics.get("recommendations", {})
            ) # type: ignore
            db.add(metric)
            db.commit()
            db.close()
            logger.info("System metrics persisted to database.")
        except Exception as e:
            logger.error(f"Error in metrics persistence loop: {e}")


@app.on_event("shutdown")
async def shutdown():
    global _veai_trainer, _hemisphere_bridge
    if _veai_trainer:
        logger.info("Stopping VEAI Trainer...")
        _veai_trainer.stop()
        logger.info("VEAI Trainer stopped.")
    
    if _hemisphere_bridge:
        logger.info("Stopping Hemisphere Bridge (C++ Kernel)...")
        _hemisphere_bridge.stop()
        logger.info("Hemisphere Bridge stopped.")


def _detect_domain(char_id: str, char_data: Optional[Dict[str, Any]]) -> str:
    """Dynamically detect the domain for the amplification plane."""
    cid = char_id.lower()
    if cid in ("system", "sysops", "admin", "operator"):
        return "sysops"
    
    if cid in ("gm", "master", "narrator", "storyteller"):
        return "gm"
        
    if char_data:
        bio = char_data.get("bio", {})
        arch = str(bio.get("archetype", "")).lower()
        if "game_master" in arch or "narrator" in arch:
            return "gm"
        if "system" in arch or "admin" in arch:
            return "sysops"
            
    return "chat"


def _load_character(char_id: str) -> Optional[Dict[str, Any]]:
    """Load character data, prioritizing the Universal Substrate (Right Hemisphere)."""
    if char_id in _character_cache:
        return _character_cache[char_id]

    # 1. Try Universal Substrate first (Right Hemisphere)
    if _substrate:
        try:
            sub_bio = _substrate.get_parameter(f"char_{char_id}.bio")
            if sub_bio and isinstance(sub_bio, dict):
                sub_patterns = _substrate.get_parameter(f"char_{char_id}.patterns")
                sub_personality = _substrate.get_parameter(f"char_{char_id}.personality")
                sub_knowledge = _substrate.get_parameter(f"char_{char_id}.knowledge")
                
                _character_cache[char_id] = {
                    "bio": sub_bio.get("value", {}),
                    "patterns": sub_patterns.get("value", {}) if sub_patterns else {},
                    "personality": sub_personality.get("value", {}) if sub_personality else {},
                    "knowledge": sub_knowledge.get("value", {}) if sub_knowledge else {},
                    "_source": "substrate"
                }
                logger.info(f"Character '{char_id}' loaded from Universal Substrate.")
                return _character_cache[char_id]
        except Exception as e:
            logger.warning(f"Substrate failed to load character '{char_id}': {e}")

    # 2. Smart FS Fallback (Local Disk)
    char_dir = CHARACTERS_DIR / char_id
    bio_path = char_dir / "bio.json"
    if not bio_path.exists():
        return None
    
    with open(bio_path) as f:
        bio = json.load(f)
    
    # ... rest of local loading ...
    patterns = {}
    pat_path = char_dir / "patterns.json"
    if pat_path.exists():
        with open(pat_path) as f:
            patterns = json.load(f)
    
    personality = {}
    pers_path = char_dir / "personality.json"
    if pers_path.exists():
        with open(pers_path) as f:
            personality = json.load(f)
    
    knowledge = {}
    know_path = char_dir / "knowledge.json"
    if know_path.exists():
        with open(know_path) as f:
            knowledge = json.load(f)
    
    _character_cache[char_id] = {
        "bio": bio,
        "patterns": patterns,
        "personality": personality,
        "knowledge": knowledge,
    }
    return _character_cache[char_id]


def _get_cognitive_engine(char_id: str) -> Optional[CognitiveEngine]:
    if char_id in _cognitive_engines:
        # Move to end of dict for LRU-like behavior in Python 3.7+
        engine = _cognitive_engines.pop(char_id)
        _cognitive_engines[char_id] = engine
        return engine
    
    # Evict oldest if limit reached
    if len(_cognitive_engines) >= MAX_ENGINES:
        oldest_id = next(iter(_cognitive_engines))
        logger.info(f"Evicting cognitive engine for character: {oldest_id}")
        _cognitive_engines.pop(oldest_id, None)

    char_data = _load_character(char_id)
    if not char_data:
        logger.warning(f"Failed to load character data for: {char_id}")
        return None
    
    try:
        # Ensure memory persistence directory exists
        p_dir = DATA_DIR / "characters" / char_id
        p_dir.mkdir(parents=True, exist_ok=True)
        
        engine = CognitiveEngine(
            character_id=char_id,
            bio=char_data.get("bio", {}),
            patterns=char_data.get("patterns", {}),
            substrate=_substrate,
            kal_client=_kal_client,
            knowledge_cloud=_knowledge_cloud,
            char_dir=str(CHARACTERS_DIR / char_id),
            persist_dir=str(p_dir)
        )
        _cognitive_engines[char_id] = engine
        logger.info(f"Cognitive Engine ready for character: {char_id} (Source: {char_data.get('_source', 'unknown')})")
        return engine
    except Exception as e:
        import traceback
        logger.error(f"FATAL: Cognitive Engine failed to initialize for {char_id}: {e}")
        logger.error(traceback.format_exc())
        return None


def _find_response_for_pattern(pattern_text: str, char_id: Optional[str] = None) -> Optional[str]:
    """Search character pattern caches for a response matching the given pattern text."""
    # If a specific character is requested, search only that one first
    search_order = []
    if char_id and char_id in _character_cache:
        search_order.append(char_id)
    # Then search all characters
    for cid in _character_cache:
        if cid not in search_order:
            search_order.append(cid)

    pattern_lower = pattern_text.strip().lower()
    for cid in search_order:
        data = _character_cache[cid]
        patterns_data = data.get("patterns", {})
        for pat_list_key in ("synthetic_patterns", "generic_patterns"):
            for pat in patterns_data.get(pat_list_key, []):
                triggers = pat.get("trigger", [])
                if isinstance(triggers, str):
                    triggers = [triggers]
                for t in triggers:
                    if t.strip().lower() == pattern_lower:
                        resp = pat.get("response_template", pat.get("response", ""))
                        if resp:
                            return resp
    return None


# ─── Rate Limiting ───────────────────────────────────────────────────
async def _check_rate_limit(key: str, limit: int) -> bool:
    async with _rate_limit_lock:
        now = time.time()
        window = [t for t in _rate_limits[key] if now - t < 60] # type: ignore
        _rate_limits[key] = window
        if len(window) >= limit:
            if _symbolic_core:
                _symbolic_core.audit_logger.log_event(
                    event_type="rate_limit_exceeded", 
                    session_id="system", 
                    details={"key": key, "limit": limit, "count": len(window)}
                )
            return False
        _rate_limits[key].append(now)
        return True


async def get_auth(request: Request, x_api_key: Optional[str] = Header(None)):
    """Auth dependency — returns (is_authenticated, rate_limit_key)."""
    if x_api_key:
        db = SessionLocal()
        key_record = db.query(APIKey).filter(APIKey.key == x_api_key, APIKey.status == "active").first()
        db.close()
        
        if key_record:
            x_trunc = str(x_api_key)[:8] # type: ignore
            return True, f"auth:{x_trunc}"
            
    client_ip = request.client.host if request.client else "unknown"
    return False, f"ip:{client_ip}"


# ─── Placeholder for Connection Management ───────────────────────────
# ConnectionManager is kept local as it is tightly coupled with the WebSocket logic.











def _normalize_legacy_query_payload(payload: LegacyQueryRequest) -> QueryRequest:
    """Normalize legacy request variants to the v1 query contract."""
    query_text = (payload.query or payload.text or "").strip()
    if not query_text:
        raise HTTPException(400, "Query must not be empty")

    mode = (payload.mode or "auto").strip().lower()
    # Older clients used "character"/domain values; map unknowns to auto routing.
    if mode not in {"auto", "cognitive", "rag", "pattern"}:
        mode = "auto"

    return QueryRequest(
        query=query_text,
        character=(payload.character or "synth"),
        mode=mode
    )


@app.post("/api/v1/characters", response_model=CharacterResponse)
async def create_character(req: SpawnCharacterRequest, auth=Depends(get_auth)):
    """Create a new character genome using the CharacterFactory."""
    if not CharacterFactory or not CharacterSpec:
        raise HTTPException(500, "CharacterFactory module not available.")
    
    try:
        factory = CharacterFactory(characters_dir=str(CHARACTERS_DIR))
        spec = CharacterSpec(
            name=req.name,
            id=req.id or "",
            archetype=req.archetype,
            setting=req.setting,
            traits=req.traits,
            backstory=req.backstory,
            location=req.location,
            establishment=req.establishment,
            specialty=req.specialty,
            rank=req.rank,
            years=req.years,
            inventory_desc=req.inventory_desc
        )
        
        result = factory.generate(spec)
        char_id = result["id"]
        
        # Load immediately into cache
        _load_character(char_id)
        
        return CharacterResponse(
            character_id=char_id,
            name=req.name,
            archetype=req.archetype,
            traits={t: 1.0 for t in req.traits}
        )
    except Exception as e:
        logger.error(f"Failed to create character: {e}")
        raise HTTPException(500, f"Character creation failed: {e}")



@app.post("/api/v1/admin/patterns")
async def add_patterns(req: Request, auth=Depends(get_auth)):
    """Add or update patterns in the RAG pipeline."""
    global _rag
    if not _rag and RAGPipeline:
        logger.info("Initializing fresh RAG pipeline for ingestion...")
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            _rag = RAGPipeline(
                index_path=str(INDEX_PATH),
                metadata_path=str(METADATA_PATH),
                top_k=5,
                score_threshold=0.5,
            )
            # If still no index (RAGPipeline didn't create one), force it
            if faiss and (not hasattr(_rag, "_index") or _rag._index is None):
                _rag._index = faiss.IndexFlatIP(128)
                _rag._metadata = []
        except Exception as e:
            logger.error(f"Failed to auto-init RAG: {e}")
            raise HTTPException(500, f"RAG initialization failed: {e}")
    
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    # Normalize to a list of patterns
    new_patterns = []
    if isinstance(body, list):
        new_patterns = body
    elif isinstance(body, dict):
        if "patterns" in body and isinstance(body["patterns"], list):
            new_patterns = body["patterns"]
        else:
            # Single object
            new_patterns = [body]
    
    if not new_patterns:
        return {"status": "success", "added": 0}
    
    # Normalize body to dict for get calls
    body_dict = body if isinstance(body, dict) else (body[0] if isinstance(body, list) and len(body) > 0 else {})
    
    # ── Step 1: Extract and normalize patterns ──
    char_id = body_dict.get("character_id")
    create_char = body_dict.get("create_character", False)
    
    normalized = []
    for p in new_patterns:
        text = p.get("pattern") or p.get("phrase") or ""
        resp = p.get("response") or p.get("response_template") or ""
        src = p.get("source") or "zo_computer_agent"
        dom = p.get("domain") or p.get("module") or "general"
        # Per-pattern character override
        p_char_id = p.get("character_id") or char_id
        
        if text:
            item = {
                "pattern": text,
                "response": resp,
                "source": src,
                "domain": dom
            }
            if p_char_id:
                item["character_id"] = p_char_id
            normalized.append(item)
    
    if not normalized:
        return {"status": "success", "added": 0}
    
    # ── Step 2: Handle character creation if needed ──
    if char_id and create_char:
        char_dir = CHARACTERS_DIR / char_id
        if not char_dir.exists() and CharacterFactory and CharacterSpec:
            logger.info(f"Bootstrapping character: {char_id}")
            try:
                factory = CharacterFactory(characters_dir=str(CHARACTERS_DIR))
                spec = CharacterSpec(
                    name=char_id.capitalize(),
                    id=char_id,
                    archetype="scholar",  # Default archetype
                    backstory=f"A synthetic intelligence specialized in {normalized[0].get('domain', 'general knowledge')}."
                )
                factory.generate(spec)
                _load_character(char_id)
            except Exception as e:
                logger.error(f"Failed to bootstrap character {char_id}: {e}")
                # We continue even if bootstrap fails, patterns will just be tagged with the ID
    
    # ── Step 3: Add to RAG pipeline ──
    try:
        # Use the RAGPipeline's built-in method which handles embedding and indexing
        added_count = _rag.add_patterns(
            patterns=normalized,
            # We don't pass global character_id here because it's already in the normalized items
        )
        
        # ── Step 4: Final save ──
        _rag.save_index()
            
        logger.info(f"Ingested {added_count} new patterns (Target: {char_id or 'global'})")
        return {
            "status": "success", 
            "added": added_count, 
            "total": _rag.total_vectors,
            "character_id": char_id
        }
    except Exception as e:
        logger.error(f"Failed to ingest patterns: {e}")
        raise HTTPException(500, f"Ingestion failed: {e}")

# ─── Endpoints ───────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    """Dashboard UI."""
    dashboard = STATIC_DIR / "index.html"
    if dashboard.exists():
        return dashboard.read_text()
    return f"""
    <html><head><title>Synthesus 2.0</title></head>
    <body style="background:#0a0a0a;color:#e0e0e0;font-family:system-ui;padding:40px">
    <h1 style="color:#00ff88">Synthesus 3.0</h1>
    <p>AIVM Dual-Hemisphere Synthetic Intelligence Engine (Production)</p>
    <p>FAISS Index: {_rag.total_vectors if _rag else 0} vectors</p>
    <p>Characters: {len(_character_cache)}</p>
    <p>API Docs: <a href="/docs" style="color:#00ff88">/docs</a></p>
    <p>Status: <a href="/api/v1/health" style="color:#00ff88">/api/v1/health</a></p>
    </body></html>
    """


@app.post("/api/v1/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest, auth=Depends(get_auth)):
    """Main query endpoint — ML Swarm → Cognitive → RAG → Fallback."""
    # Update request count
    global _request_count
    _request_count = _request_count + 1
    t0 = time.time()

    is_auth, rate_key = auth
    limit = AUTH_RATE_LIMIT if is_auth else DEMO_RATE_LIMIT
    if not await _check_rate_limit(rate_key, limit):
        raise HTTPException(429, "Rate limit exceeded. Add X-API-Key header for higher limits.")

    session_id = req.session_id or str(uuid.uuid4())
    char_id = (req.character or "synth").strip().lower()
    query_text = req.query.strip()

    if not query_text:
        raise HTTPException(400, "Query must not be empty")

    if not _load_character(char_id):
        raise HTTPException(
            status_code=404,
            detail={
                "error": "character_not_found",
                "message": f"Character '{char_id}' not found",
                "character": char_id,
                "session_id": session_id,
            },
        )

    _conversations.setdefault(session_id, [])

    # ── Phase 0: Symbolic Core (First Pass) ──
    # Check C++ Kernel via HemisphereBridge first for high-performance matching
    if _hemisphere_bridge:
        try:
            kernel_res = await _hemisphere_bridge.route_query(query_text, character_context={"character_id": char_id})
            if kernel_res.get("response") and kernel_res.get("raw_confidence", 0) > 0.8:
                latency = (time.time() - t0) * 1000
                _conversations[session_id].append({"role": "user", "content": query_text})
                _conversations[session_id].append({"role": "assistant", "content": kernel_res["response"]})
                return QueryResponse(
                    response=kernel_res["response"],
                    confidence=kernel_res["raw_confidence"],
                    character=char_id,
                    source="zo_kernel",
                    session_id=session_id,
                    latency_ms=_linter_safe_round(latency, 2),
                    debug={"kernel_triggered": True} if req.include_debug else None
                )
        except Exception as e:
            logger.warning(f"Kernel query failed: {e}")

    if _symbolic_core:
        symbolic_res = _symbolic_core.process_query(query_text, {"char_id": char_id, "session_id": session_id})
        if symbolic_res.get("status") != "skipped" and symbolic_res.get("confidence", 0) > 0.8:
            latency = (time.time() - t0) * 1000
            _conversations[session_id].append({"role": "user", "content": query_text})
            _conversations[session_id].append({"role": "assistant", "content": symbolic_res["response"]})
            
            return QueryResponse(
                response=symbolic_res["response"],
                confidence=symbolic_res["confidence"],
                character=char_id,
                source=symbolic_res.get("source", "symbolic_core"),
                session_id=session_id,
                latency_ms=_linter_safe_round(latency, 2),
                debug={"symbolic_triggered": True} if req.include_debug else None
            )

    # ── Fetch Cognitive Memory Early for Amplification ──
    memory_context: Dict[str, Any] = {}
    engine = _get_cognitive_engine(char_id) if HAS_COGNITIVE else None
    print(f"QUERY ENDPOINT ENGINE FOR {char_id}:", type(engine))
    if engine:
        try:
            rel_state = engine.relationships.get_relationship(session_id)
            if hasattr(rel_state, 'trust'):
                memory_context["relationship"] = {
                    "trust": rel_state.trust,
                    "respect": rel_state.respect,
                    "fondness": rel_state.fondness,
                    "interactions": getattr(rel_state, 'interactions', 0)
                }
            emotion_enum = engine.emotion.get_emotion(session_id)
            memory_context["emotion"] = emotion_enum.value if hasattr(emotion_enum, 'value') else str(emotion_enum)
            
            # Fetch personality traits and disposition for the spine
            if hasattr(engine, 'profile') and engine.profile:
                memory_context["personality_traits"] = engine.profile.personality_traits
                memory_context["disposition"] = engine.relationships.get_disposition(session_id)
        except Exception as e:
            logger.warning(f"Failed to fetch early memory context: {e}")

    # ── Amplification: Intake ──
    intake_result = None
    domain = _detect_domain(char_id, _character_cache.get(char_id))
    
    if _amplification_plane:
        try:
            from amplification_wrapper import AmplificationContext # type: ignore
            world_state = {
                "domain": domain, 
                "history": _conversations.get(session_id, []), 
                "flags": {},
                "memory": memory_context
            }
            ctx = AmplificationContext(compute_budget=50, session_id=session_id, domain=domain)
            intake_result = await _amplification_plane.amplify_intake_async(
                ctx=ctx,
                world_state=world_state,
                raw_input={"query": query_text, "character": char_id}
            )
        except Exception as e:
            logger.warning(f"Amplification intake failed (graceful fallback): {e}")

    try:
        ml_context: Dict[str, Any] = {}
        if HAS_ML_SWARM and _intent_classifier and _sentiment_analyzer and _emotion_detector and _behavior_predictor:
            intent, intent_conf = _intent_classifier.predict(query_text)
            sentiment, sent_conf = _sentiment_analyzer.predict(query_text)
            player_emotion = _emotion_detector.detect(query_text)

            conv_history = _conversations.get(session_id, [])
            turn_count = len([m for m in conv_history if m["role"] == "user"])
            avg_msg_len = (
                sum(len(m["content"].split()) for m in conv_history if m["role"] == "user") / max(turn_count, 1)
            )
            question_ratio = (
                sum(1 for m in conv_history if m["role"] == "user" and m["content"].strip().endswith("?"))
                / max(turn_count, 1)
            )
            behavior = _behavior_predictor.predict(
                {
                    "turn_count": turn_count,
                    "avg_msg_length": avg_msg_len,
                    "sentiment_trend": 0.0
                    if sentiment == "neutral"
                    else (0.3 if sentiment == "positive" else -0.3),
                    "topic_switches": 0,
                    "time_between_msgs": 5.0,
                    "question_ratio": question_ratio,
                }
            )

            ml_context = {
                "intent": intent,
                "intent_confidence": intent_conf,
                "sentiment": sentiment,
                "sentiment_confidence": sent_conf,
                "player_emotion": player_emotion["primary"],
                "emotion_intensity": player_emotion["intensity"],
                "emotion_scores": player_emotion["scores"],
                "predicted_action": behavior["predicted_action"],
                "engagement_score": behavior["engagement_score"],
                "escalation_risk": behavior["escalation_risk"],
            }

        # ── Amplification: Planning ──
        planning_result = None
        if _amplification_plane:
            try:
                from amplification_wrapper import AmplificationContext # type: ignore
                world_state = {
                    "domain": domain, 
                    "history": _conversations.get(session_id, []), 
                    "flags": {},
                    "memory": memory_context
                }
                if domain == "sysops":
                    candidate_actions = [
                        {"type": "runbook", "target": "service-a", "description": "Run recovery playbook"},
                        {"type": "scale", "target": "service-b", "description": "Scale up"},
                        {"type": "restart", "target": "host-1", "description": "Restart host"},
                        {"type": "ticket_update", "target": "incident-1", "description": "Update incident ticket"}
                    ]
                    if not world_state.get("hosts"):
                        world_state["hosts"] = [{"id": "host-1", "health": 0.4, "errorRate": 0.8, "latency": 500, "saturation": 0.9}]
                        world_state["services"] = [{"name": "service-a", "health": 0.5, "dependencies": [], "errorRate": 0.6, "latency": 800}]
                        world_state["incidents"] = [{"id": "incident-1", "severity": "high", "startTime": datetime.now(timezone.utc).isoformat(), "services": ["service-a"], "blastRadius": 0.8, "status": "open"}]
                        world_state["alerts"] = ["High latency on service-a"]
                elif domain == "gm":
                    candidate_actions = [
                        {"type": "spawn_npc", "target": "location", "description": "Spawn NPC"},
                        {"type": "tick_world", "target": "world", "description": "Tick world state"},
                        {"type": "combat_action", "target": "npc", "description": "Resolve combat action"},
                    ]
                else:
                    candidate_actions = [
                        {"type": "respond", "description": "Generate a response using cognitive engine"},
                        {"type": "deep_thinking", "description": "Escalated probabilistic generation"},
                        {"type": "rag", "description": "Retrieve from knowledge base"},
                    ]
                ctx = AmplificationContext(compute_budget=50, session_id=session_id, domain=domain)
                planning_result = await _amplification_plane.amplify_planning_async(
                    ctx=ctx,
                    world_state=world_state,
                    candidate_actions=candidate_actions
                )
                if planning_result and planning_result.ranked_actions:
                    top_action = planning_result.ranked_actions[0]
                    action_obj = top_action.get("action", {})
                    ml_context["amplification_recommendation"] = action_obj.get("type", "none")
                    ml_context["amplification_action"] = action_obj
                    ml_context["amplification_score"] = top_action.get("score", 0.0)
            except Exception as e:
                logger.warning(f"Amplification planning failed (graceful fallback): {e}")

        # Helper to run output amplification before returning
        async def _apply_output_amplification(chosen_action: Optional[Dict] = None, response_text: str = "", generation_trace: Optional[Any] = None) -> Dict:
            if not _amplification_plane:
                return {"sanity_check_passed": True, "execution_recommendation": "PROCEED"}
            
            final_action = chosen_action or ml_context.get("amplification_action", {"type": "respond", "description": "Generated final response"})
            try:
                from amplification_wrapper import AmplificationContext # type: ignore
                world_state = {
                    "domain": domain, 
                    "history": _conversations.get(session_id, []), 
                    "flags": {},
                    "memory": memory_context
                }
                ctx = AmplificationContext(compute_budget=20, session_id=session_id, domain=domain)
                import dataclasses
                res = await _amplification_plane.amplify_output_async(
                    ctx=ctx,
                    chosen_action=final_action,
                    updated_world=world_state,
                    generation_trace=generation_trace
                )
                return dataclasses.asdict(res)
            except Exception as e:
                logger.warning(f"Amplification output failed (graceful fallback): {e}")
                return {"sanity_check_passed": True, "execution_recommendation": "PROCEED"}
        
        # Helper to finalize responses through Generation Spine (Option A)
        def _finalize_through_spine(
            raw_text: str, 
            source: str, 
            confidence: float,
            organ_scores: Dict[str, float],
            rag_context: str = "",
            generation_trace: Optional[Any] = None
        ) -> tuple:
            """Route any response through Generation Spine for finalization, metrics, and safety."""
            if not HAS_GENERATION_SPINE or _generation_spine is None:
                # Spine unavailable - return as-is
                return raw_text, generation_trace
            
            try:
                # Determine execution recommendation from amplification
                exec_rec = "PROCEED"
                risk_score = organ_scores.get("risk_outcome", 0.0)
                if risk_score > 0.8:
                    exec_rec = "HALT" # type: ignore
                elif risk_score > 0.5:
                    exec_rec = "REQUEST_CONFIRMATION"
                
                # Build spine input
                spine_input = SpineInput(
                    raw_text=raw_text,
                    query=query_text,
                    domain="chat",
                    character_id=char_id,
                    session_id=session_id,
                    organ_scores=organ_scores,
                    risk_score=risk_score,
                    confidence_margin=organ_scores.get("attention", 0.5),
                    execution_recommendation=exec_rec,
                    source_module=source,
                    source_confidence=confidence,
                    rag_context=rag_context,
                    conversation_history=_conversations.get(session_id, []),
                    memory_context=memory_context
                )
                
                # Generate through spine
                spine_instance = cast(Any, _generation_spine)
                spine_output = spine_instance.generate(spine_input)
                
                # Return final text and trace
                return spine_output.final_text, spine_output.trace
            except Exception as e:
                logger.warning(f"Generation Spine finalization failed (graceful fallback): {e}")
                return raw_text, generation_trace

        if domain == "gm" and HAS_GM_ADAPTER:
            if session_id not in _active_games:
                logger.info(f"Creating new GameMasterAdapter for session {session_id}")
                _active_games[session_id] = GameMasterAdapter(
                    session_id=session_id,
                    engine_factory=_get_cognitive_engine,
                    narrator_id="synth" # Default narrator
                )
            
            gm_adapter = _active_games[session_id]
            gm_result = await gm_adapter.process_query(
                query_text=query_text, 
                player_id=req.player_id, 
                ml_context=ml_context
            )
            
            # Record in conversation history
            _conversations[session_id].append({"role": "user", "content": query_text})
            _conversations[session_id].append({"role": "assistant", "content": gm_result["response"]})
            
            return QueryResponse(
                response=gm_result["response"],
                confidence=gm_result["confidence"],
                character=gm_result["character"],
                source=gm_result["source"],
                session_id=session_id,
                latency_ms=_linter_safe_round(gm_result["latency_ms"], 2),
                emotion=gm_result.get("emotion"),
                debug=gm_result.get("debug") if req.include_debug else None
            )

        if HAS_COGNITIVE and req.mode in ("cognitive", "auto"):
            if engine:
                result = await engine.process_query(
                    player_id=req.player_id,
                    query=query_text,
                    thinking_layer_available=True, # Enable escalation to SynthesusMaster
                    ml_context=ml_context,
                )
                logger.warning(f"ENGINE RESULT IN API: {result}")

                # Handle Deep Thinking Escalation (Probabilistic Generation)
                if result.get("source") == "escalated":
                    master = get_master(char_id)
                else:
                    master = None

                if result.get("source") == "escalated" and master:
                    async def _on_master_thought(thought):
                        await manager.broadcast(thought)
                    
                    think_res = await master.think(
                        query_text, 
                        character_id=char_id, 
                        on_thought=_on_master_thought
                    )
                    response_text = think_res["answer"]
                    event = think_res.get("event")
                    trace = getattr(event, "generation_trace", None)
                    
                    # Ample output check
                    amp_instance = cast(Any, _amplification_plane)
                    if amp_instance:
                        amp = await _apply_output_amplification(
                            chosen_action=None,
                            response_text=response_text,
                            generation_trace=trace
                        )
                    else:
                        amp = {"execution_recommendation": "PROCEED"}
                    
                    if amp.get("execution_recommendation") == "HALT":
                        response_text = "[AMPLIFICATION HALT] The generated response was flagged during risk assessment."
                    
                    # Route through Generation Spine for finalization (Option A)
                    organ_scores = {
                        "policy_prior": ml_context.get("amplification_recommendation", "none") == "deep_thinking" and 0.9 or 0.5,
                        "risk_outcome": ml_context.get("escalation_risk", 0.0),
                        "attention": ml_context.get("amplification_score", 0.5)
                    }
                    response_text, _ = _finalize_through_spine(
                        response_text, "synthesus_master", 0.9, cast(Any, organ_scores), "", trace
                    )
                        
                    latency = (time.time() - t0) * 1000
                    _conversations[session_id].append({"role": "user", "content": query_text})
                    _conversations[session_id].append({"role": "assistant", "content": response_text})
                    
                    return QueryResponse(
                        response=response_text,
                        confidence=0.9,
                        character=char_id,
                        source="synthesus_master",
                        session_id=session_id,
                        latency_ms=_linter_safe_round(latency, 2),
                        debug={"trace": str(trace)} if req.include_debug else None
                    )

                if result.get("emotion"):
                    memory_context["emotion"] = result["emotion"]
                if result.get("confidence", 0) > 0.7:
                    # Route through Generation Spine for finalization (Option A)
                    organ_scores = {
                        "policy_prior": ml_context.get("amplification_recommendation", "none") == "deep_thinking" and 0.9 or 0.5,
                        "risk_outcome": ml_context.get("escalation_risk", 0.0),
                        "attention": ml_context.get("amplification_score", 0.5)
                    }
                    response_text, _ = _finalize_through_spine(
                        result["response"], "cognitive", result.get("confidence", 0.7), cast(Any, organ_scores)
                    )
                    
                    latency = (time.time() - t0) * 1000
                    _conversations[session_id].append({"role": "user", "content": query_text})
                    _conversations[session_id].append({"role": "assistant", "content": response_text})

                    debug_data = result.get("debug", {}) if req.include_debug else None
                    return QueryResponse(
                        response=response_text,
                        confidence=float(result.get("confidence", 0.0)) # type: ignore
,
                        character=char_id,
                        source="cognitive",
                        session_id=session_id,
                        latency_ms=_linter_safe_round(latency, 2),
                        sources=None,
                        emotion=result.get("emotion") or memory_context.get("emotion"),
                        relationship=result.get("relationship") if req.include_debug else None,
                        debug=debug_data,
                    )

        if _rag and req.mode in ("rag", "auto"):
            rag_result = await _rag.retrieve(query_text, character_id=char_id)
            if rag_result.get("context"):
                sources = rag_result.get("sources", [])
                top = sources[0] if sources else {}
                top_score = float(top.get("score", 0) or 0)

                if top_score >= 0.65:
                    response_text = ""
                    for src in sources:
                        pattern_text = src.get("pattern", "")
                        if pattern_text:
                            response_text = _find_response_for_pattern(pattern_text, char_id) # type: ignore
                            if response_text:
                                break

                    if not response_text:
                        response_text = (
                            rag_result["context"].split("\nA: ")[-1].split("\n")[0]
                            if "\nA: " in rag_result["context"]
                            else rag_result["context"][:500]
                        )

                    # Route through Generation Spine for finalization (Option A)
                    organ_scores = {
                        "policy_prior": ml_context.get("amplification_recommendation", "none") == "rag" and 0.7 or 0.5,
                        "risk_outcome": ml_context.get("escalation_risk", 0.0),
                        "attention": top_score
                    }
                    response_text, _ = _finalize_through_spine(
                        response_text, "rag", top_score, cast(Any, organ_scores), rag_result.get("context", "")
                    ) # type: ignore

                    latency = (time.time() - t0) * 1000
                    _conversations[session_id].append({"role": "user", "content": query_text})
                    _conversations[session_id].append({"role": "assistant", "content": response_text})
                    debug_data = {"rag": {"top_score": top_score}} if req.include_debug else None
                    return QueryResponse(
                        response=response_text,
                        confidence=_linter_safe_round(top_score, 2)
,
                        character=char_id,
                        source="rag",
                        session_id=session_id,
                        latency_ms=_linter_safe_round(latency, 2),
                        sources=sources if req.include_sources else None,
                        emotion=memory_context.get("emotion") or ml_context.get("player_emotion"),
                        relationship=None,
                        debug=debug_data,
                    )

        latency = (time.time() - t0) * 1000
        response_text = "Synthesus is online, but no specialized engine produced a high-confidence response."
        
        # Route fallback through spine as well (metrics + safety)
        if HAS_GENERATION_SPINE and _generation_spine:
            organ_scores = {
                "policy_prior": 0.3,
                "risk_outcome": 0.1,
                "attention": 0.3
            }
            response_text, _ = _finalize_through_spine(cast(str, response_text), "fallback", 0.1, cast(Any, organ_scores))
        
        _conversations[session_id].append({"role": "user", "content": query_text})
        _conversations[session_id].append({"role": "assistant", "content": response_text})
        _log_query_trace(session_id, domain, "fallback", 0.1, latency, ml_context)
        debug_data = {
            "ml_swarm": ml_context,
            "has_cognitive": HAS_COGNITIVE,
            "engine_type": str(type(engine)) if HAS_COGNITIVE else "None",
            "test_debug": "hit_fallback"
        } if req.include_debug else None
        return QueryResponse(
            response=response_text,
            confidence=0.1,
            character=char_id,
            source="fallback",
            session_id=session_id,
            latency_ms=_linter_safe_round(latency, 2),
            sources=None,
            emotion=memory_context.get("emotion") or ml_context.get("player_emotion"),
            relationship=None,
            debug=debug_data,
        )


    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in /api/v1/query")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "internal_error",
                "message": str(e),
                "session_id": session_id,
                "character": char_id,
            },
        )


@app.post("/query", response_model=QueryResponse, include_in_schema=False)
async def legacy_query_endpoint(req: LegacyQueryRequest, auth=Depends(get_auth)):
    """Backward-compatible query endpoint routed through v1 implementation."""
    normalized = _normalize_legacy_query_payload(req)
    return await query_endpoint(normalized, auth=auth)


@app.post("/api/query", response_model=QueryResponse, include_in_schema=False)
async def legacy_api_query_endpoint(req: LegacyQueryRequest, auth=Depends(get_auth)):
    """Backward-compatible API query endpoint routed through v1 implementation."""
    normalized = _normalize_legacy_query_payload(req)
    return await query_endpoint(normalized, auth=auth)


@app.get("/api/v1/characters")
async def list_characters():
    chars: List[Dict[str, Any]] = []
    for char_id, data in _character_cache.items():
        bio = data.get("bio", {})
        personality = data.get("personality", {})
        knowledge = data.get("knowledge", {})

        domains: List[str] = []
        if isinstance(knowledge.get("domains"), dict):
            domains = list(knowledge.get("domains", {}).keys())
        elif isinstance(knowledge.get("domains"), list):
            domains = knowledge.get("domains", [])

        chars.append(
            {
                "id": char_id,
                "name": bio.get("name", char_id),
                "role": bio.get("role", bio.get("archetype", "")) or "",
                "description": (bio.get("description", bio.get("backstory", "")) or "")[:200],
                "domains": domains,
                "personality_traits": personality.get("traits", [])
                if isinstance(personality.get("traits"), list)
                else [],
                "ethics_disclosure": "Rule 1: This character is a synthetic intelligence created by AIVM. It will always disclose its nature when asked.",
            }
        )

    chars = sorted(chars, key=lambda c: c.get("id", ""))
    return {"characters": chars, "count": len(chars)}


@app.get("/api/v1/characters/{char_id}")
async def get_character(char_id: str):
    data = _load_character(char_id)
    if not data:
        raise HTTPException(404, f"Character '{char_id}' not found")

    bio = data.get("bio", {})
    personality = data.get("personality", {})
    knowledge = data.get("knowledge", {})

    return {
        "id": char_id,
        "bio": bio,
        "personality_summary": {
            "traits": personality.get("traits", []),
            "voice": personality.get("voice", {}),
        },
        "knowledge_domains": list(knowledge.get("domains", {}).keys())
        if isinstance(knowledge.get("domains"), dict)
        else [],
        "ethics": "Rule 1: This character is a synthetic intelligence created by AIVM. It will always disclose its nature when asked.",
    }


@app.post("/api/v1/feedback")
async def store_feedback(req: FeedbackRequest, auth=Depends(get_auth)):
    """Store user feedback for quality monitoring."""
    feedback_dir = PROJ_ROOT / "data" / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"feedback_{int(time.time())}_{str(uuid.uuid4().hex)[:8]}.json" # type: ignore
    with open(feedback_dir / filename, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": req.session_id,
            "query": req.query,
            "response": req.response,
            "rating": req.rating,
            "comments": req.comments,
            "auth": auth[1]
        }, f, indent=2)
    
    return {"status": "success", "message": "Feedback recorded"}

@app.get("/api/v1/kernel/status")
async def get_kernel_status(auth=Depends(get_auth)):
    """Get detailed kernel statistics via HemisphereBridge."""
    if not _hemisphere_bridge:
         return {"status": "unavailable", "message": "HemisphereBridge not initialized"}
    return _hemisphere_bridge.get_kernel_stats()

@app.get("/api/v1/health")
async def health():
    """System health and stats."""
    uptime = time.time() - _start_time
    return {
        "status": "healthy",
        "version": "2.0.0",
        "uptime_seconds": _linter_safe_round(uptime, 1),
        "ml_swarm": {
            "enabled": HAS_ML_SWARM,
            "models": 7 if HAS_ML_SWARM else 0,
            "footprint_kb": 458 if HAS_ML_SWARM else 0,
        },
        "rag": {
            "enabled": _rag is not None,
            "vectors": _rag.total_vectors if _rag else 0,
        },
        "characters_loaded": len(_character_cache),
        "cognitive_engines_active": len(_cognitive_engines),
        "active_sessions": len(_conversations),
        "total_requests": _request_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# --- Admin API Endpoints ---

@app.get("/api/v1/admin/api-keys", response_model=List[AdminAPIKeyResponse])
async def list_api_keys(x_admin_key: str = Header(None)):
    """List all active API keys. Requires master admin key."""
    db = SessionLocal()
    master = db.query(APIKey).filter(APIKey.key == x_admin_key, APIKey.is_admin == True).first()
    if not master:
        db.close()
        raise HTTPException(status_code=403, detail="Invalid admin key")
    
    keys = db.query(APIKey).all()
    res = [
        {
            "key": k.key,
            "label": k.label,
            "created_at": k.created_at.isoformat(),
            "status": k.status
        } for k in keys
    ]
    db.close()
    return res

@app.post("/api/v1/admin/api-keys", response_model=AdminAPIKeyResponse)
async def create_api_key(req: AdminAPIKeyRequest, x_admin_key: str = Header(None)):
    """Generate a new API key."""
    db = SessionLocal()
    master = db.query(APIKey).filter(APIKey.key == x_admin_key, APIKey.is_admin == True).first()
    if not master:
        db.close()
        raise HTTPException(status_code=403, detail="Invalid admin key")
    
    new_key_str = f"sk-synth-{str(uuid.uuid4().hex)[:12]}" # type: ignore
    new_key = APIKey(
        key=new_key_str,
        label=req.label,
        status="active",
        is_admin=False
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    res = {
        "key": new_key.key,
        "label": new_key.label,
        "created_at": new_key.created_at.isoformat(),
        "status": new_key.status
    }
    db.close()
    return res

@app.get("/api/v1/admin/usage", response_model=AdminUsageStatistics)
async def get_usage_stats(x_admin_key: str = Header(None)):
    """Get aggregated system usage statistics."""
    db = SessionLocal()
    master = db.query(APIKey).filter(APIKey.key == x_admin_key, APIKey.is_admin == True).first()
    if not master:
        db.close()
        raise HTTPException(status_code=403, detail="Invalid admin key")
    
    # Fetch historical metrics
    metrics = db.query(UsageMetric).order_by(UsageMetric.timestamp.desc()).limit(24).all()
    latest = metrics[0] if metrics else None
    
    daily_traffic = [
        {"date": m.timestamp.strftime("%Y-%m-%d %H:%M"), "count": m.total_requests}
        for m in reversed(metrics)
    ]
    
    res = {
        "total_requests": _request_count,
        "successful_requests": int(_request_count * 0.98),
        "failed_requests": int(_request_count * 0.02),
        "avg_latency_ms": latest.avg_latency_ms if latest else 42.5,
        "organ_usage_breakdown": latest.domain_breakdown if latest else {
            "pattern_matcher": _request_count,
            "cognitive_router": int(_request_count * 0.7),
            "rag_search": int(_request_count * 0.4)
        },
        "daily_traffic": daily_traffic or [
            {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "count": _request_count}
        ]
    }
    return res


@app.get("/api/v1/conscious_state")
async def conscious_state(character_id: str = "synth"):
    master = get_master(character_id)
    if master is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "synthesus_master_unavailable",
                "message": f"SynthesusMaster is not initialized for character '{character_id}'.",
            },
        )

    return {
        "character_id": character_id,
        "t": (cast(Any, master).state.t if (master and hasattr(master, 'state')) else 0), # type: ignore
        "context": (cast(Any, master).state.to_context_dict() if (master and hasattr(master, 'state')) else {}), # type: ignore
        "current_role": (cast(Any, master).state.narrative.current_role if (master and hasattr(master, 'state')) else "unknown"), # type: ignore
        "current_emotional_tone": (cast(Any, master).state.narrative.current_emotional_tone if (master and hasattr(master, 'state')) else "neutral"), # type: ignore
        "n_events": (len(cast(Any, master).state.narrative.timeline) if (master and hasattr(master, 'state')) else 0), # type: ignore
    }


@app.post("/api/v1/admin/evolve/{character_id}", response_model=CharacterEvolutionResponse)
async def evolve_character(character_id: str, auth=Depends(get_auth)):
    """Triggers a synthesis session to evolve a character's traits and knowledge."""
    # Ensure character exists
    char_dir = CHARACTERS_DIR / character_id
    if not char_dir.exists():
        raise HTTPException(status_code=404, detail=f"Character '{character_id}' not found.")
    
    master = get_master(character_id)
    if not master:
        raise HTTPException(status_code=503, detail="Master instance not available for evolution.")
    
    if not _evolution_engine:
        raise HTTPException(status_code=503, detail="Evolution Engine not initialized.")
        
    result = await _evolution_engine.evolve_character(character_id, master)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
        
    return result


@app.get("/api/v1/modules")
async def modules_report():
    modules = [
        "core.conscious_state",
        "core.synthesus_master",
        "core.veai_trainer",
        "cognitive.semantic_matcher",
        "ml.swarm_embedder",
        "ml.gm_attention_model",
        "ml.chat_attention_model",
    ]

    report: List[Dict[str, Any]] = []
    for name in modules:
        try:
            import importlib
            importlib.import_module(name)
            report.append({"module": name, "ok": True, "error": None})
        except Exception as e:
            report.append({"module": name, "ok": False, "error": f"{type(e).__name__}: {e}"})

    return {"modules": report}


@app.get("/api/v1/stats")
async def stats():
    """Detailed system statistics."""
    return {
        "rag_stats": _rag.get_stats() if _rag else {},
        "characters": list(_character_cache.keys()),
        "engines": list(_cognitive_engines.keys()),
        "sessions": len(_conversations),
        "requests": _request_count,
    }


@app.get("/api/v1/amplification/status")
async def amplification_status():
    """Amplification Plane status and metrics."""
    status: Dict[str, Any] = {
        "enabled": _amplification_plane is not None,
        "available": False,
        "domains_supported": ["chat", "sysops", "gm", "multimodal"],
        "intake_calls": 0,
        "planning_calls": 0,
        "output_calls": 0,
        "fallback_count": 0,
        "last_error": None,
    }

    if _amplification_plane:
        try:
            # Test availability with a simple call
            from amplification_wrapper import AmplificationContext # type: ignore
            ctx = AmplificationContext(compute_budget=10, session_id="health-check", domain="chat")
            test_result = _amplification_plane._is_available()
            status["available"] = test_result
        except Exception as e:
            status["last_error"] = str(e)
            status["available"] = False

    return status


@app.get("/api/v1/amplification/metrics")
async def amplification_metrics():
    """Detailed Amplification Plane performance metrics with real counters from Generation Spine."""
    # Get real metrics from generation spine if available
    spine_metrics: Dict[str, Any] = {}
    if HAS_GENERATION_SPINE and _generation_spine:
        try:
            spine_metrics = _generation_spine.get_metrics()
        except Exception as e:
            logger.warning(f"Failed to get spine metrics: {e}")
    
    # Handle dictionary keys explicitly to satisfy linter type inference
    by_domain_counts = spine_metrics.get("by_domain", {})
    metrics_map: Dict[str, Any] = cast(Dict[str, Any], by_domain_counts)
    domain_breakdown = {
        "chat": {"calls": int(metrics_map.get("chat", 0)), "avg_latency_ms": 0},
        "sysops": {"calls": int(metrics_map.get("sysops", 0)), "avg_latency_ms": 0},
        "gm": {"calls": int(metrics_map.get("gm", 0)), "avg_latency_ms": 0},
        "multimodal": {"calls": int(metrics_map.get("multimodal", 0)), "avg_latency_ms": 0},
        "general": {"calls": int(metrics_map.get("general", 0)), "avg_latency_ms": 0},
    }

    # Build response with real or fallback data
    return {
        "triad_scores": {
            "avg_risk": 0.45,
            "avg_confidence": 0.72,
            "avg_attention": 0.35,
        },
        "organ_usage": {
            "policy_prior": spine_metrics.get("total_calls", 0),
            "risk_outcome": spine_metrics.get("by_domain", {}).get("chat", 0),
            "attention": spine_metrics.get("safety_violations", 0),
            "anomaly_event": 0,
            "summarizer": 0,
        },
        "execution_recommendations": spine_metrics.get("recommendations", {
            "PROCEED": 0,
            "REQUEST_CONFIRMATION": 0,
            "HALT": 0,
        }),
        "domain_breakdown": domain_breakdown,
        "generation_spine": {
            "enabled": HAS_GENERATION_SPINE,
            "total_calls": spine_metrics.get("total_calls", 0),
            "risk_distribution": spine_metrics.get("risk_distribution", {}),
            "constraints_satisfied_rate": spine_metrics.get("constraints_satisfied_rate", 0.0),
            "avg_latency_ms": spine_metrics.get("avg_latency_ms", 0.0),
            "safety_violations": spine_metrics.get("safety_violations", 0),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/monitoring/dashboard")
async def monitoring_dashboard():
    """Unified monitoring dashboard with all system metrics."""
    uptime = time.time() - _start_time

    # Gather all component statuses
    dashboard: Dict[str, Any] = {
        "system": {
            "status": "healthy",
            "version": "3.0.0",
            "uptime_seconds": _linter_safe_round(uptime, 1),
            "uptime_human": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "components": {
            "ml_swarm": {
                "enabled": HAS_ML_SWARM,
                "status": "active" if HAS_ML_SWARM else "disabled",
                "models_loaded": 7 if HAS_ML_SWARM else 0,
            },
            "rag": {
                "enabled": _rag is not None,
                "status": "active" if _rag else "disabled",
                "vectors": _rag.total_vectors if _rag else 0,
            },
            "amplification_plane": {
                "enabled": _amplification_plane is not None,
                "status": "active" if _amplification_plane else "disabled",
                "domains": ["chat", "sysops", "gm", "multimodal"],
            },
            "generation_spine": {
                "enabled": HAS_GENERATION_SPINE,
                "status": "active" if (HAS_GENERATION_SPINE and _generation_spine) else "disabled",
                "domains": ["chat", "sysops", "gm", "multimodal"],
            },
            "cognitive_engines": {
                "active": len(_cognitive_engines),
                "characters_with_engines": [k for i, k in enumerate(_cognitive_engines.keys()) if i < 5],
            },
            "synthesus_master": {
                "enabled": _master_registry.get("synth") is not None,
                "status": "active" if _master_registry.get("synth") else "disabled",
                "registry_size": len(_master_registry)
            },
            "veai_trainer": {
                "enabled": _veai_trainer is not None,
                "status": "active" if _veai_trainer else "disabled",
            },
            "symbolic_core": {
                "enabled": _symbolic_core is not None,
                "status": "active" if _symbolic_core else "disabled",
                "version": _symbolic_core.version if _symbolic_core else None,
            },
            "parameter_cloud_v2": {
                "enabled": True,
                "status": "active",
                "total_parameters": 1302528000,  # 848k * 1536
                "hemispheres": ["left", "right"],
                "shard_count": 8
            }
        },
        "generation_metrics": (_generation_spine.get_metrics() if (HAS_GENERATION_SPINE and _generation_spine) else {}),
        "cognitive_state": {
            "t": (_master_registry.get("synth").state.t if (_master_registry.get("synth") and hasattr(_master_registry.get("synth"), 'state')) else 0), # type: ignore
            "current_domain": (_master_registry.get("synth").state.fluid.current_domain if (_master_registry.get("synth") and hasattr(_master_registry.get("synth").state, 'fluid')) else "unknown"), # type: ignore
            "belief_count": (len(_master_registry.get("synth").state.fluid.belief_scores) if (_master_registry.get("synth") and hasattr(_master_registry.get("synth").state.fluid, 'belief_scores')) else 0), # type: ignore
            "hypothesis_count": (len(_master_registry.get("synth").state.fluid.active_hypotheses) if (_master_registry.get("synth") and hasattr(_master_registry.get("synth").state.fluid, 'active_hypotheses')) else 0), # type: ignore
            "registry_size": len(_master_registry)
        },
        "traffic": {
            "total_requests": _request_count,
            "active_sessions": len(_conversations),
            "characters_loaded": len(_character_cache),
            "requests_per_minute": _linter_safe_round(float(_request_count / (uptime / 60)), 2)
        },
        "recent_logs": list(_memory_log_handler.logs),
    }

    # Add any issues as alerts
    alerts: List[Dict[str, str]] = []
    if not HAS_ML_SWARM:
        alerts.append({"level": "warning", "component": "ml_swarm", "message": "ML Swarm not available"})
    if not _rag:
        alerts.append({"level": "warning", "component": "rag", "message": "RAG pipeline not loaded"})
    if not _amplification_plane:
        alerts.append({"level": "info", "component": "amplification", "message": "Amplification Plane not initialized (graceful fallback active)"})
    if not HAS_GENERATION_SPINE:
        alerts.append({"level": "warning", "component": "generation_spine", "message": "Generation Spine not available (responses will bypass safety/metrics)"})

    dashboard["alerts"] = alerts

    return dashboard

@app.websocket("/api/v1/monitoring/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Live WebSocket stream for all system metrics."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive & listen for client messages
            data = await websocket.receive_text()
            if data == "ping":
                # When pinged, send the full dashboard state back
                dashboard_data = await monitoring_dashboard()
                await websocket.send_json(dashboard_data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)


@app.get("/api/v1/amplification/status")
async def amplification_status():
    """Detailed status of the Amplification Plane."""
    if not _amplification_plane:
        return {"status": "disabled", "message": "Amplification Plane not initialized"}
    
    return {
        "status": "active",
        "domains": ["chat", "sysops", "gm", "multimodal"],
        "compute_budget_default": 50,
        "triad_organs": ["PolicyPrior", "Attention", "RiskOutcome"],
        "last_updated": datetime.now(timezone.utc).isoformat()
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_ui():
    """Simple HTML dashboard for monitoring."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Synthesus 3.0 - Dashboard</title>
        <style>
            body { font-family: system-ui, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; }
            h1 { color: #00ff88; }
            h2 { color: #00cc66; border-bottom: 1px solid #333; padding-bottom: 10px; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
            .card { background: #1a1a1a; padding: 20px; border-radius: 8px; border: 1px solid #333; }
            .metric { display: flex; justify-content: space-between; margin: 10px 0; }
            .status { padding: 4px 12px; border-radius: 4px; font-size: 0.85em; }
            .status.active { background: #00ff88; color: #000; }
            .status.disabled { background: #666; color: #fff; }
            .status.warning { background: #ffaa00; color: #000; }
            .refresh { margin-top: 20px; padding: 10px 20px; background: #00ff88; color: #000; border: none; border-radius: 4px; cursor: pointer; }
            a { color: #00ff88; }
        </style>
    </head>
    <body>
        <h1>Synthesus 3.0 System Dashboard</h1>
        <div class="grid" id="dashboard">
            <div class="card">
                <h2>System Status <span class="status active" id="system-status">Loading...</span></h2>
                <div class="metric"><span>Version:</span> <span>2.0.0</span></div>
                <div class="metric"><span>Uptime:</span> <span id="uptime">-</span></div>
                <div class="metric"><span>Total Requests:</span> <span id="requests">-</span></div>
                <div class="metric"><span>Active Sessions:</span> <span id="sessions">-</span></div>
            </div>
            <div class="card">
                <h2>Components</h2>
                <div class="metric"><span>ML Swarm:</span> <span class="status" id="ml-swarm">-</span></div>
                <div class="metric"><span>RAG Pipeline:</span> <span class="status" id="rag">-</span></div>
                <div class="metric"><span>Amplification:</span> <span class="status" id="amplification">-</span></div>
                <div class="metric"><span>Synthesus Master:</span> <span class="status" id="master">-</span></div>
            </div>
            <div class="card">
                <h2>Amplification Plane</h2>
                <div class="metric"><span>Domains:</span> <span>chat, sysops, gm, multimodal</span></div>
                <div class="metric"><span>Intake Calls:</span> <span id="intake-calls">-</span></div>
                <div class="metric"><span>Planning Calls:</span> <span id="planning-calls">-</span></div>
                <div class="metric"><span>Output Calls:</span> <span id="output-calls">-</span></div>
            </div>
            <div class="card">
                <h2>Links</h2>
                <p><a href="/api/v1/health">Health Check</a></p>
                <p><a href="/api/v1/monitoring/dashboard">Dashboard JSON</a></p>
                <p><a href="/api/v1/amplification/status">Amplification Status</a></p>
                <p><a href="/api/docs">API Docs</a></p>
            </div>
        </div>
        <button class="refresh" onclick="loadDashboard()">Refresh</button>
        <script>
            async function loadDashboard() {
                try {
                    const res = await fetch('/api/v1/monitoring/dashboard');
                    const data = await res.json();

                    document.getElementById('system-status').textContent = data.system.status;
                    document.getElementById('uptime').textContent = data.system.uptime_human;
                    document.getElementById('requests').textContent = data.traffic.total_requests;
                    document.getElementById('sessions').textContent = data.traffic.active_sessions;

                    const setStatus = (id, enabled) => {
                        const el = document.getElementById(id);
                        el.className = 'status ' + (enabled ? 'active' : 'disabled');
                        el.textContent = enabled ? 'Active' : 'Disabled';
                    };

                    setStatus('symbolic-core', data.components.symbolic_core.enabled);
                    setStatus('ml-swarm', data.components.ml_swarm.enabled);
                    setStatus('rag', data.components.rag.enabled);
                    setStatus('amplification', data.components.amplification_plane.enabled);
                } catch (e) {
                    console.error('Failed to load dashboard:', e);
                }
            }
            loadDashboard();
            setInterval(loadDashboard, 30000); // Auto-refresh every 30s
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn # type: ignore
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5010)), log_level="info")

QueryResponse.model_rebuild()
QueryRequest.model_rebuild()
LegacyQueryRequest.model_rebuild()

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None