# PPBRS Optimization Upgrade Plan

This document is the canonical start-to-finish upgrade plan for PPBRS performance work.

## Purpose

PPBRS already passes its current unit and integration tests. The optimization work is about reducing unnecessary compute, tightening graph traversal, and moving the hot path toward the C++ kernel while preserving behavior and the public API.

## Upgrade Goals

1. Reduce matching cost from full-scan scoring to candidate-scoped scoring.
2. Reduce reasoning graph traversal cost with explicit adjacency structures and caches.
3. Reduce rule evaluation cost by indexing rules and short-circuiting irrelevant paths.
4. Keep Python as the orchestration and fallback layer.
5. Move high-frequency matching paths into `zo_kernel` when the Python path is no longer the right default.
6. Preserve all existing tests unless a change is intentionally accompanied by updated expectations.

## Current Baseline

The current PPBRS modules are functional, but several paths are still linear scan style implementations:

- `ppbrs/pattern_classifier.py` now uses an inverted token index plus fanout-aware candidate pruning so shared broad tokens do not force full-corpus scoring when selective query tokens are present.
- `ppbrs/reasoning_chain.py` evaluates rules and reasoning chains without a dedicated trigger index.
- `ppbrs/multi_step_reasoning.py` uses a graph object, but repeated traversal logic can be tightened with adjacency caching and better path bookkeeping.
- `ppbrs/rule_to_action.py` evaluates every rule before selecting actions.
- `ppbrs/pattern_extractor.py` is acceptable as-is for offline extraction, but its outputs should feed indexed stores rather than ad hoc scans.

## Start-to-Finish Upgrade Sequence

### Phase 0 — Baseline Measurement

Before changing logic, capture a baseline.

Measure:
- pattern match latency
- rule evaluation latency
- graph traversal latency
- full pipeline latency
- p50 and p95, not just averages

Record:
- test corpus size
- number of registered patterns
- number of rules
- average reasoning graph size
- current test pass/fail state

Output should be written to `tools/ppbrs_dev_log.md` and any dedicated ignored benchmark artifact.

### Phase 1 — Candidate Reduction in Pattern Classification

Target file: `ppbrs/pattern_classifier.py`

Status 2026-06-06: implemented an inverted token index, fanout-aware broad-token pruning, cached normalized token forms, and exact-match short-circuiting in `PatternClassifier`. Queries with a selective token plus a shared trigger now score only selective candidates; broad-token-only queries still evaluate the broad candidate set for compatibility. Candidate scoring reuses normalized forms and avoids fuzzy distance checks when exact token/form matches already prove the match.

Implementation order:
1. Build an inverted index from normalized token -> pattern IDs.
2. Tokenize input once.
3. Pull only candidate patterns that share at least one token with the query.
4. Score only the candidate set.
5. Run fuzzy matching only on the reduced set.
6. Keep exact-match or high-confidence early exits.
7. Cache normalized token forms so candidate scoring does not rebuild cleaned variants on every request.

Expected effect:
- lower average match latency
- less wasted scoring work on irrelevant patterns
- easier scaling as the pattern library grows

### Phase 2 — Rule and Chain Filtering

Target files:
- `ppbrs/reasoning_chain.py`
- `ppbrs/rule_to_action.py`

Status 2026-06-04: implemented tag and trigger indexes for `WeightedRuleEvaluator` and `RuleToActionMapper`. Tagged contexts now evaluate matching tagged rules plus untagged shared rules, and contexts with indexed trigger keys or exact trigger values skip unrelated rule conditions before scoring. `WeightedRuleEvaluator.apply_top_rule()` and `apply_fallback()` now use a short-circuiting top-rule scan so single-winner firmware paths stop after the highest-weight qualifying rule is known. `RuleToActionMapper.map_to_action()` now uses priority-first, score-upper-bound single-winner evaluation instead of full fanout when only one action will execute.

Implementation order:
1. Add tag-based and trigger-based indexing for rules.
2. Pre-filter by context keys and tags before score evaluation.
3. Make top-rule selection short-circuit once the best viable rule is known.
4. Keep fallback logic intact so behavior remains stable when no rule qualifies.

