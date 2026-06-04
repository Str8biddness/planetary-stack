# PPBRS — Probabilistic Pattern-Based Reasoning System

> Synthesus 5 — bounded CHAL cognitive firmware

## Overview

PPBRS is the bounded symbolic reasoning firmware for Synthesus. It provides multi-step reasoning chains with confidence scoring, pattern classification, and rule-to-action mapping, but it does **not** own normal user-facing wording. Its output contract is now a CHAL firmware signal consumed by dual-hemisphere arbitration and the bounded generation spine.

## Architecture

```
Query Input
    │
    ├──► PPBRS Kernel (C++, zo_kernel) — routing / confidence / constraints
    │         │
    │         ▼
    │    Pattern Matcher → Causal Engine → Bayesian Update → CHAL firmware signal
    │
    └──► Python fallback router
              │
              ▼
         CHAL firmware signal → generation spine
```

## CHAL Firmware Contract (2026-05-27)

The concrete interface lives in `packages/core/chal/frames.py`. `packages/reasoning/chal.py` is now a compatibility import layer so older PPBRS call sites continue to resolve the same classes while the stable CHAL package boundary stays under core.

| Record | Purpose |
|--------|---------|
| `CognitiveTask` | Schedulable reasoning workload with query, domain, budgets, constraints, and trace ID |
| `ExecutionPlan` | Ordered firmware stages such as classify, route, constrain, and handoff to generation |
| `ModuleMessage` | CHAL fabric payload from PPBRS to the generation spine |
| `Checkpoint` | Replayable reasoning state for route/confidence decisions |
| `TelemetryRecord` | Latency, confidence, fallback, and template-leakage metadata |
| `PPBRSFirmwareSignal` | Parsed `synthesus.chal.reasoning_firmware.v1` envelope tying the task, plan, message, checkpoint, telemetry, confidence, constraints, and trace ID together |

`build_ppbrs_firmware_signal()` creates the JSON-shaped `synthesus.chal.reasoning_firmware.v1` payload. The fallback PPBRS bridge now returns `KernelResult.response == ""` for normal routing and stores the firmware payload in `KernelResult.metadata["chal_firmware_signal"]` with `user_facing=False`.

Each CHAL reasoning record now supports explicit `to_dict()` / `from_dict()` round trips, and `PPBRSFirmwareSignal.from_dict()` validates schema identity plus trace-ID consistency across all nested records. This keeps firmware signals replayable and prevents a drifted task, plan, message, checkpoint, or telemetry record from being accepted as a coherent PPBRS handoff.

The canonical frame names are `CognitiveFrameTask`, `CognitiveFrameExecutionPlan`, `CognitiveFrameMessage`, `CognitiveFrameCheckpoint`, and `CognitiveFrameTelemetry`. Legacy names (`CognitiveTask`, `ExecutionPlan`, `ModuleMessage`, `Checkpoint`, `TelemetryRecord`) remain aliases for reasoning firmware compatibility. Knowledge Cloud mount telemetry in `core.chal.interfaces` remains a separate mount-controller record until the broader mount schema is folded into the same package boundary.

Allowed fixed-response exceptions remain safety, abuse prevention, identity/rights protection, and explicit AIVM platform restrictions. Normal pattern matches, retrieval matches, and low-confidence fallbacks must be surfaced through the generation spine or a future VGD-backed realization path.

### Pipeline Firmware Boundary (2026-05-27)

`ContextAwareReasoningPipeline.process()` now follows the same boundary as the kernel bridge: normal matches and no-match fallbacks return `response == ""`, `user_facing == False`, and a `chal_firmware_signal`. Historical `response_template` values are preserved only as `module_message.payload.template_context` so the generation spine can use them as bounded context without emitting the raw template as final surface text.

`WeightedRuleEvaluator` and `RuleToActionMapper` maintain tag indexes and untagged-rule buckets, so tagged contexts only evaluate relevant tagged rules plus shared untagged rules. `ReasoningGraph` maintains forward/reverse adjacency maps and a cached topological order, and graph traversal uses those structures instead of scanning the full edge list.

## Core Modules

