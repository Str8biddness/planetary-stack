# Synthesus System Map (Current State)

This document explains how the repository currently works end-to-end, how major modules connect, and where behavior diverges from a strict offline, non-templated generation goal.

## 1) Top-Level Architecture

Synthesus is a multi-layer stack:

- API orchestration layer (`api/`)
- Cognitive + retrieval + symbolic pipelines (`cognitive/`, `core/`, `ml/`)
- Generation/finalization layer (`core/generation/`)
- Optional control plane and accelerator subsystems (`control_plane/`, `accelerators/`)
- Multiple client surfaces (`static/`, `frontend/`, `templates/`, `sdk/`)

Primary runtime path is `api/production_server.py`.

## 2) Runtime Entry Points

### Production server (canonical)

- `api/production_server.py`
- Exposes `/api/v1/query` and monitoring/health endpoints.
- Also contains legacy compatibility routes `/query` and `/api/query` that normalize old payloads and delegate into the v1 path.

### Alternate servers (legacy/parallel)

- `api/fastapi_server.py`
- `api/gateway.py`
- These expose older contracts and can diverge from production behavior.

### Package default

- `api/__init__.py` exports the production app.

## 3) Startup and Global Initialization

On startup, `api/production_server.py` initializes:

- ML Swarm models (`ml/intent_classifier.py`, `ml/sentiment_analyzer.py`, `ml/emotion_detector.py`, `ml/behavior_predictor.py`, `ml/dialogue_ranker.py`)
- RAG pipeline (`core/rag_pipeline.py`)
- Optional high-level thinker (`core/synthesus_master.py`) and trainer
- Optional accelerator registry (`accelerators/`)
- Optional control-plane pieces (`control_plane/`)
- Amplification plane and symbolic core (if available)
- Generation Spine singleton (`core/generation/spine.py`)
- Character caches and websocket dashboard broadcaster

Important: behavior is feature-flag and import dependent (`HAS_*` guards), so runtime can vary by environment.

## 4) Query Flow (Canonical)

Endpoint: `POST /api/v1/query` in `api/production_server.py`.

High-level order:

1. Auth + rate limiting + character/session validation
2. Optional symbolic short-circuit
3. Early memory extraction (emotion/relationship context)
4. Optional amplification intake/planning
5. ML swarm context build
6. Cognitive engine attempt (`cognitive/cognitive_engine.py`)
7. Escalation path (if triggered) via `SynthesusMaster.think(...)`
8. RAG attempt (`core/rag_pipeline.py`) if needed
9. Final fallback string if no strong result
10. Finalize through Generation Spine (safety + metrics + trace)

## 5) Generation Stack

Core files:

- `core/generation/spine.py`
- `core/generation/decoder.py`
- `core/generation/ngram_model.py`
- `core/generation/organ_param_mapper.py`
- `core/generation/response_plan.py`

Current behavior:

- Spine can finalize provided text (`raw_text`) or generate from a response plan.
- Decoder uses local n-gram vocab models (`vocab_*.pkl`) with constrained sampling.
- Decoder/spine model directory has been unified via configurable models dir.
- Safety and risk gates are applied in spine output finalization.

Current limitation:

- Template-like fallback text still exists in fallback paths (spine/cognitive/API), so generated responses are not guaranteed to be fully non-templated.

## 6) Cognitive/RAG/Agentic Behavior

### Cognitive

- `cognitive/cognitive_engine.py` orchestrates:
  - semantic matching
  - memory/state modules
  - escalation logic
  - response composition
- Fallback chain may return canned text if richer modules miss.

### RAG

- `core/rag_pipeline.py` performs local FAISS retrieval and metadata lookup.
- Pattern responses can be selected directly from stored templates.

### Agentic/tool behavior

- `cognitive/agent_dispatcher.py` can route certain intents to tools.
- `core/tools/scraper.py` and web-scraping pathways can introduce network dependence unless explicitly disabled.

## 7) Frontend and Client Surfaces

### Modern built-in frontend

- `static/index.html` + `static/js/app.js`
- Uses `/api/v1/*` endpoints and is mostly aligned with production server.

### React frontend

- `frontend/src/*`
- Uses `/api/v1/query`, `/api/v1/characters`, dashboard/metrics endpoints.

### Legacy template UI

- `templates/query.html` + `static/script.js`
- Historically legacy; now query call is wired to `/api/v1/query`, but it still contains legacy expectations for feedback/status payloads.

### SDK clients

- `sdk/python/`, `sdk/unity/`, `sdk/unreal/`
- Many still target old `/api/*` contracts and payload keys (`character_id`).

## 8) Tests and Validation Coverage

Strong areas:

- Generation primitives and decoder behavior:
  - `tests/test_decoder.py`
  - `tests/test_constrained_sampler.py`
  - `tests/test_ngram_model.py`
  - `tests/test_response_plan.py`
  - `tests/test_organ_param_mapper.py`
- Spine integration:
  - `tests/test_generation_spine_integration.py`

Gaps:

- No strict offline contract test suite across full query path.
- No hard non-templated output gate (diversity/template-leak checks).
- Legacy client compatibility and route deprecation are only partially covered.

## 9) External Dependency Surfaces

Core runtime is primarily local inference, but external dependency surfaces still exist:

- Optional remote/local accelerator adapters (`accelerators/remote_adapter.py`, `accelerators/local_gpu_adapter.py`)
- Web scraping/tool dispatch paths
- Legacy feature modules and scripts expecting networked services

## 10) What Is Already True vs Goal

Already true:

- Production path can run local without external LLM APIs in normal operation.
- Spine is wired and active in production query path.
- Modern frontend targets v1 endpoints.

Not yet guaranteed:

- Fully non-templated output under all fallback conditions
- Zero network-dependent behavior under all execution branches
- Unified contracts across all clients/SDKs/legacy UIs
