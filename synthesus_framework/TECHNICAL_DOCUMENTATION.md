# Synthesus 2.0 — Technical Documentation

## Project Overview

- **Repository:** github.com/Str8biddness/synthesus
- **Version:** 2.0.0
- **Architecture:** Dual-Hemisphere NPC AI System
- **Goal:** A game-ready NPC brain that runs 90% on pattern matching and 10% on specialized ML micro-models (~458 KB total footprint), shippable on PS5 or a mid-tier gaming PC.

## Core Philosophy

Synthesus 2.0 replaces traditional LLM-based NPC dialogue with a dual-hemisphere cognitive architecture:

**Left Hemisphere** — Fast pattern matching. Handles ~60% of all queries at <1ms latency. Zero GPU, zero ML. Pure algorithmic text matching with scored confidence. Hybrid token + semantic matching via SwarmEmbedder (TF-IDF + SVD) + FAISS.

**Right Hemisphere** — 9-module cognitive engine. Handles emotion, relationships, world awareness, personality, knowledge, and context recall. ~3ms average per turn, ~2.1 MB RAM per NPC.

**ML Swarm** — 12 specialized micro-models replacing what used to require a 0.6B parameter language model. Two layers:
- **Player-facing models** (7): IntentClassifier, SentimentAnalyzer, SwarmEmbedder, BehaviorPredictor, LootBalancer, DialogueRanker, EmotionDetector
- **World simulation models** (5): DemandPredictor, RouteRiskScorer, RumorPropagation, TopicClassifier, EmotionPredictor
- Total footprint: ~458 KB. Total inference: under 1ms. Zero GPU required.

The key insight: a system that runs 90% on pattern matching needs dramatically less compute, making it viable for real-time gaming hardware.

---

## Architecture

### System Diagram

```
Player Input
    │
    ├── ML SWARM PREPROCESSING (<1ms)
    │   ├── IntentClassifier     → intent category + confidence
    │   ├── SentimentAnalyzer    → sentiment + confidence
    │   ├── EmotionDetector      → player emotion + intensity
    │   └── BehaviorPredictor    → next action, engagement, escalation risk
    │
    ▼
COGNITIVE ENGINE (Right Hemisphere)
    Modules:
      1. Conversation Tracker
      2. Emotion State Machine    ← ML player emotion feeds in
      3. Response Compositor
      4. Relationship Tracker
      5. World State Reactor
      6. Escalation Gate          ← ML escalation risk boosts signal
      7. Personality Bank
      8. Knowledge Graph
      9. Context Recall

    Pattern Matcher (Left Hemisphere)
      Token matching + SemanticMatcher (SwarmEmbedder + FAISS)
      MATCH_QUALITY_THRESHOLD = 0.55

    4-Module Fallback Cascade:
      Knowledge Graph → Knowledge Cloud → Personality Bank → Context Recall
      If ALL miss → generic fallback text
```

### Processing Pipeline

1. **ML Swarm Preprocessing** — IntentClassifier, SentimentAnalyzer, EmotionDetector, and BehaviorPredictor classify the incoming query before the cognitive engine processes it. Results passed as `ml_context`.
2. **Conversation Tracker** — Extracts keywords, detects topic, tracks turn count, resolves pronouns, identifies named entities
3. **Emotion State Machine** — Transitions NPC emotion based on player keywords AND ML-detected player emotion (neutral → friendly → grateful, or neutral → suspicious → angry, etc.)
4. **Relationship Tracker** — Tracks trust, fondness, respect, debt per player. Persistent across sessions. Relationship tiers gate NPC behavior
5. **World State Reactor** — Checks global flags (TOWN_UNDER_ATTACK, TIME_OF_DAY, PLAYER_REPUTATION). Can override greetings, disable patterns, override emotions
6. **Context Recall Priority Check** — If player explicitly references prior NPC statements, recall gets FIRST shot before pattern matching
7. **Pattern Matching (Left Hemisphere)** — Hybrid scoring: exact match (1.0) → full-trigger substring → token overlap with geometric mean → semantic similarity via SwarmEmbedder + FAISS. Generic patterns penalized 0.7x. Threshold: 0.55
8. **Escalation Gate** — Evaluates whether to escalate based on match confidence, keywords, conversation depth, emotion intensity, AND ML Swarm escalation risk score
72. **4-Module Fallback Cascade** (if pattern match fails): Knowledge Graph → Knowledge Cloud → Personality Bank → Context Recall
73. If ALL modules miss → generic fallback text

---

## Module Reference

### Module 1: Conversation Tracker
- **File:** `cognitive/conversation_tracker.py` (11,727 bytes)
- **Cost:** ~0.3ms per query
- **Purpose:** Multi-turn context tracking with entity recognition and pronoun resolution
- Extracts keywords from player input
- Detects active topic (shopping, quest, greeting, backstory, etc.)
- Tracks turn count per player
- Resolves pronouns to previously mentioned entities
- Recognizes named entities from the character's knowledge graph

