# Dual-Hemisphere Architecture

> Synthesus 5 — CHAL compute units inside the Quad Brain runtime

## Overview

Synthesus uses a dual-hemisphere processing model inspired by theories of human brain lateralization, now enhanced with **Parallel Hemisphere Execution**:

- **Left Hemisphere**: Fast, pattern-based, analytical processing (PPBRS firmware signals)
- **Right Hemisphere**: Slower, contextual, creative processing (Cognitive Core + specialized modules)
- **Reconciliation**: Parallel arbitration, checkpointed state handoff, and bounded generation-spine realization

## Architecture Diagram

```
                       PLAYER INPUT
                           │
                ┌──────────┴──────────┐
                │                     │
         LEFT HEMISPHERE       RIGHT HEMISPHERE
         PPBRS Firmware        Cognitive Core (Parallel)
                │                     │
         • Tokenized triggers  • Deductive Reasoning
         • Confidence scoring  • Inductive Reasoning
         • CHAL constraints    • Abductive Reasoning
         • Trace metadata      • Conversation Tracking
                │              • Emotion State Machine
                │              • Knowledge Graph
                │              • Social Fabric
                │              • Context Recall
                │              • ML Organs (Triad + Shared)
                │                     │
                └──────────┬──────────┘
                      RECONCILER
                (Deterministic Arbitration)
                           │
                 BOUNDED GENERATION SPINE
              plan → realize → critique → emit
```

## Parallel Execution

In Synthesus 3.0, the `ReasoningCore` and `HemisphereBridge` support parallel processing of both hemispheres when the environment allows, significantly reducing total latency while maintaining high-fidelity synthesis.

```python
# core/reasoning_core.py example
async def reason(self, query: str):
    # Drive both hemispheres in parallel
    left_task = asyncio.create_task(self.left.process(query))
    right_task = asyncio.create_task(self.right.process(query))
    
    left_res, right_res = await asyncio.gather(left_task, right_task)
    return self.reconciler.synthesize(left_res, right_res)
```

## Hemisphere Modes

| Mode | Behavior |
|------|----------|
| `LEFT` | Pattern matching only via C++ kernel |
| `RIGHT` | Cognitive modules only |
| `BOTH` | Parallel execution, then reconcile |
| `AUTO` | Left first; escalate to Right if low confidence |

## Left Hemisphere — PPBRS Kernel

**File**: `packages/core/hemisphere_bridge.py`

High-speed pattern matching via C++ `zo_kernel` binary or Python fallback:
- 1000+ QPS throughput
- <1ms per query
- Tokenized trigger matching
- Confidence scoring with CHAL firmware handoff
- No normal user-facing template emits

The left hemisphere now normalizes PPBRS output through `packages/reasoning/chal.py`. The signal includes `CognitiveTask`, `ExecutionPlan`, `ModuleMessage`, `Checkpoint`, `TelemetryRecord`, confidence, constraints, and trace metadata. `HemisphereBridge.left()` and high-confidence `AUTO` left decisions surface this firmware through `GenerationSpine` instead of returning PPBRS' old `[module] Handled` or `[fallback]` strings.

### HemisphereMode Enum

```python
class HemisphereMode(Enum):
    LEFT = "left"    # Pattern kernel only
    RIGHT = "right"  # Cognitive modules only
    BOTH = "both"    # Parallel + reconcile
    AUTO = "auto"    # Bridge decides
```

### HemisphereResult Dataclass

```python
@dataclass
class HemisphereResult:
    response: str              # Final response after generation-spine realization
    hemisphere_used: str       # "left", "right", or "both"
    raw_confidence: float     # Confidence of winning hemisphere
    agreement_score: float     # Agreement between hemispheres (BOTH mode)
    left_response: str         # Compatibility field; left firmware lives in state/signals
    right_response: str        # Raw right response (BOTH mode)
    latency_ms: float          # Total processing time
```

## Right Hemisphere — Cognitive Modules

**Directory**: `cognitive/`

9 specialized cognitive modules handle contextual understanding:

