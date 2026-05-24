# Synthesus 2.0 - FastAPI Server
# Full REST + SSE streaming server for the ZO kernel
from __future__ import annotations
import asyncio
import subprocess
import json
import os
import glob as _glob
from pathlib import Path
from typing import AsyncIterator, Optional, Dict, List, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
try:
    from sse_starlette.sse import EventSourceResponse
    _HAS_SSE = True
except ImportError:
    _HAS_SSE = False
    EventSourceResponse = None

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cognitive.cognitive_engine import CognitiveEngine
from core.knowledge_cloud import KnowledgeCloud
from core.universal_substrate import UniversalSubstrate

# Knowledge Router setup
try:
    from knowledge_router import get_knowledge_router, KnowledgeSource
    _knowledge_router = get_knowledge_router(
        enable_wikipedia=True,
        enable_web_search=True,
        enable_distillation=True,
    )
    print("[knowledge] Hybrid Knowledge Router initialized with distillation")
except Exception as _e:
    print(f"[knowledge] Router init failed: {_e}")
    _knowledge_router = None

# V4: KAL setup
try:
    from kal.config import load_kal_config, build_kal_service
    _kal_config = load_kal_config()
    _kal_client = None
    if _kal_config.enabled:
        try:
            _kal_service, _kal_client = build_kal_service(_kal_config)
        except Exception as _e:
            print(f"[kal] Init failed, running without KAL: {_e}")
except ImportError:
    _kal_client = None

from fastapi import Depends, Header
from collections import defaultdict
import time
import uuid

DEMO_RATE_LIMIT = 10
AUTH_RATE_LIMIT = 60

app = FastAPI(title="Synthesus 2.0", version="2.0.0")

# Admin key (mandatory via environment for safety)
ADMIN_KEY = os.environ.get("SYNTHESUS_API_KEY")

# Configure allowed origins from environment or default to local development
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJ_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SYNTHESUS_DATA_DIR", str(PROJ_ROOT / "data")))
KERNEL_BIN = os.path.join(os.path.dirname(__file__), "..", "zo_kernel")
CHARACTERS_DIR = os.path.join(os.path.dirname(__file__), "..", "characters")
_kernel_proc: Optional[subprocess.Popen] = None
_character_cache: Dict[str, Dict[str, Any]] = {}
_cognitive_engines: Dict[str, CognitiveEngine] = {}
MAX_ENGINES = 50
_rate_limits: Dict[str, List[float]] = defaultdict(list)
_rate_limit_lock = asyncio.Lock()
_knowledge_cloud: Optional[KnowledgeCloud] = None
_substrate: Optional[UniversalSubstrate] = None


def _get_shared_layers() -> tuple[Optional[KnowledgeCloud], Optional[UniversalSubstrate]]:
    global _knowledge_cloud, _substrate
    if _knowledge_cloud is None:
        try:
            _knowledge_cloud = KnowledgeCloud(data_dir=str(DATA_DIR / "knowledge_cloud"))
        except Exception as e:
            print(f"[knowledge] Shared knowledge cloud unavailable: {e}")
            _knowledge_cloud = None
    if _substrate is None:
        try:
            _substrate = UniversalSubstrate(
                local_data_dir=str(DATA_DIR),
                local_char_dir=CHARACTERS_DIR,
                knowledge_cloud_dir=str(DATA_DIR / "knowledge_cloud"),
                endpoint=os.environ.get("SYNTHESUS_PARAMETER_CLOUD_URL", "http://localhost:8000/parameter-cloud/v2"),
            )
        except Exception as e:
            print(f"[substrate] Shared parameter substrate unavailable: {e}")
            _substrate = None
    return _knowledge_cloud, _substrate

async def get_auth(request: Request, x_api_key: Optional[str] = Header(None)):
    if x_api_key and x_api_key == ADMIN_KEY:
        return True, f"auth:{x_api_key[:8]}"
    client_ip = request.client.host if request.client else "unknown"
    return False, f"ip:{client_ip}"

async def _check_rate_limit(key: str, limit: int) -> bool:
    async with _rate_limit_lock:
        now = time.time()
        window = [t for t in _rate_limits[key] if now - t < 60]
        _rate_limits[key] = window
        if len(window) >= limit:
            return False
        _rate_limits[key].append(now)
        return True


