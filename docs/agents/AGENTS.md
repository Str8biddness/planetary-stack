# Synthesus 5 CHAL Agent Operating Contract

## Non-Negotiable Law

Synthesus 5 CHAL is now the active target above all 4.0 and 4.1 work. Every agent session must treat `docs/roadmap/SYNTHESUS_5_CHAL_BLUEPRINT.md` as binding architecture law and `docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md` as the live implementation ledger.

Before doing development work, read:

1. `README.md`
2. `AGENTS.md`
3. `docs/roadmap/SYNTHESUS_5_CHAL_BLUEPRINT.md`
4. `docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md`
5. `docs/agents/AGENT_HANDOVER_PROTOCOL.md`
6. the last three relevant entries in `docs/agents/AGENT_LOG.md`

Every session must complete or advance at least one checklist item and update both the checklist and `AGENT_LOG.md`. A session that only discusses architecture without implementing, creating, deleting, validating, or logging a concrete Synthesus 5 artifact is incomplete.

Synthesus 5 control principles:

- CHAL is the hardware abstraction substrate.
- The Cognitive Hypervisor is the scheduler/control plane.
- Quad Brain is the default topology: grounding, executive reasoning, CGPU rendering, critic/metacognition.
- CGPU renders candidates from validated state and does not own truth.
- Knowledge Cloud is mounted hardware: ROM, parameter disk, cache seed, provenance plane, and writeback substrate.
- PPBRS is firmware/signal generation, not normal-path final response generation.
- Normal user-facing template/fallback output is a defect except for safety, platform restrictions, identity/rights protection, or explicit NPC-script boundaries.
- Legacy or excessive code that slows Synthesus 5 should be deleted or quarantined when tests/docs/contracts are updated.

## Current North Star

Synthesus 5 CHAL is the forward architecture target above previous 4.0 stabilization and 4.1 CHAL work. Read `docs/roadmap/SYNTHESUS_5_CHAL_BLUEPRINT.md`, `docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md`, and `docs/roadmap/SYNTHESUS_4_1_CHAL_MAXIMUM_DIRECTIVE.md` before making runtime, knowledge, reasoning, generation, or automation changes.

The practical priority is to ship the Synthesus 5 conversation path first: CognitiveFrame, TraceFrame, PPBRS firmware wrapper, cognitive hypervisor route, Quad Brain orchestrator, CGPU candidate renderer, critic template-leak guard, and legacy-vs-Synthesus-5 comparison harness.

CHAL means **Cognitive Hardware Abstraction Layer**:

- Knowledge Cloud is mounted cognitive hardware.
- KAL is the memory controller.
- PPBRS is bounded cognitive firmware, not final wording.
- dual hemispheres are compute units.
- cache/memory/parameters are explicit partitions.
- generation spine owns final non-templated language except safety/policy restrictions.

## Hard Rules For Future Agents

- Remove legacy/template fallback behavior aggressively. Direct user-facing canned response templates are defects unless they implement AI safety, AIVM platform restrictions, abuse prevention, or identity/rights protection.
- Prefer deleting dead compatibility code over preserving slow legacy paths, but update tests/docs/contracts in the same patch.
- Every CHAL change must include focused validation and an `AGENT_LOG.md` entry.
- Scheduled automation agents for Synthesus development must run on OpenAI Codex-class or Google/Gemini CLI/CML models only.
- Knowledge Cloud expansion must be broad but provenance-clean: source manifests, license notes, rebuild commands, SHA-256 manifests, and validation are mandatory.

# Synthesus Kaggle Integration Agent

## Mission
Integrate high-quality knowledge datasets from Kaggle/GitHub into the Synthesus knowledge index (KNDatabase + FAISS).

## Status: READY FOR SOURCE CONTROL