| Module | File | Classes | Purpose |
|--------|------|---------|---------|
| `pattern_classifier` | `ppbrs/pattern_classifier.py` | PatternClassifier, Pattern, ClassificationResult | Classify patterns by type and confidence |
| `pattern_extractor` | `ppbrs/pattern_extractor.py` | Regex/NGram/TFIDF/Contextual/Composite extractors | Extract patterns from text and interaction logs |
| `confidence_scoring` | `ppbrs/confidence_scoring.py` | ConfidenceScorer, BayesianConfidenceUpdater | Score pattern match confidence with Bayesian updating |
| `reasoning_chain` | `ppbrs/reasoning_chain.py` | ReasoningChainBuilder, ReasoningChain, ContextAwareReasoningPipeline | Build and evaluate multi-step reasoning chains |
| `multi_step_reasoning` | `ppbrs/multi_step_reasoning.py` | MultiStepReasoningChain, ReasoningChainOptimizer, FallbackReasoningEngine | Coordinate multi-step reasoning with hypothesis tracking |
| `rule_to_action` | `ppbrs/rule_to_action.py` | RuleToActionMapper, ActionSequenceBuilder | Convert reasoning rules to executable actions |

## Optimization Baseline (2026-04-28)

The repository is currently in a validated PPBRS baseline state. Significant optimizations have been implemented in `pattern_classifier.py` and `multi_step_reasoning.py`, including **token indexing** and **adjacency map traversal** to handle higher complexity reasoning chains.

### Key Optimizations
- **Token Indexing**: Reduced candidate volume in `PatternClassifier` using inverted token indexes.
- **Fanout-Aware Candidate Pruning**: Shared high-frequency trigger tokens are treated as broad evidence and ignored when more selective query tokens are available. If a query only contains broad tokens, PPBRS still evaluates those broad candidates so compatibility and fallback behavior remain intact.
- **Adjacency Maps**: Replaced linear edge scans with constant-time adjacency lookups in `multi_step_reasoning`.
- **Cached Topology**: Pre-computed reasoning graph structures for zero-overhead traversal.
- **Rule Tag + Trigger Indexing**: Rule evaluators prefilter by context tags, trigger keys, and exact trigger values before evaluating conditions.
- **Top-Rule Short-Circuiting**: Single-winner weighted-rule execution scans indexed candidates by descending weight and stops once the best threshold-qualified firmware rule is known, while full `evaluate()` calls still return all activated rules for callers that need fanout.

## Optimization Upgrade Path

The current PPBRS implementation is functionally complete, but the next performance upgrade should follow a staged approach rather than a broad rewrite.

### Current bottlenecks

- `pattern_classifier` still does pattern scoring in a mostly linear candidate set.
- `reasoning_chain` and `rule_to_action` can benefit from tag and trigger indexes.
- `multi_step_reasoning` can be made faster by replacing repeated edge scans with adjacency maps and cached traversal structures.
- `confidence_scoring` is already light, but it should remain explicit and avoid hidden overhead.
- The C++ kernel should remain the long-term hot path for high-volume matching.

### Recommended implementation order

1. Baseline benchmark the current path.
2. Add candidate pruning to `pattern_classifier`.
3. Index rules and triggers in `reasoning_chain` and `rule_to_action`.
4. Add forward and reverse adjacency plus cache-aware traversal in `multi_step_reasoning`.
5. Keep confidence scoring cheap and stable.
6. Offload the highest-frequency match path to `zo_kernel` after Python behavior is stable.
7. Re-run the PPBRS test suite and record the latency delta.

### Validation and logging

Every upgrade pass should:
- run `tests/test_ppbrs.py`
- run `tests/test_ppbrs_extended.py`
- run `tests/test_ppbrs_integration.py`
- append a note to `logs/ppbrs_dev_log.md`
- update the canonical plan at `docs/PPBRS_OPTIMIZATION_UPGRADE.md` if the architecture changed

For the authoritative start-to-finish implementation plan, see `docs/PPBRS_OPTIMIZATION_UPGRADE.md`.

## Pattern Types