### Module 2: Emotion State Machine
- **File:** `cognitive/emotion_state_machine.py` (10,462 bytes)
- **Cost:** ~0.1ms per query
- **Purpose:** FSM-based emotional reactions with per-player state
- Emotion states: NEUTRAL, FRIENDLY, SUSPICIOUS, ANGRY, AFRAID, SAD, HAPPY, EXCITED, GRATEFUL
- Transitions based on player keyword signals
- ML Swarm integration: EmotionDetector feeds player emotion into NPC reaction (anger/disgust → SUSPICIOUS, fear → CONCERNED)
- Each player has independent emotional context
- Intensity tracking (how strongly the NPC feels)
- World state can force-override emotion

### Module 3: Response Compositor
- **File:** `cognitive/response_compositor.py` (8,501 bytes)
- **Cost:** ~0.2ms per query
- **Purpose:** Assembles varied, context-aware responses
- Takes matched pattern + full context (emotion, relationship, world state)
- Applies emotion-colored variations
- Prevents repetitive responses
- Handles template variable substitution

### Module 4: Relationship Tracker
- **File:** `cognitive/relationship_tracker.py` (10,363 bytes)
- **Cost:** ~0.1ms per query
- **Purpose:** Persistent relationship modeling per player
- Tracked dimensions:
  - Trust (0-100): Does the NPC trust this player?
  - Fondness (0-100): Does the NPC like this player?
  - Respect (0-100): Does the NPC respect this player?
  - Debt (-100 to 100): Does the NPC owe or is owed?
  - Interactions: Total conversation count
  - Tiers: stranger, acquaintance, friend, trusted_ally (computed from scores)
- Persists to JSON file for cross-session continuity

### Module 5: World State Reactor
- **File:** `cognitive/world_state_reactor.py` (5,678 bytes)
- **Cost:** ~0.05ms per query
- **Purpose:** Global world flag awareness
- Checks world state flags set via API
- Can override NPC greetings
- Can disable specific patterns (e.g., no shopping during siege)
- Can force emotion overrides
- Default reactions:
  - TOWN_UNDER_ATTACK → AFRAID + greeting override
  - TIME_OF_DAY = night → Shop closed greeting
  - PLAYER_REPUTATION = criminal → SUSPICIOUS emotion

### Module 6: Escalation Gate
- **File:** `cognitive/escalation_gate.py` (6,655 bytes)
- **Cost:** ~0.1ms per query
- **Purpose:** Smart routing decisions
- Evaluates escalation signals:
  - Low match confidence
  - Complex keywords (multi-step queries)
  - Deep conversation (many turns)
  - High emotion intensity
  - Unknown/novel query patterns
  - ML Swarm escalation risk score (BehaviorPredictor)

### Module 7: Personality Bank
- **File:** `cognitive/personality_bank.py` (21,005 bytes)
- **Cost:** ~0.2ms per query
- **Purpose:** Pre-authored creative responses for off-script questions
- Intent categories: song, joke, favorite, opinion, personal, philosophical, compliment_response, insult_response, creative_request, rumor, advice
- Loading priority:
  1. Character-specific personality.json file
  2. Custom bank passed via constructor
  3. Built-in archetype bank (guard, innkeeper, scholar, healer)
  4. Guard bank as ultimate fallback

### Module 8: Knowledge Graph
- **File:** `cognitive/knowledge_graph.py` (9,960 bytes)
- **Cost:** ~0.1ms per query, ~20 KB RAM per NPC
- **Purpose:** Structured entity knowledge with trust-gated secrets
- Entity types: person, place, item, faction, event, concept
- Knowledge depth levels: intimate, familiar, acquainted, rumor, unknown
- Features:
  - Emotion-variant descriptions
  - Trust-gated secrets (revealed only at high trust threshold)
  - Alias index for fast entity matching
  - Related entities for multi-hop queries
  - Confidence calibrated to knowledge depth (intimate=0.95, rumor=0.60)

### Module 9: Context Recall
- **Purpose:** NPC references its own prior statements
- Detects recall queries
- Gets priority processing BEFORE pattern matching
- Tracks NPC responses per player
- Prevents self-referential loops

### Module 12: Knowledge Cloud
- **File:** `core/knowledge_cloud.py` (23,209 bytes)
- **Cost:** <2ms per query (1000+ entries)
- **Purpose:** Shared world-level lore repository (creatures, locations, events)
- **Architecture**: FAISS IndexFlatIP + SwarmEmbedder (TF-IDF + SVD)
- **Agentic Intent**: Maps player intents (e.g. `shop_buy`) to NPC actions (e.g. `open_shop`)
- **Synthesis Engine**: Blends lore facts with character voice via Markov-based PatternEngine
- **Relational Bridge**: Connects multiple hits (e.g. Duke + City) into a single reasoning response
- **Scalability**: Zero GPU, 50KB total footprint, sub-millisecond search

---

## Character Genome Specification

Every NPC character is defined by a directory under `characters/{character_id}/` containing up to 4 JSON files:

