# Synthesus 3.0

> **AIVM Synthesus** — Synthetic Core + Amplification Plane + ML Organs

[![Version](https://img.shields.io/badge/Version-3.0.0-green)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)]()
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-blue)]()

Synthesus 3.0 is a synthetic reasoning engine that uses a symbolic core plus small learning “organs” and an Amplification Plane to reason across multiple domains (GM, SysOps, and Chat). It features professional-grade autonomy controls, self-improving feedback loops, and a transparent reasoning persona.

---

## Architecture

```
                       PLAYER INPUT
                           │
                ┌──────────┴──────────┐
                │                     │
         LEFT HEMISPHERE       RIGHT HEMISPHERE
         Pattern Matching      9 Cognitive Modules
                │                     │
         • Tokenized triggers  • Conversation Tracker
         • Confidence scoring  • Emotion State Machine
         • Fallback cascades   • Relationship System
         • <1ms resolution     • World-State Reactor
                │              • Knowledge Graph
                │              • Personality Bank
                │              • Context Recall
                │              • Response Compositor
                │              • Escalation Gate
                │                     │
                └──────────┬──────────┘
                      RECONCILER
                           │
                   ML SWARM (7 models)
                      ~458 KB total
                       <1ms inference
                           │
                       RESPONSE
                           │
                ┌──────────┴──────────┐
                │                     │
            ACCELERATION LAYER    COGNITIVE POWER-UPS
            CPU/Remote/Local GPU  Parallel Rollouts
            Adapters              History Clustering
                │                     │
            HTTP Inference        What-If Scenarios
            Scaling              Pattern Discovery
                │                     │
                └──────────┬──────────┘
                      ENHANCED RESPONSE
```

### AIOS Memory Model

Synthesus now treats memory as layered state instead of a single transcript buffer.

- **Episodic** — interaction history and event traces
- **Semantic** — durable facts and learned knowledge
- **Procedural** — reusable behavior rules and recipes
- **Working** — volatile task scratch state
- **Crystallized** — slow-changing facts, rules, and causal structure
- **Fluid** — active observations, hypotheses, predictions, and goals
- **Narrative** — the reasoning timeline and action log

Implementation notes:
- `file 'synthesus/core/memory_store.py'`
- `file 'synthesus/core/conscious_state.py'`
- `file 'synthesus/cognitive/state_persistence.py'`
- `file 'synthesus/docs/AIOS_MEMORY_MODEL.md'`

For the detailed contract and save/load boundary, read `file 'synthesus/docs/AIOS_MEMORY_MODEL.md'`.

### ML Organ Training

The ML organ loop is documented in `file 'synthesus/docs/ML_ORGAN_TRAINING.md'`.

Use that guide when you need to resume the trace-driven self-improvement workflow from a fresh chat.

The self-improvement command also generates an evaluation scorecard under `file 'synthesus/logs/'`; those scorecard files are runtime artifacts and are ignored by Git.

### Left Hemisphere — Pattern Matching
Pure pattern matching: tokenized triggers, confidence scoring, fallback cascades. The left hemisphere resolves most queries under 1ms.

### Right Hemisphere — Cognitive Swarm
1. **Conversation Tracking** — turn-by-turn context memory
2. **Emotion State Machine** — 10-state emotional model with transitions
3. **Relationship System** — per-player trust, rapport, and history
4. **World-State Awareness** — react to game events, weather, and time
5. **Knowledge Graph** — structured domain knowledge per character
6. **Knowledge Cloud** — shared world lore with semantic search (FAISS)
7. **Social Fabric** — NPC-to-NPC gossip, rumors, and faction dynamics
8. **Universal Substrate** — unified parameter access (Postgres + Smart FS)
9. **Context Recall** — episodic and semantic memory retrieval
10. **Escalation Gating** — route complex queries to deeper processing

Together, they create NPCs that remember, feel, and react.

### ML Swarm — 12 Specialized Micro-Models
Replaces what used to require a 0.6B parameter language model. Instead of one big model, we use 12 specialized micro-models (7 player-facing, 5 world-facing). Total footprint: **~458 KB**. Total inference: **under 1ms**. That's shippable on a PS5 or mid-tier gaming PC.

---

### Key Subsystems

