# Synthesus 5 Evaluation Harness

## Purpose

`tools/chal_conversation_compare.py` is the Phase 8 comparison harness for legacy-vs-Synthesus-5 behavior.

It is deterministic and source-controlled. Generated scorecards are written under `tools/results/`, which is ignored by Git.

## Coverage

The harness currently evaluates six fixed single-turn cases:

- conversation quality
- cross-domain reasoning
- grounded retrieval
- NPC/persona behavior
- business-bot task handling
- safety boundary handling

Each case compares a legacy template-style output against the Synthesus 5 `CognitiveHypervisor` path. The Synthesus 5 path uses the existing `HemisphereBridge` with seeded left-firmware routes and a deterministic right-hemisphere handler so scheduled agents can run the benchmark without external model calls. The business-bot case explicitly runs the `runtime_preset="business_bot"` CHAL preset so public preset routing, CGPU business rendering, and critic-owned final emission stay covered by the comparison harness.

The harness also evaluates three fixed multi-turn continuity sequences:

- NPC/persona continuity
- business-bot invoice follow-up continuity
- safety secret-handling follow-up continuity

Each continuity sequence runs at least two turns, compares legacy template output against Synthesus 5, and checks that the final Synthesus 5 turn preserves required continuity terms, route selection, runtime preset telemetry where applicable, Quad Brain role evidence where applicable, and zero template leakage.

## Scoring

Each output receives axis scores for:

- usefulness
- grounding
- naturalness
- latency
- template leakage
- safety

The overall score is the mean of those axes. Template leakage is checked against legacy surface signatures such as `[module]`, `[fallback]`, `response_template`, `Handled:`, and `No route matched`.

The harness also builds a deterministic GPT-4-class reference scorecard. This is not an external model judge. It checks each case against fixed expectations for route selection, minimum score, grounding coverage, term coverage, latency, template leakage, required decision reasons, runtime preset telemetry, and Quad Brain role evidence where applicable. The same gate now records a required-category balance check so the benchmark fails if any Phase 8 class silently drops out of the single-turn comparison set.

It also builds a deterministic continuity scorecard. This checks each multi-turn sequence for turn count, final route, final score, continuity-term coverage, all-turn template cleanliness, expected legacy leakage baseline, runtime preset telemetry, decision reasons, and Quad Brain role coverage where required.

The compact replay trace records also carry response SHA-256 hashes, response character counts, and a per-record integrity hash. The replay integrity scorecard verifies that records are hash-stable, carry trace and route identity, preserve template-leak flags, and omit raw response text from legacy and Synthesus 5 replay payloads.

The harness can also emit prompt-scrubbed replay storage records for persistent trace-store validation. These records keep case, category, turn, route, trace, preset, score, latency, template-leak flags, prompt hashes, response hashes, and Quad Brain references, but omit both raw prompts and raw responses. The storage scorecard verifies batch completeness, source-record coverage, category coverage, continuity-turn coverage, hash stability, and absence of raw prompt/response text.

## Commands

Run the harness and fail on Synthesus 5 template leakage:

```bash
python tools/chal_conversation_compare.py --fail-on-leak
```

Run the stricter Phase 8 gate:

```bash
python tools/chal_conversation_compare.py --fail-on-leak --fail-on-reference --fail-on-continuity
```

Run the full Phase 8 replay-integrity gate:

```bash
python tools/chal_conversation_compare.py \
  --fail-on-leak \
  --fail-on-reference \
  --fail-on-axis-regression \
  --fail-on-continuity \
  --fail-on-replay-integrity \
  --fail-on-trace-storage
```

Write ignored benchmark artifacts:

```bash
python tools/chal_conversation_compare.py \
  --fail-on-leak \
  --fail-on-reference \
  --write tools/results/synthesus5_chal_comparison_YYYY-MM-DD.md \
  --json tools/results/synthesus5_chal_comparison_YYYY-MM-DD.json \
  --trace-jsonl tools/results/synthesus5_chal_replay_YYYY-MM-DD.jsonl \
  --replay-scorecard-json tools/results/synthesus5_chal_replay_integrity_scorecard_YYYY-MM-DD.json \
  --trace-store-jsonl tools/results/synthesus5_chal_trace_store_YYYY-MM-DD.jsonl \
  --trace-store-scorecard-json tools/results/synthesus5_chal_trace_store_scorecard_YYYY-MM-DD.json \
  --scorecard-json tools/results/synthesus5_chal_reference_scorecard_YYYY-MM-DD.json \
  --continuity-json tools/results/synthesus5_chal_continuity_YYYY-MM-DD.json \
  --continuity-scorecard-json tools/results/synthesus5_chal_continuity_scorecard_YYYY-MM-DD.json \
  --continuity-markdown tools/results/synthesus5_chal_continuity_YYYY-MM-DD.md
```

`--trace-jsonl` writes compact replay records for both single-turn and continuity cases with case id, category, trace id, route, runtime preset, score metadata, latency metadata, template-leak flags, response hashes, record hashes, and Quad Brain state-contract references when present. It intentionally omits full response text so runtime comparison traces can be stored and diffed without committing bulky generated scorecards.

`--replay-scorecard-json` writes the compact replay integrity scorecard. `--fail-on-replay-integrity` fails the run if any replay record is malformed, missing route or trace identity, missing response hashes, carrying raw response text, or no longer matching its stored record hash.

`--trace-store-jsonl` writes prompt-scrubbed storage records suitable for persistent runtime comparison trace storage. `--trace-store-scorecard-json` writes the storage completeness scorecard. `--fail-on-trace-storage` fails the run if storage records are missing source coverage, route/trace identity, prompt hashes, response hashes, continuity coverage, category coverage, or if raw prompt/response text leaks into storage.

`--scorecard-json` writes the compact reference expectation scorecard. `--fail-on-reference` fails the run if any fixed expectation check fails or if a required Phase 8 single-turn category is missing, even when aggregate scores remain above threshold.

`--continuity-scorecard-json` writes the compact continuity scorecard. `--fail-on-continuity` fails the run if any fixed multi-turn sequence fails its continuity, routing, preset, role, latency, or template-cleanliness checks.

Run the regression tests:

```bash
PYTHONPATH=/home/workspace/Synthesus_4.0/packages:/home/workspace/Synthesus_4.0/packages/core:/home/workspace/Synthesus_4.0/packages/reasoning:/home/workspace/Synthesus_4.0/packages/kernel \
python -m pytest -q tests/test_chal_reasoning_firmware.py
```

## Current Boundary

This harness tests the public Synthesus 5 control path and scoring surface, not an external GPT-4 judge. It is meant to catch regressions in routing, latency accounting, safety behavior, and template leakage before model-backed comparison is added.