def _load_character(char_id: str) -> Optional[Dict[str, Any]]:
    """Load a character's bio + patterns from disk (cached)."""
    if char_id in _character_cache:
        return _character_cache[char_id]
    char_dir = os.path.join(CHARACTERS_DIR, char_id)
    bio_path = os.path.join(char_dir, "bio.json")
    pat_path = os.path.join(char_dir, "patterns.json")
    if not os.path.isdir(char_dir) or not os.path.exists(bio_path):
        return None
    with open(bio_path) as f:
        bio = json.load(f)
    patterns = {}
    if os.path.exists(pat_path):
        with open(pat_path) as f:
            patterns = json.load(f)
    _character_cache[char_id] = {"bio": bio, "patterns": patterns}
    return _character_cache[char_id]


def _get_cognitive_engine(char_id: str) -> Optional[CognitiveEngine]:
    """Get or create a CognitiveEngine for a character with size-limited cache."""
    if char_id in _cognitive_engines:
        # LRU: Move to end
        engine = _cognitive_engines.pop(char_id)
        _cognitive_engines[char_id] = engine
        return engine
    
    # Evict if limit reached
    if len(_cognitive_engines) >= MAX_ENGINES:
        oldest_id = next(iter(_cognitive_engines))
        print(f"[cognitive] Evicting engine for character: {oldest_id}")
        del _cognitive_engines[oldest_id]

    char_data = _load_character(char_id)
    if char_data is None:
        return None
    try:
        char_dir = os.path.join(CHARACTERS_DIR, char_id)
        knowledge_cloud, substrate = _get_shared_layers()
        engine = CognitiveEngine(
            character_id=char_id,
            bio=char_data["bio"],
            patterns=char_data["patterns"],
            char_dir=char_dir,
            kal_client=_kal_client,
            substrate=substrate,
            knowledge_cloud=knowledge_cloud,
            persist_dir=str(DATA_DIR / "characters" / char_id),
        )
        _cognitive_engines[char_id] = engine
        return engine
    except Exception as e:
        print(f"[cognitive] Failed to create engine for {char_id}: {e}")
        return None