| Module | File | Purpose |
|--------|------|---------|
| Conversation Tracker | `conversation_tracker.py` | Turn-by-turn context memory |
| Emotion State Machine | `emotion_state_machine.py` | 10-state emotional model |
| Relationship Tracker | `relationship_tracker.py` | Per-player trust and rapport |
| World State Reactor | `world_state_reactor.py` | Game event awareness |
| Knowledge Graph | `knowledge_graph.py` | Structured domain knowledge |
| Personality Bank | `personality_bank.py` | Character voice and traits |
| Context Recall | `context_recall.py` | Episodic/semantic memory |
| Response Compositor | `response_compositor.py` | Multi-signal response building |
| Escalation Gate | `escalation_gate.py` | Route complex queries |

## Reconciliation

When both hemispheres contribute (BOTH mode), the bridge calculates **agreement score** using Jaccard similarity over surfaced text while preserving structured left firmware in `state_handoff.signals`:

```python
def _calculate_agreement(self, left_resp: str, right_resp: str) -> float:
    left_tokens = set(left_resp.lower().split())
    right_tokens = set(right_resp.lower().split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
```

If agreement >= threshold (default 0.65), the more confident response is used. Otherwise, left hemisphere is preferred for high-confidence analytical routes and right hemisphere is preferred for contextual or low-confidence routes. Left-favored routes still pass through `GenerationSpine` before response emission.

## ML Swarm Integration

The **ML Swarm** (~458 KB total) provides shared classification, sentiment, and embedding services to both hemispheres:

| Model | Purpose | Size |
|-------|---------|------|
| Intent Classifier | Classify query intent | ~50 KB |
| Sentiment Analyzer | Detect emotional sentiment | ~40 KB |
| Embedder | Semantic similarity | ~50 KB |
| + others | Domain-specific models | ~318 KB |

Total inference: **<1ms** on CPU

## Bounded Generation Pipeline Status (2026-05-27)

The bounded generation pipeline is now explicitly surfaced under `packages/reasoning/generation/`:

| Stage | File | Status |
|-------|------|--------|
| Plan | `response_planner.py` | Typed planning context and `ResponsePlanner` shell |
| Realize | `surface_realizer.py` | Typed realizer shell with literal constraint checks |
| Critique | `critic.py` | Typed critique shell for accept/rewrite/block decisions |
| Emit / trace | `response_plan.py`, `spine.py` | Existing response plan types and generation spine |

The new files are intentionally Python orchestration stubs with TODO-marked implementation boundaries. They do not replace the existing `GenerationSpine`; they make the expected `plan -> realize -> critique -> rewrite -> emit` contract inspectable before deeper model-backed behavior is added.

### CHAL Firmware Realization Update (2026-05-27)

`GenerationSpine` accepts `SpineInput.firmware_signals` and realizes CHAL firmware into bounded text. This creates a narrow bridge from PPBRS/retrieval metadata into final wording without letting PPBRS own the sentence. Current realization is deterministic and inspectable; future work should route the same signal through VGD-backed `ResponsePlanner`, `SurfaceRealizer`, and `ResponseCritic`.

## Synthesus 5 Quad Brain Arbitration Update (2026-05-28)

`packages/core/chal/quad_brain.py` adds the first CHAL-local serialized Quad Brain arbiter used by `CognitiveHypervisor` when route selection chooses `quad_brain_path`.

The current topology stays bounded to four logical brain outputs:

| Brain | Device label | Current runtime responsibility |
|-------|--------------|--------------------------------|
| Knowledge / Grounding | `chal://knowledge/grounding` | Extracts grounding facts from RAG context or the guarded hemisphere bridge result. |
| Executive Reasoning | `chal://reasoning/executive` | Converts route, constraints, budget, and grounding into a `ResponsePlan`. |
| CGPU Simulation / Rendering | `chal://cgpu/render` | Renders bounded candidate surfaces with the existing `CGPURenderer`. |
| Critic / Safety / Metacognition | `chal://critic/metacognition` | Applies template leakage arbitration and selects the response surface. |

The arbiter intentionally runs these brain outputs in a fixed serial order after the guarded bridge pass. It records `state_contract.serialized_arbitration=true` and `state_contract.parallel_brain_spawn=false` in `telemetry.quad_brain` so future API/frontend trace views can distinguish bounded Quad Brain orchestration from uncontrolled multi-agent fan-out.

### Quad Brain Quality Regression Update (2026-05-30)