### 1. bio.json (Required)
Character identity and metadata. Fields: character_id, display_name, type, status, description, persona (tone, style, voice_profile, tts_voice), knowledge_domains, name.

### 2. patterns.json (Optional)
Dialogue patterns for the left hemisphere. Contains synthetic_patterns (full confidence), generic_patterns (0.7x penalty), and fallback text.
Each pattern has: id, trigger (array of strings), response_template, confidence (0-1).

### 3. knowledge.json (Optional)
Entity knowledge graph. Each entity has: entity_type, display_name, depth, description, relationship_to_npc, emotion_variants, related_entities, aliases, topics, secret_description, trust_threshold.

### 4. personality.json (Optional)
Pre-authored creative responses by intent category (song, joke, favorite, opinion, personal, philosophical, etc.) with emotion variants.

---

## Phase 1 Refactoring: Decouple from Garen — COMPLETE

### Problem
The original Cognitive Engine v1 had Garen's character data hardcoded directly into the Python modules, making it impossible to use the engine with any other character.

### Solution
Phase 1 extracted all character-specific data into external JSON configuration files and made every module load from the character directory.

### Files Modified
- `cognitive/cognitive_engine.py` — Added char_dir param. _extract_known_entities() now derives from KG. _load_knowledge() loads from knowledge.json. PersonalityBank loads from personality.json.
- `cognitive/knowledge_graph.py` — Removed build_garen_knowledge(). Added load_knowledge_from_file(), load_knowledge_from_dict(), KnowledgeGraph.get_known_entities().
- `cognitive/personality_bank.py` — Added load_personality_from_file(). Added scholar + healer built-in archetypes. PersonalityBank accepts personality_file param.
- `cognitive/__init__.py` — Updated exports for new functions.
- `api/fastapi_server.py` — Passes char_dir to CognitiveEngine constructor.

### New Files Created
- `characters/garen/knowledge.json` — 16 entities extracted from hardcoded data
- `characters/garen/personality.json` — 11 intent categories with emotion variants

### Loading Priority System
- Knowledge: file → inline bio dict → empty
- Personality: file → custom bank → built-in archetype → guard fallback
- Entities: KG entities → NPC name → pattern proper nouns

### Test Results
- Character Conversation Test: 46/46 (100%)

### Load Distribution
- Pattern Match (Left Hemisphere): 59%
- Personality Bank: 26%
- Knowledge Graph: 10%
- Context Recall: 5%
- Escalated: 0%
- Fallback: 0%

### Performance
- Average latency per turn: 3.0ms
- RAM per NPC: ~2.1 MB
- GPU required: None

---

## API Reference

### Production Server
**Server:** `uvicorn api.production_server:app --host 0.0.0.0 --port 5000`