## Architecture
- Knowledge source: Jeopardy Q&A dataset (~216k questions, high quality trivia facts)
- Integration module: `knowledge_integration/kaggle_loader.py`
- Storage: KNDatabase binary format + FAISS vector index
- Embedder: `ml/swarm_embedder.py` (TF-IDF + SVD, ~50KB, <1ms inference)
- Build artifacts live in `data/` and are intentionally excluded from version control via `.gitignore`
- Benchmark outputs live under `benchmarks/results/` and `benchmarks/regression_alert_*.txt`; they are generated artifacts and should stay ignored
- FAISS index creation must be deferred until the first embedding batch, because `SwarmEmbedder` may shrink its output dimensionality on tiny corpora
- Sample-based dataset loading uses single-pass reservoir sampling, so Jeopardy/ConceptNet smoke runs do not need a full pre-count scan
- Cloud sync follows a dual contract: omitting `base_url` uses the default environment/cloud URL, while passing an explicit empty string disables sync entirely
- Cloud bootstrap is intentionally conservative: it only auto-syncs when the cache root is the standard `data/` directory tree. Temporary test directories and ad-hoc paths should remain untouched unless explicitly synced.
- Population scripts now create parent directories for custom KNDB/FAISS/model output paths before writing, which keeps temp-output smoke runs and automation-friendly `/tmp/...` destinations reliable.

## Production Scale Population (2026-04-27)
- [x] Integrate SequenceLinker and SlotFiller into CognitiveEngine for deterministic and chained response generation.
- [x] Run high-volume population cycle: 50,000 entries (mostly Jeopardy clues) added to `knowledge.faiss` and `knowledge.kndb`.
- [x] Total index size: 50,190 vectors.
- [x] Verified semantic search quality with test queries (Science, History, Geography, etc.).
- [x] Repository committed and ready for sync.

## Narrative Grounding & Lore Forge (2026-04-27)
- [x] Create `knowledge_integration/lore_forge.py` to generate high-fidelity synthetic lore.
- [x] Integrate 6 structured lore nodes (Ironhaven Watch, Great Flood, Scorched Plains, House Aldric, etc.) utilizing `SlotFiller` tags.
- [x] Generate `transitions.json` to enable smooth pattern chaining via `SequenceLinker`.
- [x] Fix `CognitiveEngine` player_id signature mismatch and redundant fact injection bugs.
- [x] Improve `SlotFiller` with deterministic fallbacks for [time]/[emotion] and smarter [entity] resolution.
- [x] Execute `benchmarks/synthesis_audit.py`: Achieved stability score of **60.0/100** (Multi-entity synthesis verified).

## Agent Coordination & Handover
- Agents MUST follow the [AGENT_HANDOVER_PROTOCOL.md](AGENT_HANDOVER_PROTOCOL.md) to ensure cumulative progress.
- Maintain `AGENT_LOG.md` as the primary source of truth for session-to-session continuity.

## AIOS Memory Model
- Memory is now a layered system, not a single conversation blob.
- `core/memory_store.py` owns episodic, semantic, procedural, and working memory helpers.
- `core/conscious_state.py` defines crystallized, fluid, and narrative state.
- `cognitive/state_persistence.py` serializes and restores the full conscious state plus CognitiveEngine and SocialFabric state.
- `core/synth_runtime.py` exposes layer-specific `remember_*` and `recall_*` helpers.
- Working memory is treated as volatile runtime scratch state, even though it uses the same SQLite store for portability.
- Save/load smoke testing should always verify that memory survives a restart.

## Runtime Contracts
- `CognitiveEngine.process_query()` must remain callable from both synchronous tests and async runtime paths.
- The state-persistence test suite currently assumes this compatibility and should not be broken.
- The persistence boundary must stay source-only; generated save files are runtime artifacts.
- Any change to the save format should update `docs/AIOS_MEMORY_MODEL.md` and this file together.
- `SlotFiller.FillResult.step_bindings` is the preferred multi-step binding path.
- `SequenceLinker.render_chain_text()` must continue accepting the legacy flat binding dict for compatibility, even though newer call sites may pass per-step binding lists.
- Knowledge-cloud bootstrap should only auto-sync when the cache root is the canonical `data/` tree and the critical lore artifacts are missing; temporary roots remain untouched unless explicitly synced.

