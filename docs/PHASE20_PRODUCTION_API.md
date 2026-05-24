# Phase 20: Production API Server + RAG Embedding Pipeline

## Overview
Production-grade FastAPI server integrating FAISS semantic retrieval (78K+ patterns),
character routing with cognitive engine fallback, API key auth, and rate limiting.

## Architecture

```
Client Request
    │
    ▼
┌─────────────────────┐
│  Rate Limiter        │  Demo: 10 RPM │ Auth: 60 RPM
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Cognitive Engine    │  Character-specific patterns + emotion + memory
│  (confidence > 0.7) │  → 0.27ms - 1.5s latency
└─────────┬───────────┘
          │ (miss)
          ▼
┌─────────────────────┐
│  FAISS RAG Pipeline  │  78K+ vectors, SwarmEmbedder (TF-IDF + SVD) embeddings
│  (score ≥ 0.65)     │  → 30-65ms latency
└─────────┬───────────┘
          │ (miss)
          ▼
┌─────────────────────┐
│  Character Fallback  │  Polite "I don't know" with character personality
└─────────────────────┘
```

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/query` | POST | Main query (character-routed + RAG) |
| `/api/v1/chat` | POST | Multi-turn conversation |
| `/api/v1/characters` | GET | List all characters |
| `/api/v1/characters/{id}` | GET | Character details |
| `/api/v1/health` | GET | System health + stats |
| `/api/v1/stats` | GET | Detailed telemetry |
| `/docs` | GET | Swagger UI |

## Knowledge Base

### Current: 78,022 patterns from 18 datasets
- SQuAD (10K), Alpaca (10K), Dolly (10K), SciQ (5K)
- CommonsenseQA (5K), HellaSwag (5K), BoolQ (5K), Orca DPO (5K)
- GSM8K (5K), MedMCQA (5K), ARC (3.3K+3K), OpenBookQA (3K)
- TruthfulQA (800), MathInstruct (10K)
- Character patterns (864 across 6 characters)

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
# First time: build the FAISS index
python3 scripts/embedding_pipeline.py

# Start server
python3 api/production_server.py

# With auth
SYNTHESUS_API_KEY=your-key python3 api/production_server.py
```

## Files Added
- `api/production_server.py` — Production FastAPI server (480 lines)
- `scripts/embedding_pipeline.py` — HuggingFace dataset embedding pipeline
- `scripts/enrichment_round2.py` — Additional dataset loader
- `docs/PHASE20_PRODUCTION_API.md` — This file