| Subsystem | Language | Purpose |
|---|---|---|
| `ml/` | Python | ML Swarm: 7 micro-models — intent, sentiment, embeddings, etc. |
| `cognitive/` | Python | Right Hemisphere: 9 cognitive modules (emotion, memory, relationships...) |
| `core/` | Python | Left Hemisphere: PatternEngine, RAGPipeline, HemisphereBridge |
| `core/breach/` | Python | Red Team security testing — attack trees, vulnerability scanning, brute-force simulation |
| `api/` | Python | FastAPI production server + gateway |
| `kernel/` | C++ | Thread pool, memory allocator, message bus |
| `reasoning/` | C++ | PPBRS, causal, Bayesian, symbolic, SINN, planner |
| `memory/` | C++ | Episodic, working, long-term, self-perception, KN DB |
| `vcu/` | C++ | 11 Virtual Control Units (emotion, executive, language...) |
| `unpc_engine/` | Python | Universal NPC Character Engine with archetype genome system |
| `studio/` | Python/HTML | Character Studio — build, test, and export NPC characters |

---

## Features

### Recent Updates (April-May 2026)
- **Breach Red Team Module**: Implemented adversarial security testing architecture with abductive reasoning, memory vulnerability scanning, attack tree generation, and credential pressure simulation for automated Blue Team training.
- **Parallel Hemisphere Execution**: Enhanced `ReasoningCore` and `HemisphereBridge` to drive both Left and Right hemispheres in parallel, reducing latency while improving synthesis quality.
- **Game Bridge (Neon Bay 2087)**: Added `api/game_bridge.py` providing a dedicated bridge for the Neon Bay 2087 KPC system (`POST /think`).
- **Shared ML Organs**: Expanded the organ family with shared runtime modules for Prediction, Forecast, Sequence Prediction, Relation Extraction, and Summarization.
- **Reasoning Layer Architecture**: Improved orchestrator, domain router, verifier, and synthesizer for multi-entity logic.
- **ML Organ Self-Improvement**: Integrated trace-driven training for PolicyPrior, RiskOutcome, and Attention organs with automated scorecard evaluation.
- **Knowledge Cloud Expansion**: Massive lore expansion (25+ nodes) with full SlotFiller coverage and SequenceLinker stabilization for deterministic response chaining.
- **PPBRS Optimization**: Established baseline performance metrics and candidate reduction indexing for sub-5ms pattern matching.
- **AIOS Memory Model**: Implemented layered memory system (episodic, semantic, procedural, working) with restartable persistence.
- **AIVM Hardening**: Added ONNX hooks, isolation layers, and circuit breaker recovery for model inference.

- **Synthetic Core (v3)** — Symbolic world-model engine that runs alone on CPU; no ML required for basic safety/logic.
- **Knowledge Cloud** — Shared world lore with semantic search and "lore evolution" (NPC witnessing).
- **Universal Substrate (V2)** — Hybrid parameter layer with Postgres/pgvector and local Smart FS.
- **Social Fabric** — Multi-NPC relationship networks and rumor propagation.
- **Amplification Plane** — Converts compute "fuel" into deeper cognition (Intake, Planning, Output phases).
- **Learned Triads** — Specialized organs for **PolicyPrior**, **RiskOutcome**, and **Attention**.
- **Dynamic Autonomy** — Three modes: **Advisor**, **Co-pilot**, and **Autopilot**.
- **Self-Improvement Loop** — Automated training and promotion based on session traces.
- **Zero GPU Required** — Optimized for high-speed inference on standard hardware.

### Red/Blue Team Security Architecture

Synthesus 4.0 implements a **Dual-Adversarial Substrate** for automated security hardening and threat modeling:

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  Red Team    │  →   │   Emulation  │  →   │  Blue Team   │
│  (Breach)    │      │   Sandbox    │      │ (Ghostkey)   │
└──────────────┘      └──────────────┘      └──────────────┘
   Abductive              Docker              Inductive/
   Reasoning           Containers            Deductive
   Attack Trees         Isolated             Detection &
   Vuln Scanning        Testing              Mitigation
