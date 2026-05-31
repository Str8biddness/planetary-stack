# Production API Server + Synthesus 5 CHAL Query Path

## Overview
Production-grade FastAPI server integrating the legacy-compatible character/RAG
pipeline with the active Synthesus 5 CHAL runtime. The stable public response
envelope remains `QueryResponse`; clients opt into the current Cognitive
Hypervisor path with `mode="chal"` on `/api/v1/query`.

## Architecture

```
Client Request
    │
    ▼
┌─────────────────────┐
│  Rate Limiter/Auth   │  Demo: 10 RPM │ Auth: 60 RPM
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  mode="chal"?        │  yes → Cognitive Hypervisor
└──────┬──────────────┘
       │ no
       ▼
┌─────────────────────┐
│  Cognitive Engine    │  Character-specific patterns + emotion + memory
│  (confidence > 0.7)  │
└─────────┬───────────┘
          │ (miss)
          ▼
┌─────────────────────┐
│  FAISS RAG Pipeline  │  Knowledge Cloud / local vector retrieval
│  (score ≥ 0.65)      │
└─────────┬───────────┘
          │ (miss)
          ▼
┌─────────────────────┐
│  Character Fallback  │  Polite "I don't know" with character personality
└─────────────────────┘
```

### Synthesus 5 CHAL Mode

`POST /api/v1/query` accepts `mode="chal"` and routes explicitly through
`CognitiveHypervisor`. When `include_debug=true`, responses include:

```json
{
  "source": "cognitive_hypervisor",
  "debug": {
    "cognitive_hypervisor": {
      "schema": "synthesus.chal.hypervisor_trace.v1",
      "route": "fast_path | grounded_path | deep_reasoning_path | quad_brain_path | safety_path",
      "budget": {
        "latency_ms": 450.0,
        "retrieval_depth": 1,
        "candidate_count": 1,
        "critic_passes": 0
      },
      "device_isolation": {},
      "template_guard": {},
      "knowledge_provenance": {
        "schema": "synthesus.chal.knowledge_provenance.v1",
        "source": "rom_mount:kc_knowledge_cloud_world_lore_json",
        "context_used": true,
        "mounted_context_used": true,
        "cache_hit": false,
        "mounts": []
      },
      "quad_brain": null
    }
  }
}
```

The typed trace contract is mirrored as `CognitiveHypervisorTrace` in
`docs/openapi.yaml`, `docs/openapi.json`, and `docs/api_schema.json`.
`CognitiveHypervisorTrace.knowledge_provenance` records mounted Knowledge Cloud
provenance for grounded CHAL routes, including KAL operation, source mount,
cache state, and artifact integrity metadata when available.
`CognitiveHypervisorTrace.quad_brain` references `QuadBrainArbitration` when the
route is `quad_brain_path`, matching the runtime `telemetry.quad_brain` payload.
CGPU device-frame schemas are documented separately as `CGPUFrame` and
`CGPUOutputFrame`; `/api/v1/query` does not emit CGPU candidate sets as top-level
payloads.

### Synthesus 5 Smoke Command

Run the focused CHAL API smoke check from the repository root:

```bash
SYNTHESUS_KNOWLEDGE_SYNC_MODE=off python tools/synthesus5_chal_smoke.py
```

The command uses the FastAPI app in-process and sends three public
`/api/v1/query` calls with `mode="chal"` and `include_debug=true`. It fails if
the CHAL response source is missing, hypervisor trace schema is absent, the
expected grounded/Quad Brain/safety route is not selected, the request degrades
or exhausts budget, Quad Brain serial-order telemetry is malformed, or a legacy
template signature leaks into final text.

### Synthesus 5 Focused Release Suite

Run the focused release-readiness suite before treating the explicit CHAL path
as production-ready:

```bash
SYNTHESUS_KNOWLEDGE_SYNC_MODE=off python tools/synthesus5_focused_suite.py
```

The suite compiles the CHAL release-path modules, runs the public CHAL API smoke
command, verifies the hypervisor/API E2E regressions, and runs the PPBRS
firmware plus Phase 8 comparison-harness checks. It sets the same local
`PYTHONPATH`, disables Knowledge Cloud network sync by default, and fails on the
first broken release-readiness step.

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/query` | POST | Main query; `mode="chal"` routes through Synthesus 5 Cognitive Hypervisor, `auto` preserves the legacy-compatible pipeline |
| `/api/v1/chat` | POST | Multi-turn conversation |
| `/api/v1/characters` | GET | List all characters |
| `/api/v1/characters/{id}` | GET | Character details |
| `/api/v1/health` | GET | System health + stats |
| `/api/v1/stats` | GET | Detailed telemetry |
| `/docs` | GET | Swagger UI |

## Knowledge Base

### Historical Phase 20 baseline: 78,022 patterns from 18 datasets
- SQuAD (10K), Alpaca (10K), Dolly (10K), SciQ (5K)
- CommonsenseQA (5K), HellaSwag (5K), BoolQ (5K), Orca DPO (5K)
- GSM8K (5K), MedMCQA (5K), ARC (3.3K+3K), OpenBookQA (3K)
- TruthfulQA (800), MathInstruct (10K)
- Character patterns (864 across 6 characters)

Current Synthesus 5 knowledge behavior is governed by Knowledge Cloud hardware
mounts, KAL/CHAL interfaces, and the active implementation checklist rather
than this old embedded-vector count alone.

### Scaling Path to 1M+
1. Run `scripts/enrichment_round2.py` with more datasets (OpenOrca, CodeAlpaca, etc.)
2. Switch from IndexFlatIP to IndexIVFFlat for >500K vectors (10x faster search)
3. Shard metadata to reduce memory (JSON → SQLite)
4. Capacity: FAISS handles 10M+ vectors on 8GB RAM with IVF

## Characters Deployed
1. **Synth** — AIVM brand ambassador
2. **Synthesus** — Flagship male NPC
3. **Computress** — Flagship female NPC
4. **Haven** — Wellness/mental health companion
5. **Lexis** — Technical documentation expert
6. **Garen** — Game NPC merchant (fantasy RPG)

## Test Results
- 14/14 semantic search tests PASS
- Avg search latency: 31.6ms (P50: 30.6ms, P95: 48.8ms)
- Rate limiting: verified (429 after 10 RPM demo limit)
- Character routing: cognitive for character knowledge, RAG for general

## Running
```bash
# Start server
python3 packages/api/production_server.py

# With auth
SYNTHESUS_API_KEY=your-key python3 packages/api/production_server.py
```

## Current Contract Files
- `packages/api/production_server.py` — Production FastAPI server
- `packages/api/schemas.py` — Request/response models
- `docs/openapi.yaml` — OpenAPI mirror
- `docs/openapi.json` — OpenAPI mirror
- `docs/api_schema.json` — API schema mirror