#### Endpoints
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/query` | Main query endpoint (ML → Cognitive → RAG → Fallback) |
| POST | `/api/v1/chat` | Multi-turn conversation |
| GET | `/api/v1/characters` | List available characters |
| GET | `/api/v1/characters/{id}` | Character details |
| GET | `/api/v1/health` | System health + ML Swarm status |
| GET | `/api/v1/stats` | Detailed system statistics |
| GET | `/` | Dashboard UI |

#### POST /api/v1/query
Accepts: query, character, mode (auto|cognitive|rag|pattern), session_id, player_id, include_sources, include_debug.
Returns: response, confidence, character, source, session_id, latency_ms, emotion, relationship, debug (includes ml_swarm context).

### Character Studio
**Server:** `uvicorn studio.character_studio:app --host 0.0.0.0 --port 8500`

---

## Existing Characters

- **Garen Ironfoot** (FULLY BUILT) — Merchant NPC, Guild Master. 37 synthetic + 2 generic patterns, 16 KG entities, 11 personality intents
- **Haven** (FULLY BUILT) — Wellness companion. 23 patterns, 12 KG entities, 11 personality intents
- **Lexis** (FULLY BUILT) — Technical assistant. 28 patterns, 14 KG entities, 11 personality intents
- **Synth** (FULLY BUILT) — Brand ambassador. 28 patterns, 14 KG entities, 11 personality intents
- **Synthesus** (FULLY BUILT) — Platform AI NPC "The How". 48 patterns, 14 KG entities, 11 personality intents
- **Computress** (FULLY BUILT) — Platform AI NPC "The Why". 48 patterns, 14 KG entities, 11 personality intents

---

## Build Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Decouple from Garen | ✅ COMPLETE | Extract all character data to JSON configs |
| 2. Character Data Spec | ✅ COMPLETE | JSON schemas + validator |
| 3. Second Character (Haven) | ✅ COMPLETE | Full character genome |
| 4. Cross-Character Test Harness | ✅ COMPLETE | 497 auto-generated tests |
| 5. Negotiation State Machine | ✅ COMPLETE | Shopping flow + haggle patterns |
| 6. Intent Classifier | ✅ COMPLETE | ML Swarm Module 1 (sklearn) |
| 7. Sentiment Analyzer | ✅ COMPLETE | ML Swarm Module 2 (sklearn) |
| 8. Character Factory | ✅ COMPLETE | Zero-LLM auto-generation |
| 9. Push to GitHub | ✅ COMPLETE | Tagged release |
| 10. Full Character Genomes | ✅ COMPLETE | Lexis & Synth fully built |
| 11. World Systems | ✅ COMPLETE | Economy, quests, weather, scheduling, ML Swarm 3-7 |
| 12. Semantic Matcher | ✅ COMPLETE | SwarmEmbedder + FAISS hybrid matching |
| 13. Social Fabric | ✅ COMPLETE | Multi-NPC interaction system |
| 14. State Persistence | ✅ COMPLETE | Save/load system |
| 15. C++ Kernel Bridge | ✅ COMPLETE | pybind11 + IPC + Python fallback |
| 16. Character Studio | ✅ COMPLETE | Web UI for character creation |
| 17. Game Engine SDK | ✅ COMPLETE | Python + Unity + Unreal |
| 18. Benchmark Suite | ✅ COMPLETE | 7 benchmarks + demo reel |
| 19. Platform NPCs | ✅ COMPLETE | Synthesus + Computress |
| 20. ML Swarm Wiring | ✅ COMPLETE | All 12 models wired into production pipeline |

---

## Git History

| Commit | Description |
|--------|-------------|
| `51acc85` | feat: Cognitive Engine v1 (25 files, 7,809 lines) |
| `d47a49a` | refactor: Decouple cognitive engine from Garen |
| `9ad4356` | feat: Character Genome Spec v2 — JSON schemas + validator |
| `41895c1` | feat: Build Haven — full character genome |
| `4664258` | feat: Phases 4-8 — test harness, ML swarm, factory |
| `80d8136` | feat: Full genomes for Lexis & Synth — 907 tests |
| `df7b87d` | feat: Phase 11 — World Systems |
| `689dea7` | feat: Phase 12 — Semantic Embedding Matcher |
| `474534f` | feat: Phases 13-14 — Social Fabric + State Persistence |
| `00db73b` | feat: Phase 15 — C++ Kernel Bridge |
| `4c33883` | feat: Phase 16 — Character Studio Web UI |
| `c3c8257` | feat: Phase 17 — Game Engine SDK |
| `1776f4d` | feat: Phase 18 — Benchmark Suite + Demo Reel |
| `00232a4` | feat: Phase 19 — Platform AI NPCs |
| **Tag: v2.0.0-alpha** | Full dual-hemisphere release |

---

## ML Swarm Architecture (Built)

The ML Swarm replaces what used to require a 0.6B parameter language model. Instead of one big model, we use 12 specialized micro-models. Total footprint: ~458 KB. Total inference: under 1ms. That's shippable on a PS5 or mid-tier gaming PC.

### Player-Facing Models (ml/)

| # | Model | File | Purpose | Size | Latency |
|---|-------|------|---------|------|---------|
| 1 | SwarmEmbedder | `ml/swarm_embedder.py` | TF-IDF + SVD text embeddings for FAISS semantic search | ~128 KB | <1ms |
| 2 | IntentClassifier | `ml/intent_classifier.py` | Classify player intent (14 categories) | ~50 KB | <1ms |
| 3 | SentimentAnalyzer | `ml/sentiment_analyzer.py` | Detect emotional valence (6 categories) | ~40 KB | <0.5ms |
| 4 | BehaviorPredictor | `ml/behavior_predictor.py` | Predict player next action, engagement, escalation risk | ~30 KB | <0.3ms |
| 5 | LootBalancer | `ml/loot_balancer.py` | Fair reward/pricing distribution for merchants | ~25 KB | <0.3ms |
| 6 | DialogueRanker | `ml/dialogue_ranker.py` | Rank candidate NPC responses by quality | ~30 KB | <0.3ms |
| 7 | EmotionDetector | `ml/emotion_detector.py` | Classify player emotional state (8 categories) | ~35 KB | <0.3ms |

### World Simulation Models (world/ml_swarm.py)

| # | Model | Purpose | Size | Latency |
|---|-------|---------|------|---------|
| 8 | DemandPredictor | Forecast supply/demand trends for economy | ~30 KB | <0.5ms |
| 9 | RouteRiskScorer | Score trade route danger levels | ~25 KB | <0.3ms |
| 10 | RumorPropagation | Predict gossip spread/distort/fade | ~35 KB | <0.4ms |
| 11 | TopicClassifier | Classify world events by topic | ~40 KB | <0.3ms |
| 12 | EmotionPredictor | Predict NPC emotional reaction to events | ~35 KB | <0.4ms |

**All models:** sklearn LogisticRegression/TF-IDF pipelines. Zero GPU. Zero PyTorch. Zero cloud dependencies.

### Production Pipeline Integration

```
startup():
  IntentClassifier.train()        → ready
  SentimentAnalyzer.train()       → ready
  EmotionDetector()               → ready
  BehaviorPredictor()             → ready
  LootBalancer()                  → ready
  DialogueRanker()                → ready