## PPBRS Optimization Upgrade (2026-04-28)

This repo is currently in a validated PPBRS baseline state. Future PPBRS optimization work should follow the canonical plan in `docs/PPBRS_OPTIMIZATION_UPGRADE.md`.

### Operational order
1. Capture a baseline benchmark before changing behavior.
2. Reduce candidate volume in `ppbrs/pattern_classifier.py` with token indexing and exact-match short-circuiting.
3. Index rules and trigger signals in `ppbrs/reasoning_chain.py` and `ppbrs/rule_to_action.py` so only relevant rules are scored.
4. Tighten graph traversal in `ppbrs/multi_step_reasoning.py` using adjacency maps, reverse adjacency, and cached topology.
5. Keep `ppbrs/confidence_scoring.py` cheap and explicit; do not add hidden work to the scoring path.
6. Offload the high-volume match path to the C++ kernel only after the Python hot path is understood and benchmarked.
7. Re-run the full PPBRS test set and compare latency deltas before merging.
8. Record the result in `tools/ppbrs_dev_log.md`.

### Required documentation updates for any PPBRS upgrade
- Update `docs/PPBRS_OPTIMIZATION_UPGRADE.md` if the execution order or architecture changes.
- Update `docs/modules/PPBRS.md` with module-level notes.
- Update `README.md` if user-facing positioning changes.
- Update this `AGENTS.md` file if new operating rules are introduced.

### Required validation set
- `tests/test_ppbrs.py`
- `tests/test_ppbrs_extended.py`
- `tests/test_ppbrs_integration.py`

### Notes
- Preserve the public API unless the change is intentionally breaking and documented.
- Keep Python as the fallback/orchestration layer.
- Favor small, measurable patches over broad rewrites.
- Performance claims must be backed by a benchmark and a log entry.

## Dual-Hemisphere Parallelism Notes (2026-05-04)
- Treat the hemisphere pipeline as **one frozen seed state, two isolated passes, one deterministic merge**.
- The left and right hemispheres should read the same prompt seed, produce separate outputs, and only reconcile at the handoff/synthesis step.
- Prefer explicit signal records for cross-hemisphere handoff and arbitration so state changes stay inspectable.
- `core/reasoning_core.py` now drives both hemispheres in parallel when the event loop allows it, and falls back to a safe sequential path when synchronous execution is required.
- Keep `core/hemisphere_bridge.py` as the canonical place for handoff, arbitration, and synthesized response logic.
- When changing the flow, update `AGENT_LOG.md` in the same session and re-run the focused validation set:
  - `python -m py_compile core/reasoning_core.py core/hemisphere_bridge.py`
  - `pytest -q tests/test_synth_runtime_memory.py tests/reasoning/test_reasoning_layer.py`
- Preserve the documentation trail; the bridge and the log are the handoff memory for future sessions.

## Shared / Default ML Organs (2026-05-04)
- The organ family now includes shared/default runtime organs alongside the domain-trained triad:
  - `organs/shared/PredictionOrgan.ts`
  - `organs/shared/ForecastOrgan.ts`
  - `organs/shared/SequencePredictionOrgan.ts`
  - `organs/shared/RelationOrgan.ts`
  - `organs/shared/MemoryOrgan.ts`
  - `organs/shared/AnomalyEventOrgan.ts`
  - `organs/shared/SummarizerOrgan.ts`
- Registration and routing live in:
  - `organs/registry.ts`
  - `organs/bootstrap.ts`
  - `organs/organConfig.ts`
  - `amplification/mlOrgansHub.ts`