| Type | Description | Example |
|------|-------------|---------|
| `reasoning` | Deductive/inductive reasoning patterns | `"IF high_cpu AND memory_leak THEN restart"` |
| `response` | Conversational response templates | `"Greeting pattern for familiar users"` |
| `emotional` | Emotional reaction patterns | `"Express concern when user mentions problem"` |
| `behavioral` | Action sequences and habits | `"Always check logs before escalating"` |

## Confidence Scoring

Patterns are scored using weighted factors:

```
score = (context_overlap × 0.5) + (success_rate × 0.3) + (weight × 0.1) + (recency_boost × 0.1)
```

- **context_overlap**: Jaccard similarity between query and pattern trigger tokens
- **success_rate**: Historical ratio of successful pattern activations
- **weight**: Explicit importance weight [0.0, 1.0]
- **recency_boost**: Exponential decay based on last update time

## Usage

```python
from ppbrs import (
    PatternClassifier, Pattern, ClassificationResult,
    ReasoningChainBuilder, ReasoningChain, ReasoningStep,
    ConfidenceScorer, BayesianConfidenceUpdater,
    RuleToActionMapper, Action, ActionType,
    RegexPatternExtractor, MultiStepReasoningChain
)

# Classify a query against known patterns
classifier = PatternClassifier()
result = classifier.classify("Check system status")
print(f"Best match: {result.best_pattern.pattern_id} (confidence: {result.confidence:.2f})")

# Build a reasoning chain
builder = ReasoningChainBuilder()
chain = builder.define_chain("diagnose_issue", steps=[
    ReasoningStep("check_logs", "Examine recent log entries"),
    ReasoningStep("identify_pattern", "Match against known issue patterns"),
    ReasoningStep("suggest_fix", "Propose remediation steps"),
])
evaluated = builder.evaluate_chain(chain, context={"issue": "high_cpu"})

# Multi-step reasoning with hypothesis tracking
msr = MultiStepReasoningChain()
msr.add_hypothesis("cpu_spike", "High CPU caused by memory leak")
msr.add_hypothesis("memory_leak", "Memory leak in worker process")
result = msr.evaluate_hypothesis("cpu_spike", {"metrics": {...}})

# Map rules to actions
mapper = RuleToActionMapper()
mapper.register_rule(Rule(
    trigger="high_error_rate",
    action=Action(type=ActionType.NOTIFY, params={"channel": "alerts"}),
    priority=1.0
))
action_result = mapper.map_to_action({"error_rate": 0.95})
```

## C++ Kernel (`zo_kernel`)

The `zo_kernel` binary provides high-throughput pattern matching:

- **Throughput**: 1000+ queries per second
- **Latency**: <1ms per pattern match
- **Interface**: stdin/stdout JSON protocol

### Protocol

```json
// Request (to stdin)
{"query": "What is the status of the database?", "character_id": "synth"}

// Firmware response (normal reasoning path)
{
  "response": "",
  "confidence": 0.87,
  "found": true,
  "module_used": "db_health_check",
  "metadata": {
    "user_facing": false,
    "chal_firmware_signal": {
      "schema": "synthesus.chal.reasoning_firmware.v1",
      "trace_id": "trace-...",
      "constraints": ["generation_spine_owns_final_wording"]
    }
  }
}
```

### Fallback

When `zo_kernel` is unavailable, the Python fallback router in `packages/kernel/bridge.py` emits the same CHAL firmware metadata. It no longer emits legacy strings such as `[fallback] No route matched` or `[module] Handled: ...` as user-facing text.

### Reranker Fallback Boundary (2026-05-27)

`packages/reasoning/reranker.py` now defaults to deterministic lexical reranking instead of attempting an implicit cross-encoder model load. This keeps scheduled reasoning validation bounded and prevents hidden network/model-download stalls. Cross-encoder use remains available through `CrossEncoderReranker(config={"enable_cross_encoder": True})`; when disabled or unavailable, the fallback ranks by normalized query/chunk token overlap and only uses reciprocal-rank scoring when no lexical signal exists.

### Template Guard Boundary (2026-05-28)