query(text):
  intent, conf     = IntentClassifier.predict(text)
  sentiment, conf  = SentimentAnalyzer.predict(text)
  emotion          = EmotionDetector.detect(text)
  behavior         = BehaviorPredictor.predict(features)
  ml_context       = {intent, sentiment, emotion, behavior}
  result           = CognitiveEngine.process_query(query, ml_context=ml_context)
```

### Dependencies
```toml
# RAG / Embeddings (SwarmEmbedder: TF-IDF + SVD, no PyTorch needed)
"faiss-cpu>=1.8.0"
"numpy>=1.26.0"
"scikit-learn>=1.4.0"
"scipy>=1.12.0"

# No sentence-transformers. No torch. No openai. No anthropic.
```

---

## Phase 4: Cross-Character Test Harness — COMPLETE

**File:** `tests/test_cross_character.py` + `tests/conftest.py`
**Result:** 497/497 tests passing

### Architecture
The test harness auto-discovers all characters from the `characters/` directory and generates tests from their genome files. No test code changes needed when adding new characters — the harness adapts automatically.

### Test Categories
1. **Pattern Matching** — Every trigger in patterns.json produces a match with confidence >= 0.55
2. **Knowledge Graph** — Entity queries return knowledge-sourced answers (cognitive mode)
3. **Personality** — Intent triggers produce personality bank responses
4. **Fallback** — Unknown queries produce graceful in-character fallbacks
5. **Isolation** — Same query to different characters yields unique responses
6. **Latency** — All responses complete within performance budget
7. **Schema Validation** — All genome files match required structure
8. **Cognitive Engine** — Multi-turn context, emotion tracking, relationship tracking

### Key Design Decisions
- `CharacterGenome` class loads all 4 genome files and extracts testable scenarios
- `discover_characters()` scans directories, skips `schema/` folder
- Full characters (bio+patterns+knowledge+personality) get deeper cognitive tests
- Stub characters (bio+patterns only) get pattern and fallback tests

---

## Phase 5: Negotiation State Machine — COMPLETE

**File:** `cognitive/negotiation_engine.py`
**Tests:** `tests/test_negotiation.py` — 29/29 passing

### State Machine
```
IDLE → BROWSING → INQUIRING → NEGOTIATING → DEAL / WALKAWAY
                                    ↕
                              COUNTER_OFFER
                                    ↓
                              FINAL_OFFER → DEAL / WALKAWAY
```

### Features
- **Intent Detection:** Regex-based haggle intent parsing (browse, inquire, buy, sell, haggle, offer, accept, walkaway)
- **Haggle Mechanics:** Max 3 rounds before final offer, insulting offers rejected, counter-offers split the difference
- **Merchant Styles:** fair (default), shrewd (+15% markup), generous (-5%), stubborn (+10% and less flexible)
- **Relationship Pricing:** Trust above 50 gives up to -15% discount, fondness above 60 gives up to -10%
- **Restricted Items:** High-value items require minimum trust level to purchase
- **Session Management:** Per-player sessions with 5-minute timeout

### Cost
~0.3ms per state transition, ~5 KB RAM per active session, zero GPU.

---

## Phase 6: Intent Classifier (ML Swarm Module 1) — COMPLETE

**File:** `ml/intent_classifier.py`
**Tests:** `tests/test_intent_classifier.py` — 22/22 passing

### Architecture
- **Model:** TF-IDF (char_wb ngrams 2-5) → Logistic Regression
- **Training Data:** 120+ universal samples + character-derived data from patterns.json
- **14 Intent Categories:** greeting, farewell, question, shop_browse, shop_buy, shop_haggle, personal, creative, combat, quest, compliment, insult, lore, unknown

### Performance
- Inference: <1ms average
- Model size: ~50 KB (sklearn pickle)

### API
```python
classifier = IntentClassifier()
classifier.train()
intent, confidence = classifier.predict("I want to buy a sword")
# → ("shop_buy", 0.92)