Expected effect:
- fewer rule evaluations per request
- less redundant context inspection
- cleaner separation between filtering and scoring

### Phase 3 — Graph Traversal and Multi-Step Reasoning

Target file: `ppbrs/multi_step_reasoning.py`

Status 2026-05-27: implemented `ReasoningGraph.forward_adjacency`, `reverse_adjacency`, duplicate-edge suppression, cached topological order, adjacency-backed forward/backward traversal, and adjacency-backed shortest-path expansion.

Implementation order:
1. Maintain explicit forward and reverse adjacency maps.
2. Cache topological order when the graph changes.
3. Keep a visited set in every traversal path.
4. Make backward reasoning walk antecedents deterministically.
5. Add cycle-safe path handling.
6. Avoid scanning the full edge list for every path lookup.

Expected effect:
- lower traversal cost
- better behavior on larger graphs
- fewer hidden performance cliffs

### Phase 4 — Confidence and Scoring Tightening

Target file: `ppbrs/confidence_scoring.py`

Status 2026-06-05: implemented single-pass accumulation in `ConfidenceScorer.calculate()`. The scorer now builds the emitted `ConfidenceComponent` list while accumulating weighted totals, context averages, and chain averages, preserving the existing `ConfidenceScore` output shape while removing redundant scoring-path passes. `tools/ppbrs_benchmark.py` now tracks a `confidence_scoring` micro-benchmark.

Implementation order:
1. Keep the score composition explicit and cheap.
2. Skip components that are not present.
3. Normalize once at the end.
4. Preserve the current public score shape.

Expected effect:
- smaller overhead in confidence-heavy paths
- cleaner reasoning about final score composition

### Phase 5 — Kernel Offload

Target architecture:
- `reasoning/` C++ `zo_kernel`
- Python fallback modules in `ppbrs/`

Implementation order:
1. Define the exact Python-to-kernel protocol for match requests.
2. Use the kernel for hot-path matching when available.
3. Keep Python fallback behavior equivalent.
4. Treat kernel errors as fallback triggers, not fatal failures.

Expected effect:
- best throughput for the highest-volume path
- reduced Python overhead for mature deployments

### Phase 6 — Regression Validation

Every optimization pass must run the same validation set:

- `tests/test_ppbrs.py`
- `tests/test_ppbrs_extended.py`
- `tests/test_ppbrs_integration.py`
- any focused benchmark or smoke test added for the new hot path

Validation rules:
- behavior must stay functionally equivalent unless a change is intentionally documented
- performance gains must be measured, not assumed
- failed tests must block the upgrade from being marked complete

### Phase 7 — Rollout and Documentation

After implementation:
1. Update this document if the architecture changes.
2. Update `AGENTS.md` with any new operational contract.
3. Update `docs/modules/PPBRS.md` with module-level notes.
4. Update `README.md` if the user-facing positioning changes.
5. Append a progress entry to `tools/ppbrs_dev_log.md`.

## Success Criteria

The upgrade is considered complete when:

- pattern matching avoids scanning the full corpus for every request
- rule evaluation is indexed and short-circuited
- graph traversal no longer scans edges repeatedly
- hot paths are benchmarked with stable latency improvements
- the fallback path remains available and correct
- the public API and tests remain coherent

## Non-Goals

- Do not rewrite the PPBRS API for cosmetic reasons.
- Do not remove fallback logic.
- Do not trade correctness for speed without documenting the tradeoff.
- Do not move everything into C++; Python orchestration remains valuable.

## Files to Touch

Primary:
- `ppbrs/pattern_classifier.py`
- `ppbrs/reasoning_chain.py`
- `ppbrs/multi_step_reasoning.py`
- `ppbrs/rule_to_action.py`
- `ppbrs/confidence_scoring.py`

Documentation:
- `AGENTS.md`
- `docs/modules/PPBRS.md`
- `README.md`
- this file
- `tools/ppbrs_dev_log.md`

## Recommended Implementation Order

1. Baseline benchmark
2. Pattern candidate reduction
3. Rule indexing and short-circuiting
4. Graph adjacency and caching
5. Confidence-path tightening
6. Kernel offload integration
7. Regression test pass
8. Log and document the final state
