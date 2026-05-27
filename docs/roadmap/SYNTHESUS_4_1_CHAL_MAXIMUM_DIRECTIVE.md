# Synthesus 4.1 CHAL Maximum Directive

Synthesus 4.1 is the CHAL line: **Cognitive Hardware Abstraction Layer**. The goal is to make the current runtime feel primitive by comparison, not by adding vague complexity, but by turning modules, memory, parameters, retrieval, and generation into an inspectable virtual cognitive machine.

## Core Thesis

```text
Synthesus 4.0
  modules call modules

Synthesus 4.1 CHAL
  cognitive workloads run on virtual cognitive hardware
```

CHAL borrows from advanced server boxes, storage arrays, NUMA systems, GPU schedulers, and supercomputer clusters:

- mount manager for Knowledge Cloud partitions
- cache hierarchy for active context and hot retrieval
- cognitive scheduler for task routing and budgets
- message bus for module-to-module communication
- checkpointing for replayable reasoning traces
- telemetry for cache hits, retrieval confidence, generation quality, fallback elimination, and template leakage risk

## Virtual Hardware Map

```text
CHAL
├── Cognitive CPU
│   ├── planner
│   ├── verifier
│   ├── arbiter
│   └── executor
├── Cognitive GPU
│   ├── parallel hypothesis generation
│   ├── right-hemisphere narrative simulation
│   ├── multi-sample reasoning
│   └── rewrite/realization passes
├── Knowledge RAM
│   ├── working memory
│   ├── current turn facts
│   └── session-local state
├── Parameter Disk
│   ├── routing priors
│   ├── persona priors
│   ├── domain packs
│   └── learned pattern packs
├── ROM Cloud
│   ├── validated reference corpora
│   ├── hardware/emulation blueprints
│   ├── ethics and platform constraints
│   └── canonical Synthesus doctrine
├── Cache Hierarchy
│   ├── L1 current turn cache
│   ├── L2 session cache
│   ├── L3 user/project cache
│   └── L4 Knowledge Cloud/cloud mirror
└── Cognitive Fabric
    ├── ModuleMessage protocol
    ├── trace IDs
    ├── budgets
    ├── confidence metadata
    └── health checks
```

## Non-Negotiable Runtime Direction

1. **Knowledge Cloud is mounted hardware**, not a passive retrieval sidecar.
2. **KAL becomes the memory controller** for CHAL partitions.
3. **PPBRS becomes bounded cognitive firmware**, not the final language layer.
4. **Dual hemispheres become compute units**: left for retrieval/constraints, right for generative simulation, then deterministic arbitration.
5. **The generation spine must own final wording** except for explicit safety/platform restriction responses.
6. **Template fallback generation must be deleted**. Legacy canned response paths are defects unless they are safety/policy gates.
7. **Every module must expose health, latency, confidence, and trace metadata**.

## Knowledge Cloud Expansion Contract

The Knowledge Cloud repository should be aggressively expanded across useful domains, but it must remain legally and operationally clean:

- use source manifests for every source
- track license/provenance/rebuild commands
- prefer public-domain, permissive, government, academic, documentation, standards, and official reference sources
- keep raw third-party archives out of Git unless redistribution is clearly allowed
- rebuild artifacts through pipelines, not manual binary edits
- validate with `synthesus-kc validate`, `validate-sources`, manifest stamping, and file:// smoke sync

Target source planes:

- science, math, engineering, medicine references where licensing allows
- computer science, security, operating systems, distributed systems, embedded systems
- standards/specifications and official documentation
- world geography, history, civics, economics, law summaries with provenance
- game/NPC behavior, social simulation, character memory, dialogue grounding
- hardware blueprints, emulation profiles, AIVM/CHAL architecture notes

## Legacy Removal Policy

Delete or quarantine:

- direct user-facing `response_template` emits
- generic fallback strings like "I do not know" when they bypass generation
- old `/query` and `/api/query` behavior once canonical clients are migrated
- duplicated pre-4.0 compatibility shims that no active tests or clients need
- unused templates/static UI paths that keep old response contracts alive
- hidden remote or implicit model-download fallbacks

Allowed fixed-response exceptions:

- AI safety boundaries
- AIVM platform restrictions
- identity/rights protection
- abuse prevention
- explicit degraded-state markers when generation infrastructure is unavailable

## Implementation Phases

### Phase 1: CHAL Interfaces

- create `packages/core/chal/` or equivalent package boundary
- define `CHAL`, `Mount`, `Partition`, `CognitiveTask`, `ExecutionPlan`, `ModuleMessage`, `Checkpoint`, and telemetry records
- add tests for mount/query/dispatch/checkpoint contracts

### Phase 2: Knowledge Hardware Mounts

- expose Knowledge Cloud planes as mounted partitions
- route KAL queries through CHAL mount metadata
- add cache locality and provenance to retrieval results

### Phase 3: Cache + Scheduler

- implement L1/L2/L3/L4 cache controllers
- add budget-aware scheduling for fast/deep/dual-hemi/critic paths
- record cache hit/miss and task allocation telemetry

### Phase 4: Template Elimination

- replace direct template emits with plan -> realize -> critique -> rewrite -> emit
- add tests that fail on known template signatures
- keep policy/safety templates isolated from normal language generation

### Phase 5: Hemi-Sync Metacognition

- turn PPBRS output into left-hemi firmware signals
- run right-hemi generative hypotheses in parallel where possible
- serialize arbitration and checkpoint the final reasoning trace

### Phase 6: Continuous Improvement Loop

- benchmark old vs CHAL paths
- log deletions and reductions in legacy fallback surface
- expand Knowledge Cloud source coverage each cycle
- publish clean artifacts and docs to GitHub

## Automation Rule

All scheduled Synthesus development automations must use OpenAI Codex-class models or Google/Gemini CLI/CML models only. Each run should either:

- implement a CHAL interface or route,
- remove legacy/template fallback behavior,
- expand/validate the Knowledge Cloud data plane,
- benchmark CHAL vs old paths,
- update docs/tests/logs with concrete progress,
- or report a blocker with exact file paths and commands tried.
