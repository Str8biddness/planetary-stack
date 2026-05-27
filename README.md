# Synthesus 5 CHAL — Bounded Synthetic Intelligence Runtime

Synthesus 5 is the active development target for this repository.

The non-negotiable blueprint is:

- `docs/roadmap/SYNTHESUS_5_CHAL_BLUEPRINT.md`
- `docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md`
- `docs/agents/AGENTS.md`
- `docs/agents/AGENT_HANDOVER_PROTOCOL.md`
- `docs/agents/AGENT_LOG.md`

Every agent session must read the blueprint and checklist before changing code. Every session must leave behind a concrete implementation, deletion, benchmark, validation result, created artifact, or explicit blocker tied to the checklist. Development that does not move Synthesus 5 forward is out of scope unless it protects safety, correctness, or repository integrity.

## Core Thesis

Synthesus 5 is not a generic chatbot wrapper and not a claim that this repo has trained a frontier-scale model. It is a **bounded synthetic intelligence operating architecture**:

```text
User / NPC / Client
  -> Cognitive Hypervisor
  -> CHAL: Cognitive Hardware Abstraction Layer
  -> Quad Brain Compute Topology
  -> Knowledge Cloud Hardware + Memory + Parameters + Cache
  -> CGPU Simulation / Surface Rendering
  -> Critic / Safety / Metacognition
  -> Final bounded non-templated response
```

The target is GPT-4-class visible usefulness through orchestration, memory, grounding, routing, critique, and specialized cognitive modules, not through pretending that Synthesus is a larger base model than it is.

## Non-Negotiable Architecture

### CHAL

**CHAL** means **Cognitive Hardware Abstraction Layer**. Knowledge, memory, cache, parameters, PPBRS, model calls, tools, critics, and generation are treated as virtual cognitive devices with explicit request/response frames.

### Cognitive Hypervisor

The hypervisor schedules, isolates, budgets, routes, synchronizes, and audits cognitive workloads. It does not directly own truth or final language. It coordinates the runtime.

### Quad Brain

Four brains are the default logical topology:

1. **Knowledge / Grounding Brain**: Knowledge Cloud, KAL, KN, provenance, crystallized memory.
2. **Executive Reasoning Brain**: planning, constraints, budgets, route selection, decomposition.
3. **CGPU Simulation / Rendering Brain**: language, NPC behavior, persona expression, narrative continuity, candidate rendering.
4. **Critic / Safety / Metacognitive Brain**: hallucination checks, template-leak detection, safety envelope, rewrite pressure.

More nodes are allowed only as specialized accelerators. The default topology remains four brains plus accelerators, not uncontrolled agent sprawl.

### CGPU

The **Cognitive Graphics Processing Unit** renders validated cognitive state into high-quality natural language, NPC behavior, scenes, persona expression, and dialogue candidates. It does not own facts. It renders from grounded state and is constrained by the hypervisor and critic.

### Knowledge Cloud Hardware

The Knowledge Cloud is mounted cognitive hardware, not an ad hoc retrieval helper:

- ROM plane: curated validated knowledge, doctrine, blueprints.
- Parameter disk: routing priors, domain packs, persona priors, learned pattern packs.
- Cache plane: hot retrievals, session summaries, recent reasoning paths.
- Writable memory plane: episodic memory, crystallized memory, validation scores, learned corrections.

### PPBRS Firmware Boundary

PPBRS is bounded cognitive firmware. It may emit structured signals, constraints, evidence, and candidate frames. It must not emit normal-path final user-facing templates.

Template/canned output is allowed only for:

- AI safety and abuse prevention.
- AIVM platform restrictions.
- identity, rights, or consent protection.
- intentionally scripted NPC scenes where the script boundary is explicit.

## Repository Structure

- `packages/kernel/`: C++ AIVM kernel, virtual devices, pybind11 bridge, VMM and hardware-adjacent acceleration.
- `packages/aivm/`: AIVM Python plane: devices, scheduler, isolation, snapshot, kernel, inspector.
- `packages/core/`: SynthRuntime, Quad Brain orchestration, hemisphere bridge, memory state, CHAL interfaces.
- `packages/knowledge/`: KAL, KN, Knowledge Cloud runtime integration, cloud sync, health checks, partitions.
- `packages/reasoning/`: PPBRS, planning, query decomposition, verification, reranking, bounded generation spine.
- `packages/organs/`: TypeScript ML organs, shared backbone, training/evaluation loop.
- `packages/api/`: API surfaces, gateways, parameter cloud, knowledge cloud routing.
- `packages/frontend/`: React hyperspace console.
- `apps/`: desktop, Android, Ghostkey, and related applications.
- `tools/`: benchmarks, training, ingestion, maintenance, evaluation utilities.
- `tests/`: integrated Python and TypeScript verification.
- `docs/`: architecture, modules, agents, roadmap, memory, setup, and API schemas.

## Required Agent Workflow

Start every Synthesus development session by reading:

1. `docs/roadmap/SYNTHESUS_5_CHAL_BLUEPRINT.md`
2. `docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md`
3. `docs/agents/AGENTS.md`
4. `docs/agents/AGENT_HANDOVER_PROTOCOL.md`
5. the last three relevant entries in `docs/agents/AGENT_LOG.md`

End every session by updating:

1. `docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md`
2. `docs/agents/AGENT_LOG.md`
3. any module docs affected by the change

## Build And Validation

Use targeted validation tied to the changed files:

```bash
python -m py_compile <changed_python_files>
python -m pytest -q <relevant_tests>
```

For kernel work:

```bash
cd packages/kernel
mkdir -p build
cd build
cmake .. -DBUILD_PYBIND=ON
cmake --build . -j2
```

For TypeScript organ work:

```bash
cd packages/organs
bun test
```

## Roadmap

- **Phase 0**: freeze Synthesus 5 law into README, agent docs, automation prompts, and implementation checklist.
- **Phase 1**: CHAL frame contract for tasks, devices, telemetry, checkpoints, and outputs.
- **Phase 2**: Cognitive Hypervisor MVP with route plans, budgets, isolation, and trace records.
- **Phase 3**: Quad Brain MVP with grounded specialized dispatch and serialized arbitration.
- **Phase 4**: CGPU candidate renderer and surface realization path.
- **Phase 5**: Knowledge Cloud hardware mounts through KAL/CHAL.
- **Phase 6**: delete or quarantine normal-path legacy template/fallback generation.
- **Phase 7**: memory/cache hierarchy with writeback, provenance, and replayable traces.
- **Phase 8**: GPT-4-class comparison/evaluation harness.
- **Phase 9**: product runtime polish across API, frontend, NPC, and business-bot surfaces.
- **Phase 10**: hardening, release gates, and reproducible build/test validation.

## Git Hygiene

Generated artifacts stay out of source control:

- `data/`
- FAISS indexes
- KNDB binaries
- generated model caches
- benchmark results
- scorecards
- runtime logs

Commit only intentional source and documentation changes. Do not commit `.github/workflows/` changes unless explicitly requested.

---

© 2026 AIVM LLC | Synthesus 5 CHAL
