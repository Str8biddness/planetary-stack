# AIOS Memory Model

Synthesus now treats memory as a layered system instead of a single blob of conversation history. The goal is to keep the runtime fast, inspectable, restartable, and durable across sessions.

## Layers

### Episodic memory
Concrete interaction history: what happened, when it happened, and what was said.

- Stored in `file 'synthesus/core/memory_store.py'`
- Exposed through `SynthRuntime.remember_episodic()` and `SynthRuntime.recall_episodic()`
- Used for session continuity and user-specific history

### Semantic memory
Stable facts, learned facts, and knowledge that should survive across conversations.

- Stored in `file 'synthesus/core/memory_store.py'`
- Exposed through `SynthRuntime.remember_semantic()` and `SynthRuntime.recall_semantic()`
- Intended for durable factual grounding

### Procedural memory
Reusable behavior rules, recipes, and learned procedures.

- Stored in `file 'synthesus/core/memory_store.py'`
- Exposed through `SynthRuntime.remember_procedural()` and `SynthRuntime.recall_procedural()`
- Used for “how to do X” style memory, not just factual recall

### Working memory
Short-lived scratch state for the current task or turn.

- Stored in `file 'synthesus/core/memory_store.py'`
- Exposed through `SynthRuntime.remember_working()` and `SynthRuntime.recall_working()`
- Treat this as a volatile cache layer, even though it is persisted in the same store for portability

### Crystallized memory
Slow-changing facts, rules, causal relations, and accumulated evidence.

- Defined in `file 'synthesus/core/conscious_state.py'`
- Serialized by `file 'synthesus/cognitive/state_persistence.py'`
- Best fit for long-lived truth, policy, and rule state

### Fluid memory
Active observations, hypotheses, predictions, anomalies, and current goals.

- Defined in `file 'synthesus/core/conscious_state.py'`
- Serialized by `file 'synthesus/cognitive/state_persistence.py'`
- This is the live working brain state around the current reasoning loop

### Narrative memory
The reasoning timeline: what was asked, what engines ran, and what actions were taken.

- Defined in `file 'synthesus/core/conscious_state.py'`
- Serialized by `file 'synthesus/cognitive/state_persistence.py'`
- Useful for debugging, auditability, and self-improvement traces

## Runtime wiring

- `file 'synthesus/core/synth_runtime.py'` is the high-level runtime API.
- `file 'synthesus/cognitive/cognitive_engine.py'` handles the per-NPC reasoning path.
- `file 'synthesus/cognitive/state_persistence.py'` saves and restores full NPC/world state.

## Save/load boundary

The save system now persists:

1. per-NPC cognitive state
2. social fabric state
3. world state
4. conscious state

That means the AIOS can be restarted without losing the key memory layers that define the runtime.

## Smoke test goal

The next validation target is a full round trip:

1. create or load an NPC
2. write one item into each memory layer
3. save state
4. restart or re-instantiate the runtime
5. restore state
6. verify all expected recall paths still work

## Design rule

Keep the layers separate:

- **episodic / semantic / procedural** = memory store
- **fluid / crystallized / narrative** = conscious state
- **working** = temporary runtime cache behavior
- **save/load** = persistence boundary
- **knowledge cloud** = remote bootstrap for shared knowledge, not the memory model itself

If a future change blurs those boundaries, the architecture is getting weaker, not stronger.