# Enrich with character patterns
from ml.intent_classifier import build_training_data_from_character
extra = build_training_data_from_character(patterns_data, "garen")
classifier.add_training_data(extra)
classifier.train()  # Retrain with enriched data
```

---

## Phase 7: Sentiment Analyzer (ML Swarm Module 2) — COMPLETE

**File:** `ml/sentiment_analyzer.py`
**Tests:** `tests/test_sentiment.py` — 19/19 passing

### Architecture
- **Model:** TF-IDF (char_wb ngrams 2-4) → Logistic Regression
- **6 Sentiment Categories:** positive, negative, neutral, threatening, pleading, flirtatious

### Emotion Mapping
| Sentiment | EmotionStateMachine Trigger |
|-----------|---------------------------|
| positive | friendly |
| negative | angry |
| neutral | neutral |
| threatening | afraid |
| pleading | sad |
| flirtatious | embarrassed |

### Performance
- Inference: <0.5ms average
- Model size: ~40 KB

---

## Phase 8: Character Factory v2 (Zero-LLM) — COMPLETE

**File:** `character_factory_v2.py`
**Tests:** `tests/test_character_factory.py` — 25/25 passing

### Purpose
Auto-generate complete character genomes from a simple spec. No LLM required — uses archetype templates, combinatorial pattern generation, and knowledge graph scaffolding.

### Supported Archetypes
1. **merchant** — shop patterns, trade, pricing
2. **guard** — combat, duty, patrol
3. **innkeeper** — hospitality, rooms, food
4. **scholar** — research, knowledge, teaching
5. **healer** — care, wellness, compassion
6. **blacksmith** — forge, weapons, armor

### Generated Files (per character)
- `bio.json` — Identity, archetype, setting, traits, safety rules
- `patterns.json` — Greeting, identity, domain-specific, farewell patterns
- `knowledge.json` — Self, location, establishment, custom entities
- `personality.json` — All 11 intent categories with archetype-appropriate responses

### CLI Usage
```bash
python character_factory_v2.py --name "Elda Brightwater" --archetype innkeeper \
    --setting medieval_fantasy --traits "warm,gossipy,protective" \
    --location "Goldport"
