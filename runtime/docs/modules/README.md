# Synthesus 3.0 — Module Documentation

## Modules

| Module | Description |
|--------|-------------|
| [KN.md](KN.md) | Knowledge Node system — hybrid KNDatabase + FAISS vector index |
| [PPBRS.md](PPBRS.md) | Procedural Pattern-Based Reasoning System — symbolic core |
| [DUAL_HEMISPHERE.md](DUAL_HEMISPHERE.md) | Left/Right hemisphere processing architecture |
| [AIVM.md](AIVM.md) | Amplification Intelligence Virtual Machine — self-improvement layer |

## Core System

| Component | File | Purpose |
|-----------|------|---------|
| Pattern Engine | `core/pattern_engine.py` | Discovers, scores, and retrieves reasoning patterns |
| Hemisphere Bridge | `core/hemisphere_bridge.py` | Orchestrates dual-hemisphere processing |
| Synthesus Master | `core/synthesus_master.py` | Main orchestrator for full reasoning pipeline |
| Cognitive Core | `core/cognitive_core.py` | Right hemisphere cognitive module coordinator |
| Conscious State | `core/conscious_state.py` | Narrative timeline and belief tracking |
| Reasoning Core | `core/reasoning_core.py` | Multi-step reasoning chain orchestration |
| Knowledge Cloud | `core/knowledge_cloud.py` | Shared world lore with semantic search |
| RAG Pipeline | `core/rag_pipeline.py` | Retrieval-Augmented Generation pipeline |
| Amplification Bridge | `core/amplification_bridge.py` | Integration with AIVM amplification layer |

## API Layer

| File | Purpose |
|------|---------|
| `api/schemas.py` | Pydantic request/response models |
| `api/fastapi_server.py` | FastAPI production server |
| `api/production_server.py` | Multi-client production server |
| `api/gateway.py` | API gateway with rate limiting |
| `api/database.py` | SQLAlchemy models for API keys and metrics |
| `api/parameter_cloud.py` | Shared parameter synchronization |
| `api/security_middleware.py` | Authentication and rate limiting |

## Cognitive Modules

Located in `cognitive/`:

| Module | Purpose |
|--------|---------|
| `emotion_state_machine.py` | 10-state emotional model with transitions |
| `conversation_tracker.py` | Turn-by-turn context memory |
| `relationship_tracker.py` | Per-player trust, rapport, history |
| `world_state_reactor.py` | Game event, weather, time awareness |
| `knowledge_graph.py` | Structured domain knowledge per character |
| `personality_bank.py` | Character voice and trait soft-prompts |
| `context_recall.py` | Episodic and semantic memory retrieval |
| `response_compositor.py` | Multi-signal response building |
| `escalation_gate.py` | Route complex queries to deeper processing |
| `semantic_matcher.py` | Semantic similarity matching |
| `dialogue_memory.py` | Dialogue history management |
| `social_fabric.py` | NPC-to-NPC gossip and faction dynamics |
| `evolution_engine.py` | Character self-improvement from feedback |
| `proactive_engine.py` | Anticipatory behavior generation |
| `negotiation_engine.py` | Negotiation and conflict resolution |
| `pattern_engine.py` | Pattern discovery and matching |
| `transition_learner.py` | Learning emotional transition models |
| `goal_stack.py` | Hierarchical goal management |
| `agent_dispatcher.py` | Routing to specialized agents |
| `slot_filler.py` | Argument extraction and slot filling |
| `character_voice.py` | Character voice and style enforcement |
| `state_persistence.py` | Save/restore cognitive state |

## PPBRS Modules

Located in `ppbrs/`:

| Module | Purpose |
|--------|---------|
| `pattern_extractor.py` | Extract patterns from interaction logs |
| `pattern_classifier.py` | Classify patterns by type and domain |
| `confidence_scoring.py` | Score pattern match confidence |
| `reasoning_chain.py` | Build multi-step reasoning chains |
| `multi_step_reasoning.py` | Coordinate multi-step reasoning |
| `rule_to_action.py` | Convert reasoning rules to actions |

## UNPC Engine

Located in `unpc_engine/`:

| Component | Purpose |
|-----------|---------|
| `genome_expander.py` | Archetype genome system for NPC generation |
| `pattern_generator.py` | Procedural pattern generation for characters |

## Knowledge Integration

Located in `knowledge_integration/`:

| File | Purpose |
|------|---------|
| `kaggle_loader.py` | Download and parse external datasets |
| `kn_populator.py` | Populate KNDatabase from datasets |
| `faiss_indexer.py` | Build and query FAISS index |
| `cloud_sync.py` | Cloud artifact synchronization |
| `run_population.py` | Main entry point for knowledge population |

## ML Organs

Located in `organs/` and `amplification/`:

| Organ | Input | Output | Notes |
|------|-------|--------|------|
| `PolicyPrior` | state + actions | action scores | Domain-triad learned head |
| `RiskOutcome` | trajectory features | risk / quality | Domain-triad learned head |
| `Attention` | multi-focus features | attention weights | Domain-triad learned head |
| `Prediction` | state features | prediction score / direction | Shared/default runtime organ |
| `Forecast` | trajectory features | trend / horizon | Shared/default runtime organ |
| `SequencePrediction` | state + trajectory features | continuity / churn | Shared/default runtime organ |
| `Relation` | state features | trust / rapport / conflict | Shared/default runtime organ |
| `Memory` | state features | recall / salience | Shared/default runtime organ |
| `AnomalyEvent` | state features | anomaly flags / event types | Shared/default runtime organ |
| `Summarizer` | state features | structured summary | Shared/default runtime organ |

### Organ architecture note
- The recommended default is a **shared backbone + small organ heads** architecture.
- Not every organ should own a full neural network.
- Use full learned heads for the highest-value paths, and keep heuristic fallbacks for low-data or low-value organs.
- The shared/default organs are meant to widen the amplification plane without destabilizing the GM/SysOps/Chat triad.