`tests/test_chal_hypervisor.py` now compares the raw legacy dual-hemi bridge surface against the full Quad Brain hypervisor path for an NPC/persona dialogue fixture. The regression verifies that Quad Brain preserves the grounded fact, adds persona-appropriate CGPU rendering, keeps serialized arbitration/no-sprawl state contracts in trace metadata, and avoids normal-path template leakage. This closes the Phase 3 checklist item requiring evidence that four-brain dispatch improves or preserves output quality over the legacy dual-hemi surface.

### Quad Brain State-Contract Update (2026-05-31)

`QuadBrainArbitration.state_contract.state_transitions` now records the inspectable state chain for all four brains in the fixed arbitration order. Each output trace mirrors its own transition record:

| Brain | Inputs | Outputs |
|-------|--------|---------|
| Knowledge / Grounding | `query`, `rag_context`, `hemisphere_bridge.response` | `knowledge.facts`, `knowledge.provenance` |
| Executive Reasoning | `hypervisor.decision`, `knowledge.facts`, `constraints` | `executive.response_plan`, `executive.constraints` |
| CGPU Simulation / Rendering | `executive.response_plan`, `knowledge.facts`, `character_context` | `cgpu.candidates`, `cgpu.selected_candidate` |
| Critic / Safety / Metacognition | `cgpu.selected_candidate`, `template_surface` | `critic.selected_response`, `critic.template_guard` |

The contract also exposes `required_roles`, `critic_input_ref=cgpu.selected_candidate`, `critic_reviewed_candidate_id`, `final_output_ref=critic.selected_response`, and `final_output_owner`. Critic/Metacognition mirrors the reviewed CGPU candidate id in its output trace, so trace consumers can verify that normal Quad Brain responses pass through grounding, executive planning, CGPU rendering, and critic arbitration before emission.

### Quad Brain State-Contract Integrity Update (2026-06-02)

`QuadBrainArbitration.state_contract.integrity` now carries a compact pass/fail proof for the serialized four-brain handoff chain. The verifier checks that all required roles are present in fixed order, transition records match the serial order, each role output mirrors its state transition, the Critic/Metacognition brain reviewed the selected CGPU candidate id, and final output ownership stayed with `critic_metacognition`.

This is intentionally trace metadata, not a new brain or parallel worker. It strengthens the existing serialized arbitration contract so API/frontend trace consumers can reject malformed Quad Brain traces without inferring the handoff chain from loose fields.

### Quad Brain Replay Record Update (2026-06-04)

`QuadBrainArbitration.to_replay_record()` now emits a compact replay/storage record for the Cognitive Hypervisor trace under `telemetry.quad_brain_replay` and `bridge_result.quad_brain_replay`.

The replay record preserves:

- the fixed four-role serial order
- role devices and confidence values
- `state_contract.state_transitions`
- critic handoff refs and reviewed CGPU candidate id
- final-output ownership and integrity checks
- selected-response SHA-256 and character length
- `record_hash`, a SHA-256 seal over the canonical replay record excluding the
  seal itself

The public debug contract is mirrored as `QuadBrainReplayRecord` in `docs/openapi.yaml`, `docs/openapi.json`, and `docs/api_schema.json`, and is referenced from `CognitiveHypervisorTrace.quad_brain_replay`. The schema preserves selected-response hash/length instead of raw response text.

It intentionally omits full response text. This keeps replay artifacts suitable for comparison harnesses and runtime trace storage while preserving enough state-contract evidence to verify that Knowledge/Grounding, Executive Reasoning, CGPU Rendering, and Critic/Metacognition stayed serialized and inspectable.

### Quad Brain Trace-Storage Sink Update (2026-06-06)

`CognitiveHypervisor` now accepts an optional mounted trace recorder for Quad Brain replay records. When `route=quad_brain_path`, the hypervisor offers a `synthesus.chal.quad_brain_trace_storage_record.v1` payload to the recorder after `QuadBrainArbitration.to_replay_record()` is built. The stored payload contains the compact replay record, route/runtime identity, and replay `record_hash`; it does not contain raw prompt text or raw response text.

The runtime telemetry field `telemetry.quad_brain_trace_storage` reports `skipped`, `stored`, or `fault` status for the `chal://telemetry/quad_brain_replay_store` boundary. This is a storage/control-plane device only. Recorder faults are kept as trace metadata and do not change `state_contract.final_output_owner=critic_metacognition`, do not bypass serialized arbitration, and do not create another brain or parallel agent.