```

**Breach (Red Team)** — Uses abductive reasoning to identify attack surfaces:
- **Attack Tree Generation**: Structured JSON attack paths with MITRE ATT&CK techniques
- **Memory Pattern Matcher**: Scans for unsafe functions (strcpy, gets), vulnerable library versions, injection patterns
- **Brute Force Simulator**: Generates credential pressure to train detection systems
- **Crash Analysis**: Works backward from failures to find root causes

**Ghostkey (Blue Team)** — Monitors and defends:
- **ImmuneSystem**: SHA-256 integrity monitoring for critical files
- **SecurityTools**: Nmap scanning, process termination, IP blocking
- **Anomaly Detection**: ML-based detection trained on Breach simulation data

All Red Team operations default to **sandbox mode** via Docker containers. Live mode requires explicit `breach` character authorization.

---

## Quick Start

### Prerequisites

- Python 3.10+
- CMake 3.18+ (optional — for C++ kernel)

### Installation

```bash
# Clone and create venv
git clone https://github.com/Str8biddness/synthesus.git
cd synthesus
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate

# Install dependencies
pip install fastapi "uvicorn[standard]" httpx pydantic numpy scipy scikit-learn faiss-cpu python-dotenv rich tenacity

# Start the production server
uvicorn api.production_server:app --host 0.0.0.0 --port 5000
```

See [REQUIREMENTS.md](REQUIREMENTS.md) for one-liner setup commands for all Operating Systems.
See [INSTALLATION.md](INSTALLATION.md) for detailed setup instructions, database migrations, and the Character Studio.

### Knowledge Cloud Sync

Synthesus treats `data/` as a local cache. On startup, the knowledge loaders try to pull missing cloud artifacts from `SYNTHESUS_KNOWLEDGE_CLOUD_URL` (default: `https://zo.pub/syntech/synthesus-knowledge`) unless `SYNTHESUS_KNOWLEDGE_SYNC_MODE=off`.

To publish a cloud bundle, generate a manifest from the data root:

```bash
python -m knowledge_integration.cloud_sync --write-manifest --root ./data \
  --artifact faiss.index \
  --artifact faiss_metadata.json \
  --artifact models/swarm_embedder.pkl:optional \
  --artifact knowledge_cloud/world_lore.json \
  --artifact knowledge_cloud/evolution.json:optional
```

Then sync that directory to your cloud host or Zo pub collection. Clients cloning the repo will auto-bootstrap the cache the next time Synthesus starts.

### Docker

```bash
docker build -t synthesus:2.0 .
docker run -p 5000:5000 synthesus:2.0
```

---

## API Usage

### Query a Character

```bash
curl -X POST http://localhost:5000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What do you sell?", "character": "synth"}'
```

### Multi-Turn Conversation

```bash
curl -X POST http://localhost:5000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Tell me about the ancient war", "character": "sage", "session_id": "my-session"}'
```

### List Characters

```bash
curl http://localhost:5000/api/v1/characters
```

### Health Check

```bash
curl http://localhost:5000/api/v1/health
```

---

## Available Archetypes

| Archetype | Response Style | Dominant Traits |
|---|---|---|
| `warrior` | aggressive_direct | motor, executive |
| `sage` | philosophical_deliberate | language, memo |
| `doctor` | clinical_empathetic | language, social |
| `detective` | analytical_skeptical | executive, perception |
| `merchant` | persuasive_pragmatic | social, language |
| `teacher` | instructional_patient | language, social |
| `scientist` | precise_curious | executive, memo |
| `soldier` | direct_tactical | motor, executive |
| `noble` | formal_authoritative | executive, social |
| `trickster` | playful_deflective | language, social |
| `software_engineer` | technical_methodical | executive, memo |

Custom archetypes can be added by creating JSON files in `unpc_engine/archetypes/`.

---

## Development

```bash
# Run tests
pytest tests/ -v

# Run benchmarks
python scripts/benchmark.py

# Build C++ kernel (optional)
cmake -B build && cmake --build build
```

---

## Project Structure

```
synthesus/
├── synthetic_core/   # Core interfaces and symbolic engine
├── amplification/    # Amplification Plane & domain handlers
├── organs/           # ML Organs (PolicyPrior, RiskOutcome, Attention)
├── learning/         # Trace logging, training runners, and feedback data
├── scripts/          # Training sessions and self-improvement loop
├── domains/          # Domain adapters (gm, sysops, chat)
├── utils/            # Shared utilities & Guardrails engine
├── api/              # FastAPI production server & web gateway
├── characters/       # Character registry & personality files
├── cognitive/        # Legacy Right Hemisphere: Cognitive modules
├── core/             # Legacy Left Hemisphere: PatternEngine
├── ml/               # Legacy micro-models
└── studio/           # Character Studio & web tools
```

