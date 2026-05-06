# Core Orchestrator

> Synthesus 3.0 — Top-level runtime and system orchestration

---

## Overview

The core orchestrator (`SynthRuntime`) wires together all subsystems into a single, clean public API. It manages characters, inference, multi-layer memory, and pattern discovery — serving as the primary entry point for applications using Synthesus.

**Key files:**

| File | Responsibility |
|------|-----------------|
| `core/synth_runtime.py` | `SynthRuntime` — top-level runtime, character management, inference |
| `core/reasoning_core.py` | `ReasoningCore` — multi-step reasoning pipeline |
| `core/reasoning/planner.py` | `Planner` — decomposes complex tasks into sub-tasks |
| `core/reasoning/domain_router.py` | `DomainRouter` — routes sub-tasks to specialized handlers |
| `core/reasoning/verifier.py` | `Verifier` — validates reasoning results against constraints |
| `core/reasoning/synthesizer.py` | `Synthesizer` — merges multi-entity results into final response |
| `core/hemisphere_bridge.py` | `HemisphereBridge` — dual-hemisphere orchestration |
| `core/pattern_engine.py` | `PatternEngine` — pattern discovery and management |
| `core/els_bridge.py` | `ELSBridge` — interaction logging and candidate pattern integration |
| `core/memory_store.py` | `MemoryStore` — layered memory (episodic/semantic/procedural/working) |
| `core/cognitive_core.py` | `CognitiveCore` — right-hemisphere deductive/inductive/abductive reasoning |
| `api/game_bridge.py` | `GameBridge` — Synthesus <-> Neon Bay 2087 KPC bridge (POST /think) |

---

## SynthRuntime

### Initialization

```python
from core.synth_runtime import SynthRuntime

runtime = SynthRuntime(
    characters_dir="characters",
    data_dir="data",
    left_model="left",
    right_model="right",
)
```

### Character Management

```python
# Create a character
result = runtime.create_character(
    character_id="synth",
    name="Synth",
    archetype="reasoning",
    traits=["analytical", "helpful", "creative"],
    backstory="Synthesus is a synthetic reasoning engine...",
)

# Load existing character
char = runtime.load_character("synth")
# {'character_id': 'synth', 'path': '...', 'bio': {...}, 'manifest': {...}}

# List all characters
characters = runtime.list_characters()  # ['synth', 'gorn', 'aldric']
```

### Inference

```python
result = runtime.respond(
    character_id="synth",
    user_input="Hello, what can you do?",
    context="User is new to the system.",
    session_id="session-001",
)

# ReasoningResult fields:
print(result.final_response)     # Synthesized output
print(result.session_id)         # Session ID
print(result.total_latency_ms)    # Total processing time (ms)
print(result.success)             # True/False

# Steps in the pipeline:
for step in result.steps:
    print(f"[{step.step_type}] {step.output_text[:100]}... ({step.latency_ms}ms)")
```

### Memory Operations

SynthRuntime exposes four memory layers, each with `remember_*` and `recall_*` helpers:

```python
# Store memories (auto-detects layer from memory_type)
runtime.remember(character_id="synth", content="User prefers short answers.", memory_type="semantic")
runtime.remember_episodic(character_id="synth", content="User asked about reasoning at 3pm.")
runtime.remember_procedural(character_id="synth", content="How to restart the kernel.")
runtime.remember_working(character_id="synth", content="Currently processing query X.")

# Recall memories
memories = runtime.recall(character_id="synth", query="preferences", top_k=5)
episodic = runtime.recall_episodic(character_id="synth", query="session", top_k=3)
semantic = runtime.recall_semantic(character_id="synth", query="reasoning", top_k=5)
procedural = runtime.recall_procedural(character_id="synth", query="kernel", top_k=3)
working = runtime.recall_working(character_id="synth", query="processing", top_k=3)
```

### Pattern Management

```python
# Add a pattern
runtime.add_pattern(
    character_id="synth",
    trigger="what is your name",
    response_template="I am Synthesus, a synthetic reasoning engine.",
    pattern_type="response",
    weight=1.0,
)

# Review and approve ELS candidate patterns
approved_count = runtime.review_candidates(
    character_id="synth",
    approve_all=False,  # Only approve if score > 0.6
)
```

### Statistics

```python
stats = runtime.stats("synth")
# {'character_id': 'synth', 'pattern_stats': {...}, 'els_stats': {...}, 'memory': {...}}
```

---

## Memory Store

The `MemoryStore` handles four distinct memory layers:

| Layer | Purpose | TTL | Typical use |
|-------|---------|-----|-------------|
| **Episodic** | Event history, interaction traces | Long | "What happened in the last session?" |
| **Semantic** | Durable facts and learned knowledge | Permanent | "What does the character know about X?" |
| **Procedural** | Reusable behavior rules and recipes | Long | "How does the character typically respond?" |
| **Working** | Volatile task scratch state | Short | "What is the character currently processing?" |

---

## Pattern Engine

The `PatternEngine` discovers, scores, and manages learned reasoning patterns. Patterns are discovered from interaction history and scored by success rate. The left hemisphere uses them to generate fast, contextually appropriate responses.

```python
from core.pattern_engine import PatternEngine, Pattern, PatternMatch

pe = PatternEngine(db_path="data/patterns.db")

# Match patterns
matches = pe.match(character_id="synth", query="Tell me about dragons", top_k=3)

# Discover from new interaction
pe.discover(
    character_id="synth",
    interaction_text="User asked about dragons. Character explained fire-breathing.",
    outcome_success=True,
)
```

---

## ELS Bridge

The `ELSBridge` (Experience Learning System) captures interactions and identifies candidate patterns for the pattern engine.

```python
from core.els_bridge import ELSBridge

els = ELSBridge(
    db_path="data/interactions.db",
    patterns_path="data/candidate_patterns.json",
)

# Capture an interaction
els.capture(
    character_id="synth",
    user_input="What is the capital of France?",
    character_response="Paris is the capital of France.",
    outcome_success=True,
)

# Get candidate patterns
candidates = els.get_candidates(character_id="synth", status="pending")

# Integrate approved patterns
els.integrate_patterns(character_id="synth", approved=candidates[:5])
```

---

## CognitiveCore (Right Hemisphere)

Handles three reasoning modes:

```python
from core.cognitive_core import CognitiveCore

cog = CognitiveCore()

# Classify which reasoning mode a query requires
intent = cog.classify_intent("Why did the dragon attack the castle?")
# {'primary': 'abductive', 'secondary': [], 'scores': {'abductive': 3, 'deductive': 0, 'inductive': 0}}

intent = cog.classify_intent("Given that all metals conduct electricity, and gold is a metal, what follows?")
# {'primary': 'deductive', 'secondary': [], 'scores': {'deductive': 2, ...}}
```

---

## Module-Level Singleton

```python
from core.synth_runtime import get_runtime

runtime = get_runtime()  # Returns or creates the global instance
```

---

## Default Directory Structure

```
.
├── characters/           # Per-character data (bio.json, manifest.json)
├── data/
│   ├── patterns.db       # SQLite: discovered patterns
│   ├── interactions.db   # SQLite: interaction history
│   ├── memory.db          # SQLite: layered memory store
│   └── candidate_patterns.json  # ELS candidate patterns
```

---

## Configuration Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `characters_dir` | `"characters"` | Directory for character data |
| `data_dir` | `"data"` | Directory for runtime data |
| `left_model` | `"left"` | Left hemisphere model name |
| `right_model` | `"right"` | Right hemisphere model name |
| `top_k_patterns` | `3` | Patterns recalled per query |
| `kernel_bin` | `./build/zo_kernel` | C++ kernel binary path |
| `kernel_timeout` | `2.0` | Kernel query timeout (seconds) |
| `agreement_threshold` | `0.65` | Hemisphere agreement threshold |

---

## Reasoning Layer (v4)

The Reasoning Layer provides advanced logic for complex, multi-entity queries.

### Components

1. **Planner** — Uses a task-based model to break down user input.
2. **Decomposer** — Analyzes dependencies between sub-tasks.
3. **Domain Router** — Directs tasks to Knowledge Cloud, Pattern Engine, or ML organs.
4. **Verifier** — Checks for logical consistency and safety guardrails.
5. **Synthesizer** — Consolidates findings into a coherent narrative.

### ML Organs (Triad + Shared)

The reasoning pipeline is augmented by specialized ML organs that handle specific cognitive sub-tasks:

| Organ | Purpose | Path |
|-------|---------|------|
| **Chat** | Policy Prior, Risk, Attention | `organs/chat/` |
| **GM** | Narrative Guidance, Risk, Attention | `organs/gm/` |
| **SysOps** | Infrastructure Monitoring, Risk, Attention | `organs/sysops/` |
| **Prediction** | Heuristic/learned forecasting | `organs/shared/PredictionOrgan.ts` |
| **Relation** | Entity relationship extraction | `organs/shared/RelationOrgan.ts` |
| **Memory** | Efficient memory indexing/retrieval | `organs/shared/MemoryOrgan.ts` |

```python
from core.reasoning_core import ReasoningCore

rc = ReasoningCore()
result = rc.reason("Explain the relationship between House Aldric and the Scorched Plains.")
# Returns a structured Result with steps, proof traces, and synthesis.
```

---