# Dual-Hemisphere Architecture

> Synthesus 3.0 — Left + Right Hemisphere Processing

## Overview

Synthesus uses a dual-hemisphere processing model inspired by theories of human brain lateralization, now enhanced with **Parallel Hemisphere Execution**:

- **Left Hemisphere**: Fast, pattern-based, analytical processing (PPBRS kernel)
- **Right Hemisphere**: Slower, contextual, creative processing (Cognitive Core + specialized modules)
- **Reconciliation**: Parallel arbitration and agreement synthesis

## Architecture Diagram

```
                       PLAYER INPUT
                           │
                ┌──────────┴──────────┐
                │                     │
         LEFT HEMISPHERE       RIGHT HEMISPHERE
         Pattern Matching      Cognitive Core (Parallel)
                │                     │
         • Tokenized triggers  • Deductive Reasoning
         • Confidence scoring  • Inductive Reasoning
         • Fallback cascades   • Abductive Reasoning
         • <1ms resolution     • Conversation Tracking
                │              • Emotion State Machine
                │              • Knowledge Graph
                │              • Social Fabric
                │              • Context Recall
                │              • ML Organs (Triad + Shared)
                │                     │
                └──────────┬──────────┘
                      RECONCILER
                (Parallel Arbitration)
                           │
                   ML SWARM (7+ models)
                      ~500 KB total
                       <1ms inference
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

**File**: `core/hemisphere_bridge.py`

High-speed pattern matching via C++ `zo_kernel` binary:
- 1000+ QPS throughput
- <1ms per query
- Tokenized trigger matching
- Confidence scoring with fallback cascades

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
    response: str              # Final reconciled response
    hemisphere_used: str       # "left", "right", or "both"
    raw_confidence: float     # Confidence of winning hemisphere
    agreement_score: float     # Agreement between hemispheres (BOTH mode)
    left_response: str         # Raw left response (BOTH mode)
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

When both hemispheres contribute (BOTH mode), the bridge calculates **agreement score** using Jaccard similarity:

```python
def _calculate_agreement(self, left_resp: str, right_resp: str) -> float:
    left_tokens = set(left_resp.lower().split())
    right_tokens = set(right_resp.lower().split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
```

If agreement >= threshold (default 0.65), the more confident response is used. Otherwise, left hemisphere is preferred for analytical queries, right for creative ones.

## ML Swarm Integration

The **ML Swarm** (~458 KB total) provides shared classification, sentiment, and embedding services to both hemispheres:

| Model | Purpose | Size |
|-------|---------|------|
| Intent Classifier | Classify query intent | ~50 KB |
| Sentiment Analyzer | Detect emotional sentiment | ~40 KB |
| Embedder | Semantic similarity | ~50 KB |
| + others | Domain-specific models | ~318 KB |

Total inference: **<1ms** on CPU