`packages/reasoning/generation/template_guard.py` defines the shared normal-surface leakage guard for legacy signatures such as `[module]`, `[fallback]`, `response_template`, `Handled:`, and `No route matched`. `CognitiveHypervisor` applies this guard after bridge dispatch and before returning a Synthesus 5 response. Normal-path leaks are quarantined into degraded CHAL telemetry instead of being emitted as final prose.

Allowed fixed-response exceptions are labeled through `TemplateSurface`: `safety`, `platform`, `identity_rights`, and `explicit_npc_script`. Those labels do not make PPBRS a final language owner; they only preserve explicit policy/script boundaries while keeping the surface classification visible in `telemetry.template_guard`.

Legacy import paths are preserved through thin compatibility packages:
- `ppbrs.*` -> `packages/reasoning/*`
- `core.reasoning.*` -> `packages/reasoning/*`

### NPC Response-Compositor Boundary (2026-06-01)

`packages/core/cognitive/response_compositor.py` is no longer classified as an unlabeled legacy template emitter. It exposes `ResponseCompositor.compose_labeled()`, which returns text plus Synthesus 5 surface metadata:

- `surface="explicit_npc_script"`
- `boundary="response_compositor"`
- `user_facing=True`
- `legacy_template_signature_present=<bool>`

The older `compose()` API remains as a string-returning compatibility wrapper. Cognitive-engine local character handling now calls the labeled form and records `debug.template_surface`, so classic character `response_template` strings remain visible as an explicit NPC-script exception instead of an unclassified normal-path final-language source.

### ELS Candidate Writeback Boundary (2026-06-02)

`packages/core/els_bridge.py` is classified as non-user-facing writeback substrate. It can extract and persist `response_template` text from successful interactions for review, but candidate JSON exports and integrated pattern records carry `template_surface` metadata:

- `surface="writeback_candidate"`
- `boundary="els_candidate_writeback"`
- `user_facing=False`
- `legacy_template_signature_present=False`

This keeps learned pattern text available to legacy stores while making the Synthesus 5 boundary explicit: ELS does not own final wording, and any later user-facing use must pass through a labeled NPC-script, firmware, generation, or critic-controlled path.

### Cognitive Engine Fallback Boundary (2026-06-02)

`packages/core/cognitive/cognitive_engine.py` now labels terminal local NPC fallback text in `debug.template_surface` before returning it from the legacy cognitive engine. Both direct character fallback text and escalation stall text carry:

- `surface="explicit_npc_script"`
- `boundary="cognitive_engine_fallback"`
- `source="character_fallback"` or `source="escalation_stall"`
- `user_facing=True`
- `legacy_template_signature_present=<bool>`

This preserves classic NPC behavior while making the exception explicit: local character fallback remains an NPC-script surface outside the normal Synthesus 5 assistant path, not an unlabeled PPBRS or template-owned final response.

### Legacy API Template Boundary (2026-06-02)

`packages/api/fastapi_server.py` and `packages/api/production_server.py` are no longer classified as `legacy_quarantine_required` template emitters. The remaining legacy-compatible API surfaces now carry explicit template metadata:

- FastAPI character pattern and fallback responses include `debug.template_surface` with `boundary="explicit_npc_script"` and `normal_assistant_path=False`.
- FastAPI kernel-unavailable fallback text no longer emits `[FALLBACK]` signatures on `/query` or `/stream`.
- Production API pattern ingestion labels stored response text as `boundary="legacy_api_pattern_storage"` with `user_facing=False`.
- Production API pattern recall returns a labeled candidate with `boundary="explicit_npc_script"` before any RAG response is finalized through the generation spine.

This completes the current Phase 6 quarantine pass: legacy API compatibility remains available for explicit NPC-script and non-user-facing storage paths, while normal Synthesus 5 assistant responses stay owned by CHAL, the Cognitive Hypervisor, generation spine, and critic/template guard.

## Integration with Dual-Hemisphere

PPBRS runs primarily in the **Left Hemisphere** of the dual-hemisphere architecture:

| Hemisphere | Processing | Latency Target |
|------------|------------|----------------|
| Left (PPBRS) | Pattern matching, fast deduction, CHAL firmware signals | <1ms |
| Right (Cognitive) | Emotion, relationships, context | 10-50ms |