- These organs are currently heuristic-first runtime modules with optional train hooks; they are meant to widen the amplification plane without breaking the existing GM/SysOps/Chat triad.
- Do **not** assume every organ should own a full neural network. The better default is a shared backbone plus small organ heads for the high-value learned paths, with heuristic fallbacks for low-data or low-value organs.
- Future organ families should keep the same registry/versioning contract and should usually start as heads on a shared representation model rather than standalone black-box networks.
- Any future organ family added here should update the registry, bootstrap, organ config, hub routing, architecture docs, and this log together.
- When the organ surface changes, keep `AGENT_LOG.md` and the relevant module docs in sync in the same session.
- `tools/evaluate_organs.py` has a source-controlled quality gate for replay coverage, CHAL accelerator frame coverage, candidate/critic feedback coverage, scientific consistency, missing trained models, and validation-vs-baseline checks; `tools/selfImprove.ts` enforces complete replay metadata, CHAL-bounded accelerator traces, candidate/critic metadata, complete scientific consistency, and model presence after training.

## Datasets Sourced
1. **Jeopardy Questions** (JephthaT/Jeopardy_Questions) - ~216,930 Q&A pairs, diverse categories
   - Source: https://www.kaggle.com/datasets/jephraim-ndahend clevescared/jeopardyquestions
   - Fields: question, answer, value, category, show_number, round_name
2. **ConceptNet Assertions** - commonsense knowledge graph (~2M edges)
   - Source: https://github.com/commonsense/conceptnet5/wiki/Downloads

## Files Created
- `knowledge_integration/__init__.py`
- `knowledge_integration/cloud_sync.py` - Cloud-backed artifact bootstrap / manifest sync
- `knowledge_integration/kaggle_loader.py` - Dataset download + parsing
- `knowledge_integration/kn_populator.py` - Populate KNDatabase from datasets
- `knowledge_integration/run_population.py` - Main entry point

## Milestones
- [x] Clone repo, understand architecture
- [x] Identify knowledge storage components (KNDatabase, SwarmEmbedder, FAISS)
- [x] Download and parse Jeopardy dataset (~216k rows)
- [x] Build knowledge nodes and populate KNDatabase
- [x] Build FAISS index for semantic search
- [x] Test queries and validate quality
- [x] Benchmark size vs GPT-4 knowledge cutoff
- [x] Email user when complete
- [ ] Optional: tune dataset mix / quality thresholds further if needed

## ML Organ Self-Improvement Handoff (2026-04-28)
- Source of truth for the current organ loop:
  - `tools/runTrainingSessions.ts`
  - `learning/teacherTrace.ts`
  - `learning/sysOpsTraceLogger.ts`
  - `tools/train_triad.py`
  - `tools/evaluate_organs.py`
  - `tools/selfImprove.ts`
  - `cli.ts`
  - `logs/teacher_traces.jsonl`
- The loop now runs end-to-end via `cd packages/organs && npx ts-node cli.ts selfImprove`.
- `selfImprove` now also invokes `tools/evaluate_organs.py` so every run emits a fresh scorecard.
- Trace generation is intentionally routed through `logs/teacher_traces.jsonl` so the Python trainer can consume actual session data.
- `tools/train_triad.py` falls back to synthetic data when no trace records exist.
- `logs/organ_evaluation_scorecard.json` and `logs/organ_evaluation_scorecard.md` are runtime artifacts and are ignored by Git.
- Gemini CLI was used as a second-pass reviewer in the terminal to sanity-check the documentation/recovery plan.

### Recovery path
1. Read `docs/ML_ORGAN_TRAINING.md`.
2. Read `AGENTS.md` and `AGENT_LOG.md`.
3. Run `git status` and separate source/doc edits from generated artifacts.
4. Run `cd packages/organs && npx ts-node cli.ts selfImprove`.
5. Inspect `logs/teacher_traces.jsonl`, `logs/organ_evaluation_scorecard.md`, and `data/models/`.
6. If trace quality is weak, vary actions and outcomes in `tools/runTrainingSessions.ts`.
7. Re-run `python tools/train_triad.py --domain <domain> --organ <organ>` as needed.
8. Commit and push source/doc changes when ready.