def _match_pattern(query_text: str, patterns_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Match a query against a character's synthetic + generic patterns.

    Scoring strategy (v3 — strict topic matching):
    1. Exact trigger match → immediate return (conf 1.0)
    2. Near-exact: query contains the full trigger as substring → high score
    3. Token overlap with STRICT requirements:
       - Must have >= 2 overlapping content words (unless trigger has only 1)
       - Score uses geometric mean of trigger-coverage and query-coverage
       - Single-word overlap on a long query scores very low
    Generic patterns are penalised so domain patterns win on ties.
    """
    import re as _re
    q = query_text.strip().lower()

    # Broad stop-word list to isolate content words
    _stop = {
        "the","a","an","is","it","of","in","to","and","or","i","me","my",
        "you","your","do","does","did","can","could","would","should",
        "what","how","why","when","where","who","that","this","if",
        "about","for","with","on","at","by","from","up","out","so",
        "be","been","am","are","was","were","have","has","had","not",
        "but","just","more","very","ever","one","thing","like","any",
        "some","no","all","them","they","we","he","she","it's","i'm",
        "don't","there","i'll","got","get","know","think","tell",
        "really","much","way","too","also","here","now","then",
        "something","anything","everything","nothing","someone",
        "going","want","need","make","let","go","come","see",
        "take","give","say","said","look","well","back","even",
        "still","us","our","his","her","its","their","him",
        "being","been","into","over","after","before","between",
        "through","only","other","than","such","will","shall"
    }

    def _tokenize(text: str) -> set:
        return set(_re.findall(r'[a-z]+', text)) - _stop

    q_tokens = _tokenize(q)

    synthetic = patterns_data.get("synthetic_patterns", [])
    generic = patterns_data.get("generic_patterns", [])

    best_match = None
    best_score = 0.0

    for pat_list, is_generic in [(synthetic, False), (generic, True)]:
        for pat in pat_list:
            triggers = pat.get("trigger", [])
            if isinstance(triggers, str):
                triggers = [triggers]
            conf = pat.get("confidence", 0.5)

            for t in triggers:
                t_lower = t.lower().strip()
                t_tokens = _tokenize(t_lower)

                # ── Exact match → instant winner ──
                if t_lower == q:
                    return pat, 1.0

                score = 0.0
                overlap = q_tokens & t_tokens
                n_overlap = len(overlap)

                # ── Full-trigger substring containment ──
                # The entire trigger phrase appears inside the query
                if t_lower in q and len(t_lower) >= 4:
                    specificity = len(t_lower) / max(len(q), 1)
                    score = conf * (0.7 + 0.3 * specificity)

                # ── Token overlap scoring ──
                elif t_tokens and q_tokens:
                    # Require minimum overlap:
                    #  - 1 word if trigger OR query has <= 2 content tokens
                    #  - 2 words otherwise (prevents stray single-word matches on long queries)
                    min_required = 1 if (len(t_tokens) <= 2 or len(q_tokens) <= 2) else 2
                    if n_overlap >= min_required:
                        trigger_cov = n_overlap / len(t_tokens)
                        query_cov = n_overlap / len(q_tokens)
                        # Geometric mean — punishes cases where one side is tiny
                        geo_mean = (trigger_cov * query_cov) ** 0.5
                        score = geo_mean * conf

                # ── Penalise generic patterns ──
                if is_generic:
                    score *= 0.7

                if score > best_score:
                    best_score = score
                    best_match = pat

    return best_match, best_score


# Minimum match quality to accept a pattern (below this → character fallback)
MATCH_QUALITY_THRESHOLD = 0.55


def _character_fallback(query_text: str, char_id: str) -> Dict[str, Any]:
    """Process a query through character pattern matching (Python fallback)."""
    char_data = _load_character(char_id)
    if char_data is None:
        return {
            "response": f"Character '{char_id}' not found.",
            "confidence": 0.0, "module": "character_router",
            "source": "fallback", "character": char_id
        }
    patterns_data = char_data["patterns"]
    match, match_score = _match_pattern(query_text, patterns_data)
    if match and match_score >= MATCH_QUALITY_THRESHOLD:
        return {
            "response": match["response_template"],
            "confidence": round(match_score, 4),
            "module": f"ppbrs_character_{char_id}",
            "source": "character_pattern",
            "character": char_id,
            "pattern_id": match.get("id", "unknown")
        }
    # Character fallback string
    fallback_text = patterns_data.get(
        "fallback",
        f"I am {char_data['bio'].get('name', char_id)}. Could you rephrase your question?"
    )
    return {
        "response": fallback_text,
        "confidence": 0.3, "module": f"ppbrs_character_{char_id}",
        "source": "character_fallback", "character": char_id
    }


def get_kernel():
    global _kernel_proc
    if _kernel_proc is None or _kernel_proc.poll() is not None:
        if os.path.exists(KERNEL_BIN) and os.access(KERNEL_BIN, os.X_OK):
            try:
                _kernel_proc = subprocess.Popen(
                    [KERNEL_BIN], stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1
                )
            except (PermissionError, OSError) as e:
                print(f"[kernel] Unavailable: {e}")
                _kernel_proc = None
        else:
            _kernel_proc = None
    return _kernel_proc

class QueryRequest(BaseModel):
    query: str = ""
    q: str = ""
    text: str = ""
    stream: bool = False
    context: str = ""
    mode: str = "left"       # "left" | "cognitive" | "auto"
    character: str = ""
    player_id: str = "default"  # For cognitive engine multi-turn tracking
    explain: bool = False    # Return reasoning explanation alongside answer

class QueryResponse(BaseModel):
    response: str
    confidence: float
    module: str
    source: str = "kernel"
    character: str = ""
    pattern_id: str = ""
    emotion: str = ""
    relationship: Dict = {}
    debug: Dict = {}
    explanation: Optional[str] = None  # Reasoning trace in natural language


QueryRequest.model_rebuild()
QueryResponse.model_rebuild()

@app.get("/", response_class=HTMLResponse)
async def root():
    static_path = os.path.join(os.path.dirname(__file__), "..", "static", "dashboard.html")
    if os.path.exists(static_path):
        with open(static_path) as f:
            return f.read()
    return "<h1>Synthesus 2.0</h1><p>Dashboard not found.</p>"

@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, auth=Depends(get_auth)):
    # Rate limiting
    is_auth, rate_key = auth
    limit = AUTH_RATE_LIMIT if is_auth else DEMO_RATE_LIMIT
    if not await _check_rate_limit(rate_key, limit):
        raise HTTPException(429, "Rate limit exceeded.")

    # Resolve the actual query text (support text, query, or q fields)
    query_text = (req.text or req.query or req.q or "").strip()
    if not query_text:
        raise HTTPException(400, "Query must not be empty")

    # Explicit character mode uses the character fallback path.
    char_id = (req.character or "synth").strip().lower()
    if req.mode == "character" and char_id:
        result = _character_fallback(query_text, char_id)
        return QueryResponse(**result)

    # ── Cognitive Engine mode ──
    if req.mode in ("cognitive", "auto") and char_id:
        engine = _get_cognitive_engine(char_id)
        if engine:
            result = await engine.process_query(
                player_id=req.player_id,
                query=query_text,
                thinking_layer_available=False,
            )
            
            # Generate reasoning explanation if requested
            explanation = None
            if req.explain:
                try:
                    from core.conversational_narrator import get_narrator, ReasoningStep
                    from datetime import datetime
                    
                    narrator = get_narrator(persona="friendly" if char_id == "synth" else "analytical")
                    
                    # Build reasoning trace from debug info
                    reasoning_trace = []
                    debug = result.get("debug", {})
                    
                    # Add pattern matching step
                    if debug.get("pattern_matched"):
                        reasoning_trace.append(ReasoningStep(
                            hemisphere="MC",
                            action="pattern_match",
                            input_data={"query": query_text},
                            output_data={"pattern": debug.get("pattern_matched"), "confidence": debug.get("pattern_confidence", 0.5)},
                            confidence=debug.get("pattern_confidence", 0.5),
                            timestamp=datetime.now()
                        ))
                    
                    # Query knowledge router for factual grounding
                    knowledge_info = None
                    if _knowledge_router:
                        try:
                            knowledge_result = await _knowledge_router.query(
                                query=query_text,
                                merge_results=True,
                                top_k=2,
                            )
                            if knowledge_result.confidence > 0.3:
                                knowledge_info = {
                                    "routing": knowledge_result.metadata.get("routing_decision", ""),
                                    "primary_source": knowledge_result.source.value,
                                    "sources": knowledge_result.sources,
                                    "confidence": knowledge_result.confidence,
                                    "content_preview": knowledge_result.content[:200] if knowledge_result.content else "",
                                }
                                
                                # Add knowledge retrieval step
                                reasoning_trace.append(ReasoningStep(
                                    hemisphere="Knowledge",
                                    action="hybrid_retrieve",
                                    input_data={"query": query_text},
                                    output_data={
                                        "source": knowledge_result.source.value,
                                        "confidence": knowledge_result.confidence,
                                        "routing": knowledge_info["routing"],
                                    },
                                    confidence=knowledge_result.confidence,
                                    timestamp=datetime.now()
                                ))
                        except Exception as ke:
                            print(f"Knowledge router query error: {ke}")
                    
                    # Add knowledge retrieval step if sources exist
                    sources = debug.get("sources", [])
                    if sources and not knowledge_info:
                        reasoning_trace.append(ReasoningStep(
                            hemisphere="Knowledge",
                            action="retrieve",
                            input_data={"query": query_text},
                            output_data={"results_count": len(sources)},
                            confidence=result["confidence"],
                            timestamp=datetime.now()
                        ))
                    
                    # Generate base reasoning explanation
                    base_explanation = narrator.narrate_reasoning(
                        query=query_text,
                        reasoning_trace=reasoning_trace,
                        final_answer=result["response"] or "[ESCALATED]",
                        sources=sources if sources else None,
                        overall_confidence=result["confidence"]
                    )
                    
                    # Add knowledge routing explanation if available
                    if knowledge_info:
                        knowledge_narrative = narrator.narrate_knowledge_routing(
                            query=query_text,
                            routing_decision=knowledge_info["routing"],
                            primary_source=knowledge_info["primary_source"],
                            sources_consulted=knowledge_info["sources"],
                            confidence=knowledge_info["confidence"],
                        )
                        
                        # Combine explanations
                        explanation = f"{knowledge_narrative}\n\n{base_explanation}"
                    else:
                        explanation = base_explanation
                        
                except Exception as e:
                    print(f"Explanation generation error: {e}")
                    explanation = None
            
            return QueryResponse(
                response=result["response"] or "[ESCALATED]",
                confidence=result["confidence"],
                module=f"cognitive_engine_{char_id}",
                source=result["source"],
                character=char_id,
                pattern_id=result["debug"].get("pattern_matched", "") or "",
                emotion=result.get("emotion", ""),
                relationship=result.get("relationship", {}),
                debug=result.get("debug", {}),
                explanation=explanation,
            )

    kernel = get_kernel()
    if kernel is None:
        # Python fallback
        if char_id:
            result = _character_fallback(query_text, char_id)
            return QueryResponse(**result)
        return QueryResponse(
            response=f"[FALLBACK] Processed: {query_text}",
            confidence=0.5, module="python_fallback", source="fallback"
        )
    try:
        kernel.stdin.write(query_text + "\n")
        kernel.stdin.flush()
        line = kernel.stdout.readline()
        if not line:
            # Kernel crashed or closed pipe
            global _kernel_proc
            _kernel_proc = None # Force restart on next call
            return QueryResponse(
                response="Neural link interrupted. Re-initializing...",
                confidence=0.0, module="kernel", source="error"
            )
        data = json.loads(line.strip())
        return QueryResponse(
            response=data.get("r", data.get("response", "")),
            confidence=data.get("c", data.get("confidence", 0.0)),
            module=data.get("m", data.get("module", "pattern_kernel")),
            source="kernel",
            character=char_id
        )
    except (BrokenPipeError, IOError, Exception) as e:
        print(f"[kernel] Runtime error: {e}")
        _kernel_proc = None
        return QueryResponse(
            response="Neural link interrupted. Please retry.",
            confidence=0.0, module="kernel", source="error"
        )

@app.get("/health")
async def health():
    kernel = get_kernel()
    return {"status": "ok", "kernel": kernel is not None and kernel.poll() is None, "knowledge_cloud": _get_shared_layers()[0] is not None, "parameter_cloud": _get_shared_layers()[1] is not None}

@app.get("/stream")
async def stream(q: str):
    async def generator() -> AsyncIterator[dict]:
        kernel = get_kernel()
        if kernel:
            kernel.stdin.write(q + "\n")
            kernel.stdin.flush()
            line = kernel.stdout.readline().strip()
            yield {"data": line}
        else:
            yield {"data": json.dumps({"r": f"[FALLBACK] {q}", "c": 0.5, "m": "fallback"})}
    return EventSourceResponse(generator())



@app.get("/characters")
async def characters():
    import glob, json as _json
    chars = []
    for p in glob.glob("characters/*/bio.json") + glob.glob("synth/*/bio.json"):
        try:
            with open(p) as fh: d = _json.load(fh)
            chars.append({"id": d.get("id",""), "name": d.get("name","")})
        except: pass
    return {"characters": chars}

@app.post("/process", response_model=QueryResponse)
async def process(req: QueryRequest):
    return await query(req)


@app.post("/world_state")
async def set_world_state(flags: Dict[str, Any]):
    """Set world state flags for all cognitive engines."""
    from cognitive.world_state_reactor import WorldStateReactor
    for key, value in flags.items():
        if value is None:
            WorldStateReactor.clear_flag(key)
        else:
            WorldStateReactor.set_flag(key, value, set_by="api")
    return {"status": "ok", "active_flags": WorldStateReactor.get_all_flags()}


@app.get("/world_state")
async def get_world_state():
    """Get current world state flags."""
    from cognitive.world_state_reactor import WorldStateReactor
    return {"flags": WorldStateReactor.get_all_flags()}

@app.get("/cognitive_stats")
async def cognitive_stats():
    """Get statistics from all active cognitive engines."""
    stats = {}
    for char_id, engine in _cognitive_engines.items():
        stats[char_id] = engine.get_stats()
    return {"engines": stats}


@app.post("/knowledge/query")
async def knowledge_query(req: QueryRequest):
    """
    Query the Hybrid Knowledge Router for factual information.
    Routes to Wikipedia, Web Search, or Document Store based on query type.
    """
    if _knowledge_router is None:
        raise HTTPException(503, "Knowledge Router not available")
    
    query_text = (req.text or req.query or req.q or "").strip()
    if not query_text:
        raise HTTPException(400, "Query must not be empty")
    
    try:
        result = await _knowledge_router.query(
            query=query_text,
            merge_results=True,
            top_k=3,
        )
        
        return {
            "query": query_text,
            "content": result.content,
            "source": result.source.value,
            "confidence": result.confidence,
            "sources": result.sources,
            "routing": result.metadata.get("routing_decision", "Unknown"),
            "retrieval_time_ms": result.retrieval_time_ms,
        }
    except Exception as e:
        logger.error(f"Knowledge query error: {e}")
        raise HTTPException(500, f"Knowledge query failed: {str(e)}")


@app.get("/knowledge/sources")
async def knowledge_sources():
    """List available knowledge sources and their status."""
    sources = []
    if _knowledge_router:
        for source in _knowledge_router.sources.keys():
            sources.append({
                "id": source.value,
                "name": source.value.replace("_", " ").title(),
                "available": True,
            })
    
    return {
        "sources": sources,
        "router_available": _knowledge_router is not None,
    }


# ─────────────────────────────────────────────────────────────
# Distillation RAG API Endpoints
# ─────────────────────────────────────────────────────────────

try:
    from core.distillation_rag_source import get_distillation_source
    _distillation_source = get_distillation_source()
    _DISTILLATION_AVAILABLE = True
except Exception as _e:
    print(f"[distillation] Init failed: {_e}")
    _distillation_source = None
    _DISTILLATION_AVAILABLE = False


@app.post("/distillation/query")
async def distillation_query(req: QueryRequest):
    """
    Query using Distillation RAG with DistilBERT/DistilGPT-2.
    Provides RAG-augmented answers using lightweight distilled models.
    """
    if not _DISTILLATION_AVAILABLE:
        raise HTTPException(503, "Distillation RAG not available")
    
    query_text = (req.text or req.query or req.q or "").strip()
    if not query_text:
        raise HTTPException(400, "Query must not be empty")
    
    try:
        result = _distillation_source.query(
            query=query_text,
            use_rag=True,
            top_k=3,
        )
        
        return {
            "query": query_text,
            "answer": result.answer,
            "confidence": result.confidence,
            "model_used": result.model_used,
            "retrieval_method": result.retrieval_method,
            "sources": [
                {
                    "content": s.get("content", "")[:200],
                    "relevance_score": s.get("relevance_score", 0),
                    "metadata": s.get("metadata", {}),
                }
                for s in result.sources
            ],
            "latency_ms": result.latency_ms,
        }
    except Exception as e:
        logger.error(f"Distillation query error: {e}")
        raise HTTPException(500, f"Distillation query failed: {str(e)}")


@app.post("/distillation/documents")
async def distillation_add_documents(documents: List[Dict[str, Any]]):
    """
    Add documents to the distillation knowledge base.
    Documents will be used for RAG-augmented queries.
    """
    if not _DISTILLATION_AVAILABLE:
        raise HTTPException(503, "Distillation RAG not available")
    
    if not documents:
        raise HTTPException(400, "No documents provided")
    
    try:
        texts = [d.get("text", "") for d in documents]
        metadata_list = [d.get("metadata", {}) for d in documents]
        
        result = _distillation_source.add_documents(texts, metadata_list)
        
        return result
    except Exception as e:
        logger.error(f"Error adding documents: {e}")
        raise HTTPException(500, f"Failed to add documents: {str(e)}")


@app.get("/distillation/stats")
async def distillation_stats():
    """Get statistics about the distillation RAG system."""
    if not _DISTILLATION_AVAILABLE:
        return {"available": False, "error": "Distillation RAG not initialized"}
    
    return _distillation_source.get_stats()


# ─────────────────────────────────────────────────────────────
# Psi Transformer Attention API (Attention Visualization)
# ─────────────────────────────────────────────────────────────

try:
    from core.psi_transformer_attention import get_psi_transformer
    _psi_transformer = get_psi_transformer()
    _PSI_TRANSFORMER_AVAILABLE = True
except Exception as _e:
    print(f"[psi_transformer] Init failed: {_e}")
    _psi_transformer = None
    _PSI_TRANSFORMER_AVAILABLE = False


@app.post("/psi/analyze")
async def psi_analyze(req: QueryRequest):
    """
    Analyze query using Psi (Fluid) hemisphere transformer attention.
    Returns attention patterns, focus tokens, and pattern detection.
    """
    if not _PSI_TRANSFORMER_AVAILABLE:
        raise HTTPException(503, "Psi transformer not available")
    
    query_text = (req.text or req.query or req.q or "").strip()
    if not query_text:
        raise HTTPException(400, "Query must not be empty")
    
    try:
        # Convert query to tokens
        tokens = query_text.lower().split()
        token_ids = [hash(word) % 10000 for word in tokens]
        
        # Process through transformer
        analysis = _psi_transformer.process(
            text_tokens=token_ids,
            query_context=query_text,
        )
        
        return {
            "query": query_text,
            "token_count": len(tokens),
            "pattern_detected": analysis.pattern_detected,
            "confidence": analysis.confidence,
            "entropy": analysis.entropy,
            "novelty_score": analysis.novelty_score,
            "uncertainty": analysis.uncertainty,
            "focus_tokens_preview": analysis.focus_tokens[:5],
            "hypotheses": analysis.active_hypotheses,
            "attention_layers": len(analysis.attention_maps),
        }
    except Exception as e:
        logger.error(f"Psi analysis error: {e}")
        raise HTTPException(500, f"Psi analysis failed: {str(e)}")


@app.post("/psi/attention-visualization")
async def psi_attention_viz(req: QueryRequest):
    """
    Get attention weights for visualization.
    Returns attention matrix that can be rendered as heatmap.
    """
    if not _PSI_TRANSFORMER_AVAILABLE:
        raise HTTPException(503, "Psi transformer not available")
    
    query_text = (req.text or req.query or req.q or "").strip()
    if not query_text:
        raise HTTPException(400, "Query must not be empty")
    
    try:
        # Process query
        tokens = query_text.lower().split()
        token_ids = [hash(word) % 10000 for word in tokens]
        
        analysis = _psi_transformer.process(
            text_tokens=token_ids,
            query_context=query_text,
        )
        
        # Extract attention from last layer
        if not analysis.attention_maps:
            return {"error": "No attention maps available"}
        
        last_attention = analysis.attention_maps[-1]
        # Average across heads
        avg_attention = np.mean(last_attention[0], axis=0)
        
        return {
            "query": query_text,
            "tokens": tokens,
            "attention_matrix": avg_attention.tolist(),
            "shape": avg_attention.shape,
            "max_attention": float(np.max(avg_attention)),
            "min_attention": float(np.min(avg_attention)),
            "mean_attention": float(np.mean(avg_attention)),
            "layer": -1,  # Last layer
        }
    except Exception as e:
        logger.error(f"Attention viz error: {e}")
        raise HTTPException(500, f"Failed to generate attention viz: {str(e)}")


@app.get("/psi/transformer-stats")
async def psi_transformer_stats():
    """Get statistics about the Psi transformer attention system."""
    if not _PSI_TRANSFORMER_AVAILABLE:
        return {"available": False, "error": "Psi transformer not initialized"}
    
    return {
        "available": True,
        "num_layers": _psi_transformer.num_layers,
        "d_model": _psi_transformer.d_model,
        "num_heads": _psi_transformer.num_heads,
        "total_parameters": _psi_transformer.total_parameters,
        "parameters_millions": round(_psi_transformer.total_parameters / 1e6, 2),
    }


# ─────────────────────────────────────────────────────────────
# Reasoning Trace API (A: Deep Traces, B: Streaming, C: Drill-down)
# ─────────────────────────────────────────────────────────────

try:
    from core.reasoning_tracer import get_tracer
    _tracer = get_tracer(enable_streaming=True)
    _TRACER_AVAILABLE = True
except Exception as e:
    print(f"[tracer] Init failed: {e}")
    _tracer = None
    _TRACER_AVAILABLE = False


@app.post("/query/stream-reasoning")
async def query_stream_reasoning(req: QueryRequest):
    """
    Query with real-time reasoning stream (B: Real-time streaming).
    Returns both final answer AND Server-Sent Events for reasoning trace.
    """
    if not _TRACER_AVAILABLE:
        raise HTTPException(503, "Reasoning tracer not available")
    
    query_text = (req.text or req.query or req.q or "").strip()
    if not query_text:
        raise HTTPException(400, "Query must not be empty")
    
    char_id = (req.character or "synth").strip().lower()
    
    # Start trace with streaming enabled
    trace_id = _tracer.start_trace(
        query=query_text,
        character_id=char_id,
        enable_streaming=True,
    )
    
    async def stream_generator() -> AsyncIterator[str]:
        """Stream reasoning events as they happen."""
        # Start streaming events
        stream_task = None
        
        try:
            # Create stream from tracer
            async for event in _tracer.stream_trace(trace_id):
                # Send event as SSE
                yield f"data: {json.dumps(event)}\n\n"
                
                # If execution complete, we're done
                if event.get("event_type") == "execution_complete":
                    break
                    
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        # Send final answer
        trace = _tracer.get_trace(trace_id)
        if trace:
            yield f"data: {json.dumps({
                'event_type': 'final_answer',
                'answer': trace.final_answer,
                'trace_id': trace_id,
                'overall_confidence': trace.overall_confidence,
            })}\n\n"
    
    # Run the actual query in background
    async def run_query():
        try:
            # Get master AI
            from core.quadbrain_master import QuadbrainMaster
            master = QuadbrainMaster()
            
            # Execute with streaming
            result = await master.think(
                query_text,
                character_id=char_id,
                stream_reasoning=True,
            )
            
            return result
        except Exception as e:
            logger.error(f"Streaming query error: {e}")
            # Still end the trace
            _tracer.end_trace(trace_id, f"Error: {str(e)}", 0.0)
    
    # Start background task
    asyncio.create_task(run_query())
    
    # Return streaming response
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Trace-ID": trace_id,
        },
    )


@app.get("/traces")
async def list_traces(character: Optional[str] = None, limit: int = 50):
    """List recent reasoning traces with summaries."""
    if not _TRACER_AVAILABLE:
        return {"traces": [], "tracer_available": False}
    
    traces = _tracer.list_traces(character_id=character, limit=limit)
    return {
        "traces": traces,
        "tracer_available": True,
        "total_stored": len(_tracer.traces),
    }


@app.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    """Get full reasoning trace by ID (A: Deep hemisphere traces)."""
    if not _TRACER_AVAILABLE:
        raise HTTPException(503, "Tracer not available")
    
    trace = _tracer.get_trace(trace_id)
    if not trace:
        # Check active traces
        trace = _tracer.get_active_trace(trace_id)
    
    if not trace:
        raise HTTPException(404, f"Trace {trace_id} not found")
    
    # Build detailed response
    events = []
    for event in trace.events:
        events.append({
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "hemisphere": event.hemisphere.value if event.hemisphere else None,
            "timestamp": event.timestamp,
            "data": event.data,
            "depth": event.depth,
            "parent_event_id": event.parent_event_id,
        })
    
    hemisphere_states = {}
    for hemisphere, states in trace.hemisphere_states.items():
        hemisphere_states[hemisphere.value] = [
            {
                "timestamp": s.timestamp,
                "confidence": s.confidence,
                "latency_ms": s.latency_ms,
                "metadata": s.metadata,
            }
            for s in states
        ]
    
    return {
        "trace_id": trace.trace_id,
        "query": trace.query,
        "character_id": trace.character_id,
        "start_time": trace.start_time,
        "end_time": trace.end_time,
        "duration_ms": (trace.end_time - trace.start_time) * 1000 if trace.end_time else None,
        "final_answer": trace.final_answer,
        "overall_confidence": trace.overall_confidence,
        "events": events,
        "hemisphere_states": hemisphere_states,
        "event_count": len(events),
    }


@app.post("/traces/{trace_id}/drill-down")
async def drill_down(trace_id: str, event_id: str):
    """
    Drill down into specific reasoning step (C: Interactive drill-down).
    Returns detailed view of event + children + hemisphere state.
    """
    if not _TRACER_AVAILABLE:
        raise HTTPException(503, "Tracer not available")
    
    result = _tracer.drill_down(trace_id, event_id)
    if not result:
        raise HTTPException(404, f"Event {event_id} not found in trace {trace_id}")
    
    return result


@app.get("/traces/{trace_id}/stream")
async def stream_trace(trace_id: str):
    """
    Stream real-time events for an active trace (B: Real-time streaming).
    Connect to this endpoint to watch reasoning as it happens.
    """
    if not _TRACER_AVAILABLE:
        raise HTTPException(503, "Tracer not available")
    
    # Check if trace exists and is active
    trace = _tracer.get_active_trace(trace_id)
    if not trace:
        # Check if completed
        trace = _tracer.get_trace(trace_id)
        if trace:
            # Return completed trace events
            async def completed_stream():
                for event in trace.events:
                    yield f"data: {json.dumps({
                        'event_id': event.event_id,
                        'event_type': event.event_type.value,
                        'hemisphere': event.hemisphere.value if event.hemisphere else None,
                        'timestamp': event.timestamp,
                        'data': event.data,
                    })}\n\n"
                yield f"data: {json.dumps({'event_type': 'completed', 'trace_id': trace_id})}\n\n"
            
            return StreamingResponse(
                completed_stream(),
                media_type="text/event-stream",
            )
        else:
            raise HTTPException(404, f"Trace {trace_id} not found")
    
    # Stream active trace
    async def active_stream():
        async for event in _tracer.stream_trace(trace_id):
            yield f"data: {json.dumps(event)}\n\n"
    
    return StreamingResponse(
        active_stream(),
        media_type="text/event-stream",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)