---

## Labs: Control Plane & AI VM Quickstart

Experimental features for device management, emulation experiments, and GM/world-simulation.

**Capabilities**:
- Device control plane with approvals for secure onboarding.
- AI VM hosts: Run experiments inside containers on enrolled devices.
- Emulation profiles: SysOps (CPU/IO stress) and GM (combat/NPC/world ticks).
- Scheduler: Automate periodic experiments on AI VM hosts.
- Acceleration layer: CPU, remote, and local GPU adapters for inference.
- Parallel rollouts: Multi-scenario what-if analysis for experiments.
- History clustering: Group experiments by behavior patterns.
- Persistence: Store experiments, rollouts, and clusters across restarts.

**Local Dev Recipe**:
1. Clone repo, create venv, install requirements.
2. Set env vars:
   ```
   ENABLE_CONTROL_PLANE=true
   ALLOW_DEVICE_ONBOARDING=true
   LOCAL_AI_VM_HOST=true
   ENABLE_EMULATION_SCHEDULER=true  # optional
   ENABLE_ACCELERATION_LAYER=true   # optional for accelerators
   DEBUG_CONTROL_PLANE_FIXTURES=true  # optional for fake data
   ACCEL_REMOTE_ENDPOINT_URL=...    # optional for remote accelerator
   ACCEL_REMOTE_API_KEY=...         # optional
   ACCEL_LOCAL_GPU_ENDPOINT_URL=... # optional for local GPU
   HISTORY_STORE_PATH=./data/experiments_history.jsonl  # optional
   ```
3. Start backend: `uvicorn api.production_server:app --host 0.0.0.0 --port 5000`
4. Open frontend at `http://localhost:5000`
5. Go to Labs → enable flags if needed.
6. Go to Control Plane → verify local ai_vm_host → run an experiment → (optional) add a schedule.
7. Ask Synthesus to summarize recent experiments or analyze trends.

**Safety**: All features off by default. Experiments run in containers or simulation, not bare metal. For local/sandbox use only.

See `docs/labs_overview.md` for details.

---

## Amplification Plane

The Amplification Plane provides intelligent decision support through ML organ-driven triad scoring:

### Architecture

```
Input → Intake(Risk) → Planning(Rank) → Output(Autonomy) → Dispatch → Action
         │                │                    │
         └────┬───────────┴───────────┬────────┘
              │         ML Organs Hub        │
              │  PolicyPrior │ RiskOutcome   │
              │  Attention   │ AnomalyEvent  │
              │  Summarizer                 │
```

### Three Phases

**1. Intake** - Risk assessment and triad computation:
```typescript
const result = await amplifyIntake(ctx, worldState);
// { riskScore, triad, prioritizedFocus, needsOperatorAttention }
```

**2. Planning** - Action ranking with rollouts:
```typescript
const result = await amplifyPlanning(ctx, worldState, candidateActions);
// { rankedActions, confidenceMargins, rolloutProjections, executionRecommendation }
```

**3. Output** - Sanity check and autonomy enforcement:
```typescript
const result = await amplifyOutput(ctx, { chosenAction, updatedWorld });
// { sanityCheckPassed, operatorExplanation, internalSummary, executionRecommendation }
```

### Supported Domains
- **chat** - Conversational AI with intent analysis
- **sysops** - System operations and monitoring  
- **gm** - Game Master for interactive narratives
- **multimodal** - Vision + voice + text integration

---

## Multimodal Capabilities

### Vision Adapter
```typescript
import { VisionAdapter } from './vision/visionAdapter';

const vision = new VisionAdapter();
const result = await vision.processImage(base64Image);
// Returns: objects[], scene classification, embeddings, alignment score
```

### Voice Synthesis
```typescript
import { VoiceSynthesis } from './voice/voiceSynthesis';

const voice = new VoiceSynthesis();
const transcript = await voice.transcribe(audioBuffer);
const tts = await voice.synthesize('Hello world', { speed: 1.0, pitch: 1.0 });
```