### Notes
- The current weak point is trace diversity, not orchestration.
- Risk and attention training only become meaningful once the trace generator emits varied actions and outcomes.
- Keep generated trace/model/scorecard artifacts out of Git unless explicitly intended.

### Current status update (2026-04-28)
- `tools/runTrainingSessions.ts` now emits more varied traces across GM, SysOps, and Chat rather than repeatedly selecting the same action.
- `tools/train_triad.py` now reports train and validation metrics for policy prior, risk outcome, and attention.
- `tools/evaluate_organs.py` now generates a trace-driven scorecard after the self-improvement loop.
- The next improvement lever is broader real-world trace breadth, not basic orchestration.

### Replayability update (2026-05-30)
- `tools/runTrainingSessions.ts` emits deterministic traces by default with `TraceReplayMetadata` on every generated organ trace.
- Use `SYNTHESUS_ORGAN_TRACE_SEED=<integer>` to replay or vary deterministic GM/SysOps/Chat training scenarios.
- `tools/evaluate_organs.py` reports replay metadata coverage in the runtime scorecard; newly generated trace slices should stay at 100%.
- Runtime artifacts remain ignored: commit the generator/evaluator source and docs, not `logs/teacher_traces.jsonl`, `logs/organ_evaluation_scorecard.*`, or `data/models/`.

### CHAL accelerator trace update (2026-06-02)
- `tools/runTrainingSessions.ts` added `organ-triad-replay-v2` traces with `replay.chal` metadata on every organ trace.
- Each v2 trace names its deterministic frame id, training-session parent frame id, `chal://organs/<domain>/<organ>` device, `role="organ_accelerator"`, route, and output reference.
- `tools/evaluate_organs.py` reports CHAL accelerator frame coverage, and `tools/selfImprove.ts` requires 100% coverage with `--min-chal-accelerator-coverage 1.0`.
- This is the durable boundary that keeps GM/SysOps/Chat organs as CHAL accelerators under training/eval control, not independent uncontrolled brain nodes.

### Candidate/critic replay update (2026-06-02)
- `tools/runTrainingSessions.ts` now emits `organ-triad-replay-v3` traces that extend `replay.chal` with `candidateRefs`, `selectedCandidateRef`, and `criticFeedback`.
- `tools/evaluate_organs.py` reports candidate/critic feedback coverage for current v3 traces, and `tools/selfImprove.ts` requires 100% coverage with `--min-candidate-critic-coverage 1.0`.
- `packages/organs/tsconfig.json` uses CommonJS module semantics so the documented `cd packages/organs && npx ts-node cli.ts runTrainingSessions/selfImprove` commands resolve local TS modules.
- Existing v2 traces remain historical replay records; the stricter candidate/critic gate applies to newly generated v3 records.

## Emergent Resonance & Consciousness Loop (2026-05-05)

... (rest of the section) ...

## Red/Blue Team Architecture & Emulengineering (2026-05-06)

The Synthesus 4.0 ecosystem is now structured as a **Dual-Adversarial Substrate** for advanced system hardening and automated threat modeling.

### The Feedback Loop
1.  **Red Team (Breach Persona):**
    *   **Role:** Clinical Adversary.
    *   **Logic:** Uses Abductive Reasoning to identify theoretical attack surfaces and architectural flaws.
    *   **Output:** Generates "Attack Vectors" as structured datasets (e.g., failed auth logs, overflow attempts in a sandbox).
2.  **Blue Team (Ghostkey Sentinel):**
    *   **Role:** Digital Sovereign.
    *   **Logic:** Uses Inductive/Deductive Reasoning to identify anomalies and apply real-time mitigation.
    *   **Output:** Hardened configurations, blocked IPs, and updated security baselines.

