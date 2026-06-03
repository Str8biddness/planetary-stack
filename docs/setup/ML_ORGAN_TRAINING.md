# ML Organ Training and Recovery Guide

This document is the start-to-finish handoff for the Synthesus ML organ loop.

## What this pipeline does

1. `cd packages/organs && npx ts-node cli.ts selfImprove`
2. `tools/runTrainingSessions.ts` emits planning/output traces for GM, SysOps, and Chat.
3. `learning/teacherTrace.ts` persists those traces to `logs/teacher_traces.jsonl`.
4. `tools/train_triad.py` reads the trace log and trains the triad organs.
5. `tools/evaluate_organs.py` evaluates the freshly trained models and writes a scorecard.
6. Trained models are written to `data/models/<domain>_<organ>.pkl`.
7. The trained models are re-used on the next run.

## Current contracts

- `learning/teacherTrace.ts` is the shared trace store.
- `tools/runTrainingSessions.ts` is the trace generator.
- `tools/train_triad.py` is the training entrypoint.
- `tools/evaluate_organs.py` is the evaluation entrypoint.
- `tools/selfImprove.ts` is the orchestration wrapper.
- `packages/organs/cli.ts selfImprove` is the top-level command.
- `logs/organ_evaluation_scorecard.json` and `logs/organ_evaluation_scorecard.md` are runtime artifacts and are ignored by Git.
- `tools/runTrainingSessions.ts` now emits deterministic replay metadata on each organ trace: generator version, seed, scenario ID, step, and simulated timestamp.
- Current `organ-triad-replay-v3` traces also include CHAL accelerator frame metadata under `replay.chal`: `frameId`, `parentFrameId`, `chal://organs/<domain>/<organ>` device URI, `role="organ_accelerator"`, route, output reference, candidate references, selected candidate reference, and critic feedback reference. This keeps organ traces bounded as CHAL accelerators rather than independent brains, while exposing candidate-generation and critic-feedback interfaces to evaluation.
- Set `SYNTHESUS_ORGAN_TRACE_SEED=<integer>` to replay the same GM/SysOps/Chat trace scenarios with a different deterministic seed.

## Fresh start to finish

### 1. Get into the repo

```bash
git clone https://github.com/Str8biddness/synthesus.git
cd synthesus
```

### 2. Verify the toolchain

```bash
bun --version
python --version
```

### 3. Run the full self-improvement loop

```bash
cd packages/organs
npx ts-node cli.ts selfImprove
```

This should:
- register the default fallback organs
- run GM, SysOps, and Chat training sessions
- append traces to `logs/teacher_traces.jsonl`
- train all 9 triad models
- evaluate the models and write a fresh scorecard under `logs/`

### 4. Check the trace log

```bash
wc -l logs/teacher_traces.jsonl
head -5 logs/teacher_traces.jsonl
```

### 5. Check the trained models

```bash
ls -lh data/models/
```

### 6. Check the evaluation scorecard

```bash
cat logs/organ_evaluation_scorecard.md
```

### 7. Train one organ directly if needed

```bash
python tools/train_triad.py --domain chat --organ policy_prior
python tools/train_triad.py --domain sysops --organ risk_outcome
python tools/train_triad.py --domain gm --organ attention
```

### 8. Evaluate one domain directly if needed

```bash
python tools/evaluate_organs.py --domain chat
python tools/evaluate_organs.py --domain sysops
python tools/evaluate_organs.py --domain gm
```

### 9. Verify the outputs

Expected behavior:
- if trace data exists, the Python trainer uses it
- if no trace data exists, it falls back to synthetic training data
- the command exits cleanly and writes model files and a scorecard
- the scorecard reports replay metadata coverage for each domain/organ slice

### 10. Push source changes only

Before pushing:
- review `git status`
- commit source and docs changes
- keep generated trace/model/scorecard artifacts out of the commit unless they are explicitly intended

## What to watch for

- If the trace log is too uniform, training will be numerically weak even if the pipeline is wired correctly.
- If the trace file is missing, the trainer will silently fall back to synthetic data.
- If you change the trace schema, update this document, `AGENTS.md`, and `AGENT_LOG.md` together.
- If replay coverage drops below 100% on newly generated traces, check that every `appendTraceEntry` call includes `replay` metadata.
- If candidate/critic coverage drops below 100%, check that every `replay.chal` block includes `candidateRefs`, `selectedCandidateRef`, and `criticFeedback`.
- If the evaluation scorecard shows validation below baseline, the next lever is broader trace diversity, not orchestration changes.

## Recovery checklist for another chat

1. Read this file first.
2. Read `AGENTS.md` and `AGENT_LOG.md`.
3. Run `git status` and identify whether only source/docs are dirty or whether generated outputs are also present.
4. If the pipeline needs to be refreshed, run `cd packages/organs && npx ts-node cli.ts selfImprove`.
5. If trace quality needs improvement, edit `tools/runTrainingSessions.ts` to vary actions and outcomes.
6. Re-run `python tools/train_triad.py --domain <domain> --organ <organ>` for the affected organs.
7. Verify the traces, model outputs, and the evaluation scorecard.
8. Commit and push source changes.

## Current status

- Trace generation is now diversified across GM, SysOps, and Chat sessions.
- `tools/train_triad.py` now reports train/validation metrics instead of only fitting on the full trace set.
- `tools/evaluate_organs.py` now produces a runtime scorecard after the full self-improvement loop.
- `tools/evaluate_organs.py` now supports a quality gate for replay metadata coverage, scientific consistency, missing models, and validation-vs-baseline checks.
- `tools/evaluate_organs.py` now reports CHAL accelerator frame coverage and candidate/critic feedback coverage for current `organ-triad-replay-v3` traces, and can fail when those traces lack CHAL-bounded organ metadata.
- `tools/selfImprove.ts` runs evaluation with `--min-replay-coverage 1.0 --min-chal-accelerator-coverage 1.0 --min-candidate-critic-coverage 1.0 --min-scientific-consistency 1.0 --fail-missing-models` so generated traces must remain replayable, CHAL-bounded, critic-visible, and numerically valid.
- `packages/organs/cli.ts selfImprove` runs the updated loop.

## Updated next step

Keep expanding trace variety if risk or attention metrics still look weak; use `python tools/evaluate_organs.py --fail-under-baseline` as the stricter local gate before making baseline performance mandatory in the full loop.