### Cross-Modal Alignment
```typescript
import { CrossModalAligner } from './multimodal/crossModalAlignment';

const aligner = new CrossModalAligner();
const fused = aligner.fuseEmbeddings(visionEmb, voiceEmb, textEmb);
// Returns: unifiedFeatures, modalityWeights, confidence
```

---

## VEAI Integration

The Amplification Bridge connects triad scores to organ promotion/demotion:

```python
from core.amplification_bridge import AmplificationBridge, AmplificationSignal

bridge = AmplificationBridge(synthesus_master, veai_trainer)
bridge.emit_signal(AmplificationSignal(
    session_id='session-123',
    domain='chat',
    phase='planning',
    risk_score=0.3,
    confidence_margin=0.8,
    organ_scores={'policy_prior': 0.85, 'risk_outcome': 0.7}
))

# Auto-promotes/demotes organs based on performance
report = bridge.get_organ_health_report('chat')
```

---

## Security

Input validation and sanitization for multimodal endpoints:

```python
from api.security_middleware import SecurityValidator

validator = SecurityValidator()
result = validator.validate_multimodal_query({
    'text': 'Hello',
    'base64Image': 'data:image/jpeg;base64,...'
}, session_id)
# Returns: { valid, errors, sanitized }
```

- Rate limiting (60 req/min)
- Base64 validation
- Image/audio size limits (10MB/50MB)
- XSS prevention
- URL scheme validation

---

## API Reference

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/query` | POST | Main query endpoint with amplification |
| `/api/v1/health` | GET | System health status |
| `/api/v1/stats` | GET | Detailed statistics |
| `/api/v1/amplification/status` | GET | Amplification Plane status |
| `/api/v1/amplification/metrics` | GET | Performance metrics |
| `/api/v1/monitoring/dashboard` | GET | Unified dashboard JSON |
| `/dashboard` | GET | HTML monitoring UI |

### Query Example
```bash
POST /api/v1/query
Content-Type: application/json

{
  "query": "What do you see?",
  "character_id": "assistant",
  "session_id": "test-123",
  "base64Image": "data:image/jpeg;base64,/9j/4AAQ...",
  "base64Audio": "data:audio/wav;base64,UklGRiQAA..."
}
```

---

## Development

### TypeScript Compilation
```bash
npx tsc --noEmit        # Check types
npx tsc                 # Build to dist/
```

### Running Tests
```bash
npx jest                # Run all tests
npx jest --testPathPattern=featureAdapters  # Specific tests
```

### Starting Server
```bash
# Development
uvicorn api.production_server:app --reload --host 0.0.0.0 --port 5000

# Production
python -m api.production_server
```

---

## Project Structure

```
synthesus/
├── amplification/           # Amplification Plane
│   ├── index.ts            # Main dispatchers
│   ├── chatAmplification.ts
│   ├── sysopsAmplification.ts
│   ├── gmAmplification.ts
│   ├── multimodalAmplification.ts
│   └── mlOrgansHub.ts
├── api/                     # FastAPI server
│   ├── production_server.py
│   ├── security_middleware.py
│   └── routes/
├── control_plane/           # Experiment management
│   ├── history_store.py
│   ├── parameter_sweep.py
│   └── scheduler.py
├── core/                    # Python core
│   ├── synthesus_master.py
│   ├── veai_trainer.py
│   ├── cognitive_core.py
│   └── amplification_bridge.py
├── domains/                 # Domain adapters
│   ├── chat/
│   ├── sysops/
│   ├── gm/
│   └── multimodal/
├── vision/                  # Vision processing
│   └── visionAdapter.ts
├── voice/                   # Voice synthesis
│   └── voiceSynthesis.ts
├── multimodal/              # Cross-modal alignment
│   └── crossModalAlignment.ts
├── organs/                  # ML organ definitions
│   ├── registry.ts
│   └── autonomyConfig.ts
├── utils/                   # Utilities
│   ├── guardrails.ts
│   └── securityValidator.ts
├── tests/                   # Unit tests
│   └── domains/
└── scripts/                 # CLI scripts
    └── amplifyCli.ts
```

---

### PPBRS Optimization Roadmap

The start-to-finish PPBRS upgrade plan is documented in `docs/PPBRS_OPTIMIZATION_UPGRADE.md`.

It covers the baseline benchmark, candidate reduction in pattern matching, rule indexing, graph traversal caching, kernel offload, and the required regression validation/logging steps.
