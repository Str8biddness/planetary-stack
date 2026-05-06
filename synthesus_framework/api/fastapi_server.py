# Synthesus 2.0 - FastAPI Server
# Full REST + SSE streaming server for the ZO kernel
from __future__ import annotations
import asyncio
import subprocess
import json
import os
import glob as _glob
from typing import AsyncIterator, Optional, Dict, List, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
try:
    from sse_starlette.sse import EventSourceResponse
    _HAS_SSE = True
except ImportError:
    _HAS_SSE = False
    EventSourceResponse = None

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cognitive.cognitive_engine import CognitiveEngine

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

KERNEL_BIN = os.path.join(os.path.dirname(__file__), "..", "zo_kernel")
CHARACTERS_DIR = os.path.join(os.path.dirname(__file__), "..", "characters")
_kernel_proc: Optional[subprocess.Popen] = None
_character_cache: Dict[str, Dict[str, Any]] = {}
_cognitive_engines: Dict[str, CognitiveEngine] = {}
MAX_ENGINES = 50
_rate_limits: Dict[str, List[float]] = defaultdict(list)
_rate_limit_lock = asyncio.Lock()

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
        engine = CognitiveEngine(
            character_id=char_id,
            bio=char_data["bio"],
            patterns=char_data["patterns"],
            char_dir=char_dir,
            kal_client=_kal_client,  # V4: pass KAL client for pre-fetch
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
        if os.path.exists(KERNEL_BIN):
            _kernel_proc = subprocess.Popen(
                [KERNEL_BIN], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1
            )
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
    return {"status": "ok", "kernel": kernel is not None and kernel.poll() is None}

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)