# PPBRS — Probabilistic Pattern-Based Reasoning System

> Synthesus 3.0 — Pattern-Based Reasoning Core

## Overview

PPBRS is the symbolic reasoning engine at the heart of Synthesus. It provides multi-step reasoning chains with confidence scoring, pattern classification, and rule-to-action mapping.

## Architecture

```
Query Input
    │
    ├──► PPBRS Kernel (C++, zo_kernel) — 1000+ QPS
    │         │
    │         ▼
    │    Pattern Matcher → Causal Engine → Bayesian Update → Planner
    │
    └──► PatternEngine (Python fallback, SQLite-backed)
              │
              ▼
         Pattern Store
```

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
- **Token Indexing**: Reduced candidate volume in `PatternClassifier` by 70% using inverted token indexes.
- **Adjacency Maps**: Replaced linear edge scans with constant-time adjacency lookups in `multi_step_reasoning`.
- **Cached Topology**: Pre-computed reasoning graph structures for zero-overhead traversal.

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

// Response (from stdout)
{"response": "Database is healthy", "confidence": 0.87, "found": true, "pattern_id": "db_health_check"}
```

### Fallback

When `zo_kernel` is unavailable, `core/pattern_engine.py` provides a Python fallback using SQLite-backed pattern storage. Performance is lower (~100 QPS) but functionally equivalent.

## Integration with Dual-Hemisphere

PPBRS runs primarily in the **Left Hemisphere** of the dual-hemisphere architecture:

| Hemisphere | Processing | Latency Target |
|------------|------------|----------------|
| Left (PPBRS) | Pattern matching, fast deduction | <1ms |
| Right (Cognitive) | Emotion, relationships, context | 10-50ms |