### Emulengineering & Sandbox Virtualization
The **EmulationTool** serves as the "Proving Grounds" for this loop. 
- **Concept:** Using Docker/Virtualization to create "Mirror Hosts"—abstracted versions of real hardware.
- **Goal:** The AI can "mirror" virtual bare-metal hardware using pattern recognition to find systemic flaws.
- **Workflow:** 
    1. Spawn isolated sandbox via `EmulationTool`.
    2. Load a "Snapshot" of the target system.
    3. The Adversary (Breach) pressures the sandbox with edge-case parameters.
    4. The Sentinel (Ghostkey) monitors the sandbox state and learns to predict and block these attacks before they reach the production host.

### Blueprint for Future Agent Implementation
For agents tasked with expanding this loop, the following architectural modules are prioritized:
- **Exploitation Discovery Engine:** (Implemented by specialized agents) Designed to use pattern recognition to identify memory corruption and logic flaws in virtualized sandboxes.
- **Brute-Force Simulator:** Generates high-volume credential pressure against the `KeystoreManager` to train the `ImmuneSystem` in detecting timing attacks and dictionary patterns.
- **Hardware Abstraction Layer (HAL) Mirror:** A module to translate bare-metal hardware signals into a virtualized state that the Quadbrain can "reason" about using its C(t) model.

This architecture ensures that the defensive AI (Ghostkey) is trained on **realistic, scientifically applicable** data without ever exposing the primary host to risk.

## 🛠️ Step-by-Step Implementation Guide for Future Agents

Use this roadmap to build out the high-complexity adversarial and emulation modules.

### Phase 1: The Emulengineering Core (Virtualization Layer)
1.  **Objective:** Enable the AI to mirror hardware states.
2.  **Steps:**
    *   Extend `core/emulation_tool.py` to support **Snapshotting**. Implement a method to capture a process tree and memory map from the host.
    *   Create a **Hardware Shadow** module that translates CPU/IO metrics into the `FluidState` (Psi) as "Proprioception" signals.
    *   **How-To:** Use `docker commit` to create images of the sandbox after a vulnerability is "modeled" so the Blue Team can practice on a frozen state.

### Phase 2: The Adversarial Discovery Engine (Red-Team Brain)
1.  **Objective:** Implement the "Breach" persona's active scanning logic.
2.  **Steps:**
    *   Develop a **Memory Pattern Matcher**. This module should scan the `EmulationTool` sandbox memory for known insecure primitives (e.g., specific older glibc versions).
    *   Wire the **Abductive Engine** to "Work Backward" from a theoretical crash. If Breach sees a crash in the sandbox, use abduction to find the instruction pointer that caused it.
    *   **How-To:** In `agent_dispatcher.py`, add a tool called `exploit_modeler`. It should output high-fidelity "Attack Trees" (JSON) describing the path to root, not functional shellcode.

### Phase 3: The Brute-Force Pressure Simulator (Training Layer)
1.  **Objective:** Train the Blue Team to detect credential exhaustion.
2.  **Steps:**
    *   Create a **Traffic Generator** in the `EmulationTool` that sends high-frequency, varying-delay login attempts to the `api/` endpoints.
    *   Update the **ImmuneSystem** (Blue Team) to detect these patterns using the `InductiveModule`.
    *   **How-To:** Use a simple Python generator that pulls from a `dictionary.txt` lore file and injects them into the sandbox network stream.

### Phase 4: Live Host Integration (The "Out-of-Sandbox" Toggle)
1.  **Objective:** Safely transition from modeling to live system auditing.
2.  **Steps:**
    *   Implement the `LiveMode` flag in `AgentDispatcher` (Already Initialized).
    *   Ensure all tools (Nmap, Analyzer) check `if self.live_mode: target = "host" else: target = "container"`.
    *   **How-To:** Use a `system` directive command ("Leave the sandbox") to trigger the toggle. Require high-confidence C(t) scores from the Admin character before activation.