```

---

## Phase 10: Full Character Genomes — Lexis & Synth — COMPLETE

**Commit:** 80d8136
**Tests:** 907/907 passing (up from 592)

### Lexis — Technical Assistant (hemisphere_id: 30)
- **Archetype:** Scholar
- **Domain:** Technical documentation and troubleshooting
- **Knowledge Graph:** 14 entities (Python, Docker, Git, REST APIs, Kubernetes, CI/CD, SQL, Auth, Testing, Linux, Microservices, Debugging, Networking, Performance)
- **Patterns:** 28 total (25 synthetic + 3 generic)

### Synth — Brand Ambassador (hemisphere_id: 10)
- **Archetype:** Custom (brand ambassador)
- **Domain:** AIVM products, Synthesus architecture, use cases, pricing
- **Knowledge Graph:** 14 entities (Synthesus Engine, AIVM LLC, PPBRS, Character Genome, Cognitive Engine, ML Swarm, NPC Dialogue, Enterprise Chatbots, Licensing, ONNX, Character Factory, Negotiation Engine, Emotion State Machine, Hardware Requirements)
- **Patterns:** 28 total (25 synthetic + 3 generic)

---

## Phase 11: World Systems — COMPLETE

**Commit:** df7b87d
**Tests:** 1017/1017 passing (907 existing + 110 new)

All 5 world systems communicate through the shared WorldStateReactor flag bus. The WorldSimulator coordinator runs them in dependency order each tick:

```
Weather → Economy → NPC Scheduling → Quest Generation → ML Swarm
```

### 11A: Procedural Economy Engine
**File:** `world/economy.py`
- Living supply-demand economy with real-time pricing
- Price = base_price × (1 / supply_demand_ratio^volatility)
- 3 regions, 12 resources, 6 bidirectional trade routes
- Economic events (shortage, surplus, boom, crash, blight, harvest, disruption)

### 11B: Dynamic Quest Generator
**File:** `world/quests.py`
- Quests emerge from world contradictions, not static lists
- "Contradiction Detector" scans world flags for tensions
- 7 quest templates, lifecycle: AVAILABLE → OFFERED → ACTIVE → COMPLETED/FAILED/EXPIRED

### 11C: NPC Scheduling System
**File:** `world/scheduling.py`
- Every NPC has needs: SLEEP, FOOD, SOCIAL, WORK, SAFETY, LEISURE
- 15 activities, world state overrides, urgent need fulfillment

### 11D: ML Swarm Expansion (World Models 8-12)
**File:** `world/ml_swarm.py`
- DemandPredictor, RouteRiskScorer, RumorPropagation, TopicClassifier, EmotionPredictor
- All sklearn LogisticRegression, all <0.5ms, zero GPU
- MLSwarmManager.train_all() trains all 5 models

### 11E: Weather Generation System
**File:** `world/weather.py`
- 17 weather conditions, 8 biomes, 4 seasons
- Markov chain transitions biased by season and narrative tension
- Game Director API for narrative control

### 11F: World Simulator Coordinator
**File:** `world/coordinator.py`
- One clock, one tick, everything talks
- Cross-system effects: weather → economy → quests → NPC behavior
- Graceful degradation: works with any subset of systems

---

## Phase 12: Left Hemisphere v2 — Semantic Matching — COMPLETE

**Commit:** 689dea7
**Tests:** 1061/1061 passing

### Overview
Upgraded the Left Hemisphere pattern matcher from keyword/token overlap to a hybrid token + semantic similarity system using SwarmEmbedder (TF-IDF + SVD) + FAISS.

### Before (v1 — Token Overlap Only)
- 'got any wares?' → 0.0 (no shared keywords)
- 'whats ur name' → 0.0 (no token match)
- NPCs only understood exact/near-exact phrasing

### After (v2 — Hybrid Token + Semantic)
- Token matcher still runs (~0.1ms) for exact/substring matches
- Semantic matcher (SwarmEmbedder + FAISS) runs in parallel (<1ms)
- Takes the BETTER of the two results
- Zero regression on existing behavior

### Results
- 'got any wares for sale?' → 0.700 ✓ (was 0.0)
- 'whats ur name' → 0.676 ✓ (was 0.0)
- 'any rumors around town?' → 0.636 ✓ (was 0.0)
- NPCs now understand paraphrasing, slang, typos, indirect references

### Architecture
**File:** `cognitive/semantic_matcher.py`
- SwarmEmbedder: TF-IDF + Truncated SVD → 128-dim embeddings (~128 KB)
- FAISS IndexFlatIP for sub-millisecond cosine similarity
- Pre-embeds ALL triggers at engine init time
- similarity_floor = 0.35

### Memory & Performance
- Model: ~128 KB (shared across ALL NPC instances)
- FAISS index: ~1.5KB per 100 triggers (negligible)
- Query latency: <3ms total
- Zero GPU required — runs on CPU

### Dependencies
```
scikit-learn>=1.4.0
scipy>=1.12.0
faiss-cpu>=1.8.0
numpy>=1.26.0
```
No sentence-transformers. No torch. No PyTorch.

---

## Phase 13: Multi-NPC Interaction System (Social Fabric) — COMPLETE

**Module 11 | Commit:** 474534f
**Tests:** 1200/1200 passing

**File:** `cognitive/social_fabric.py` (580 lines)

### Features
- NPC-to-NPC relationships with dispositions (-1.0 to 1.0)
- Faction dynamics (allied, neutral, hostile, rival)
- Gossip propagation with truth decay per hop
- Group conversations with roles (INITIATOR, PARTICIPANT, OBSERVER)
- Direct NPC-to-NPC messaging (chat, warning, request, gossip, trade)

### Cost
- Tick: <0.2ms for 100 NPCs
- Memory: ~2KB per NPC profile
- Zero GPU

---

## Phase 14: Memory Persistence / Save-Load — COMPLETE

**Module 12 | Commit:** 474534f
**Tests:** 1200/1200 passing (includes 39 persistence tests)

**File:** `cognitive/state_persistence.py` (670 lines)

### Features
- Full save/load for all NPC cognitive state, social fabric, and world state
- Versioned save directories with JSON files per NPC
- Save 20 NPCs: ~5ms, Load: ~1ms, Size: ~37KB

---

## Phase 15: C++ Kernel Bridge — COMPLETE

**Module 13 | Commit:** 00db73b
**Tests:** 1245/1245 passing

### Files
- `kernel/bridge.py` (516 lines) — Python bridge API + fallback mode
- `kernel/pybind_module.cpp` (181 lines) — pybind11 native module
- `CMakeLists.txt` (152 lines) — Full CMake build system

### Three Operating Modes (auto-detected)
1. **NATIVE** — pybind11 compiled module (fastest, requires C++ build)
2. **IPC** — Subprocess communication (medium speed, cross-process)
3. **FALLBACK** — Pure Python implementation (always available)

### Performance
- Fallback mode: 0.006ms avg per query
- Native mode (estimated): 0.001ms per query
- Throughput: ~170,000+ queries/sec (fallback), ~1M+ (native)

---

## Phase 16: Character Studio Web UI — COMPLETE

**Commit:** 4c33883
**Tests:** 1296/1296 passing

### Files
- `studio/character_studio.py` (401 lines) — FastAPI server (port 8500)
- `studio/studio_ui.html` (530 lines) — Single-page web UI (cosmic theme)

### Features
- Genome editor, personality sliders, pattern management
- Live chat preview with any character
- Export/Import character genomes
- 10 REST endpoints for full CRUD

---

## Phase 17: Game Engine Integration SDK — COMPLETE

**Commit:** c3c8257
**Tests:** 1296/1296 passing

### Files
- `sdk/python/synthesus_sdk.py` (313 lines) — Python SDK
- `sdk/unity/SynthesusClient.cs` (267 lines) — Unity C# SDK
- `sdk/unreal/SynthesusClient.h` + `.cpp` (351 lines) — Unreal C++ SDK

### Python SDK API
- `query()`, `get_character()`, `list_characters()`, `set_world_state()`, `health()`
- `batch_query()` — Parallel queries
- `stream_query()` — Streaming responses

---

## Phase 18: Benchmark Suite + Demo Reel — COMPLETE

**Commit:** 1776f4d
**Tests:** 1343/1343 passing

### Benchmark Results (Intel Xeon 2.60GHz, 2 cores, 8GB RAM, no GPU)

| Metric | Result |
|--------|--------|
| Pattern Matching | 0.006ms avg, 0.011ms p99 |
| Full Cognitive Pipeline | 0.079ms avg, 0.381ms p99 |
| Memory Per NPC | 13.87 KB/NPC |
| NPC Scaling (100 NPCs) | 0.127ms avg |
| Social Fabric Tick (100 NPCs) | 0.201ms avg |
| Save/Load (20 NPCs) | save=5.37ms, load=1.09ms |
| Kernel Bridge (Fallback) | 0.006ms avg |

### Synthesus vs LLM NPC Comparison

| Metric | Synthesus | GPT-4 | LLaMA-7B |
|--------|-----------|-------|----------|
| Latency | <5ms | 500-3000ms | 200-1000ms |
| Memory Per NPC | ~2 MB | N/A (cloud) | ~4000 MB |
| GPU Required | No | Cloud | Yes |
| Cost / 1K Queries | $0.00 | $15-60 | $0.00 |
| Max Concurrent NPCs | 1000+ | Rate limited | 1-4 |
| Deterministic | Yes | No | No |
| Offline Capable | Yes | No | Yes |

---

## Phase 19: Platform AI NPCs — Synthesus + Computress — COMPLETE

**Commit:** 00232a4
**Tests:** 2,004 passing

### Synthesus (Male, Hemisphere ID: 1)
- Role: Primary Platform AI NPC — "The How"
- Persona: Authoritative, technical, precise
- 48 patterns, 14 KG entities, 11 personality intents

### Computress (Female, Hemisphere ID: 2)
- Role: Secondary Platform AI NPC — "The Why"
- Persona: Warm, creative, engaging
- 48 patterns, 14 KG entities, 11 personality intents

### Cross-Reference Architecture
Both characters reference each other in bio and knowledge graph, sharing AIVM knowledge from different explanatory angles.

---

## Complete Test Suite Summary

| Test File | Tests | Description |
|-----------|-------|-------------|
| test_cross_character.py | 497 | Auto-generated from character genomes |
| test_ml_swarm_integration.py | 215 | ML swarm integration |
| test_world_systems.py | 110 | Economy, quests, scheduling, weather, ML swarm |
| test_social_fabric.py | 95 | Multi-NPC interaction, factions, gossip |
| test_platform_npcs.py | 91 | Platform NPC validation |
| test_benchmark_suite.py | 47 | Benchmark + demo reel validation |
| test_kernel_bridge.py | 45 | C++ kernel bridge |
| test_semantic_matcher.py | 44 | Semantic embedding matching |
| test_state_persistence.py | 39 | Save/load system |
| test_character_studio.py | 35 | Character Studio web UI |
| test_negotiation.py | 29 | Shopping state machine |
| test_character_factory.py | 25 | Character auto-generation |
| test_intent_classifier.py | 22 | ML intent classification |
| test_sdk.py | 21 | Game engine SDK |
| test_sentiment.py | 19 | ML sentiment analysis |
| **TOTAL** | **1,343+** | **All passing (100%)** |

---

## Module Count: 13

1. ConversationTracker
2. EmotionStateMachine
3. ResponseCompositor
4. RelationshipTracker
5. WorldStateReactor
6. EscalationGate
7. PersonalityBank
8. KnowledgeGraph
9. ContextRecall
10. SemanticMatcher
11. SocialFabric (Multi-NPC Interaction)
12. StatePersistence (Save/Load)
13. KernelBridge (C++ Acceleration)

**Plus:** ML Swarm (12 micro-models), Character Studio (Web UI), Game Engine SDK (Python/Unity/Unreal), Benchmark Suite, Demo Reel

---

## Agentic Capabilities Analysis

### Current Agentic Capabilities

| Capability | Score | Description |
|-----------|-------|-------------|
| Autonomous Emotional State | 7/10 | EmotionStateMachine tracks state across interactions, ML Swarm EmotionDetector feeds player emotion |
| Relationship Tracking & Memory | 8/10 | Persistent trust/fondness/respect, cross-session continuity |
| Autonomous Social Behavior | 9/10 | NPC-to-NPC relationships, gossip propagation, faction dynamics |
| World State Reactivity | 7/10 | Weather, economy, scheduling drive NPC behavior |
| Escalation & Boundary Awareness | 6/10 | Autonomous decision-making on when to escalate, ML risk scoring |

**Current State: 7.4/10**

### Enhancement Roadmap

1. **Goal-Directed Behavior** (HIGH IMPACT) — GoalStack module for autonomous objectives. +2 points.
2. **Autonomous Tool Use** (HIGH IMPACT) — ActionRouter for triggering external systems. Transforms NPCs from conversational to operational agents.
3. **Proactive Initiation** (MEDIUM IMPACT) — ProactiveEngine for time/event/relationship-based conversation initiation. +1.5 points.
4. **Multi-Step Reasoning** (MEDIUM IMPACT) — ReasoningChain module for planned multi-step explanations. +1 point.
5. **Self-Improvement Signals** (LOW IMPACT, HIGH VALUE) — Pattern gap detection, improvement logging. Creates continuous feedback loop.

**With All Enhancements: 9.2/10**

Key Insight: The current architecture is already designed for agentic behavior — the 13 cognitive modules, relationship tracking, social fabric, and world state reactivity ARE agentic systems. The upgrade path is additive, not architectural. The foundation supports it.
