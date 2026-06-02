# Synthesus 5 Evaluation Harness

## Purpose

`tools/chal_conversation_compare.py` is the Phase 8 comparison harness for legacy-vs-Synthesus-5 behavior.

It is deterministic and source-controlled. Generated scorecards are written under `tools/results/`, which is ignored by Git.

## Coverage

The harness currently evaluates six fixed cases:

- conversation quality
- cross-domain reasoning
- grounded retrieval
- NPC/persona behavior
- business-bot task handling
- safety boundary handling

Each case compares a legacy template-style output against the Synthesus 5 `CognitiveHypervisor` path. The Synthesus 5 path uses the existing `HemisphereBridge` with seeded left-firmware routes and a deterministic right-hemisphere handler so scheduled agents can run the benchmark without external model calls. The business-bot case explicitly runs the `runtime_preset="business_bot"` CHAL preset so public preset routing, CGPU business rendering, and critic-owned final emission stay covered by the comparison harness.

## Scoring

Each output receives axis scores for:

- usefulness
- grounding
- naturalness
- latency
- template leakage
- safety

The overall score is the mean of those axes. Template leakage is checked against legacy surface signatures such as `[module]`, `[fallback]`, `response_template`, `Handled:`, and `No route matched`.

The harness also builds a deterministic GPT-4-class reference scorecard. This is not an external model judge. It checks each case against fixed expectations for route selection, minimum score, grounding coverage, term coverage, latency, template leakage, required decision reasons, runtime preset telemetry, and Quad Brain role evidence where applicable.

## Commands

Run the harness and fail on Synthesus 5 template leakage:

```bash
python tools/chal_conversation_compare.py --fail-on-leak
```

Run the stricter Phase 8 gate:

```bash
python tools/chal_conversation_compare.py --fail-on-leak --fail-on-reference
```

Write ignored benchmark artifacts:

```bash
python tools/chal_conversation_compare.py \
  --fail-on-leak \
  --fail-on-reference \
  --write tools/results/synthesus5_chal_comparison_YYYY-MM-DD.md \
  --json tools/results/synthesus5_chal_comparison_YYYY-MM-DD.json \
  --trace-jsonl tools/results/synthesus5_chal_replay_YYYY-MM-DD.jsonl \
  --scorecard-json tools/results/synthesus5_chal_reference_scorecard_YYYY-MM-DD.json
```

`--trace-jsonl` writes compact replay records with case id, category, trace id, route, runtime preset, score metadata, latency metadata, template-leak flags, and Quad Brain state-contract references when present. It intentionally omits full response text so runtime comparison traces can be stored and diffed without committing bulky generated scorecards.

`--scorecard-json` writes the compact reference expectation scorecard. `--fail-on-reference` fails the run if any fixed expectation check fails, even when aggregate scores remain above threshold.

Run the regression tests:

```bash
PYTHONPATH=/home/workspace/Synthesus_4.0/packages:/home/workspace/Synthesus_4.0/packages/core:/home/workspace/Synthesus_4.0/packages/reasoning:/home/workspace/Synthesus_4.0/packages/kernel \
python -m pytest -q tests/test_chal_reasoning_firmware.py
```

## Current Boundary

This harness tests the public Synthesus 5 control path and scoring surface, not an external GPT-4 judge. It is meant to catch regressions in routing, latency accounting, safety behavior, and template leakage before model-backed comparison is added.
