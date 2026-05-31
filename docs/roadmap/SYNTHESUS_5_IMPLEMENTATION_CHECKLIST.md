# Synthesus 5 Implementation Checklist

This is the live implementation ledger for the Synthesus 5 CHAL blueprint. Every agent session must update this file before ending.

Rules:

- Mark an item only when source/docs/tests validate the work.
- Add the commit hash or session log reference when possible.
- Do not mark aspirational architecture as complete unless there is runnable implementation, a test, or a durable artifact.
- If a session cannot complete an item, add a blocker note under the relevant phase.

Legend:

- `[ ]` not started
- `[~]` in progress
- `[x]` implemented and validated

## Phase 0: Freeze The Target Contract

- [x]  Create Synthesus 5 CHAL blueprint with architecture, diagrams, terminology, and start-to-finish implementation plan.

- [x]  Promote Synthesus 5 as the README-level active target.

- [x]  Add root `file AGENTS.md` so agent bootstrapping starts from Synthesus 5 law.

- [x]  Update agent operating contract to make the blueprint non-negotiable.

- [x]  Update handover protocol so every session reads the blueprint and checklist first.

- [x]  Create this implementation checklist as the cross-agent progress ledger.

- [x]  Ensure all scheduled automations are retargeted from Synthesus 4.1 to Synthesus 5 and restricted to Codex-class or Google/Gemini CLI/CML models.

- [x]  Commit and push Phase 0 control-plane files to GitHub.

## Phase 1: CHAL Frame Contract

- [ ] 

- [x]  Define reusable CHAL task, plan, module message, checkpoint, telemetry, and firmware signal objects. Session log: 2026-05-30 Agent 6 PPBRS CHAL serialization.

- [ ]  Consolidate CHAL frame definitions into a stable package boundary shared by `packages/core`, `packages/reasoning`, and `packages/knowledge`.

- [x]  Add serialization/deserialization tests for CHAL frames. Session log: 2026-05-30 Agent 6 PPBRS CHAL serialization.

- [ ]  Add trace IDs and budget fields to every CHAL frame.

- [~]  Document CHAL frame schemas in `docs/modules/`. Session log: 2026-05-30 Agent 6 documented the PPBRS firmware-signal frame schema and round-trip validation; broader shared CHAL/core/knowledge schema docs remain.

## Phase 2: Cognitive Hypervisor MVP

- [x]  Implement `CognitiveHypervisor` as the central scheduler/control layer.

- [x]  Add route modes: fast path, grounded path, deep reasoning path, Quad Brain path, safety path.

- [x]  Add budget control for latency, retrieval depth, candidate count, and critic passes.

- [x]  Add per-device isolation and timeout handling. Session log: 2026-05-27 Agent 8 AIVM hypervisor isolation.

- [x]  Emit trace records for route decisions and budget exhaustion. Session log: 2026-05-27 Agent 8 AIVM hypervisor isolation.

- [x]  Add focused tests for route selection and timeout degradation. Session log: 2026-05-27 Agent 8 AIVM hypervisor isolation.

## Phase 3: Quad Brain MVP

- [~]  Implement Brain 1: Knowledge / Grounding as a CHAL device consumer. Session log: 2026-05-28 Agent 7 Quad Brain arbiter added `chal://knowledge/grounding` output frames inside serialized arbitration.

- [~]  Implement Brain 2: Executive Reasoning as planner/constraint controller. Session log: 2026-05-28 Agent 7 Quad Brain arbiter added `chal://reasoning/executive` plan frames.

- [~]  Implement Brain 3: CGPU Simulation / Rendering as candidate generator. Session log: 2026-05-28 Agent 7 Quad Brain arbiter now invokes `CGPURenderer` from the Quad Brain path.

- [~]  Implement Brain 4: Critic / Safety / Metacognition as evaluator/rewrite trigger. Session log: 2026-05-28 Agent 7 Quad Brain arbiter added critic/metacognition template-guard arbitration.

- [x]  Add serialized arbiter that merges four brain outputs into a single response frame. Session log: 2026-05-28 Agent 7 Quad Brain arbiter.

- [x]  Mirror serialized Quad Brain arbitration telemetry in OpenAPI/API schema docs as `QuadBrainArbitration` under `CognitiveHypervisorTrace.quad_brain`. Session log: 2026-05-31 Agent 10 Quad Brain trace schema.

- [x]  Add tests showing four-brain dispatch improves or preserves output quality over legacy dual-hemi path. Session log: 2026-05-30 Agent 7 Quad Brain quality-preservation regression.

## Phase 4: CGPU Render Accelerator

- [x]  Define `CGPUFrame` input/output contract. Session log: 2026-05-28 Agent 9 CGPU frame contract.

- [x]  Generate multiple candidate phrasings from grounded state. Session log: 2026-05-28 Agent 9 CGPU frame contract.

- [x]  Add persona/NPC behavior rendering mode. Session log: 2026-05-28 Agent 9 CGPU frame contract.

- [x]  Add business-bot concise answer rendering mode. Session log: 2026-05-28 Agent 9 CGPU frame contract.

- [x]  Add critic feedback loop for rewrite. Session log: 2026-05-28 Agent 9 CGPU frame contract.

- [x]  Ensure CGPU candidates never bypass grounding/safety arbitration. Session log: 2026-05-28 Agent 9 CGPU frame contract.

- [x]  Mirror `CGPUFrame` and `CGPUOutputFrame` in OpenAPI/API schema docs without claiming `/api/v1/query` emits them yet. Session log: 2026-05-28 Agent 10 API schema alignment.

## Phase 5: Knowledge Cloud Hardware Mount

- [ ] 

- \[\~\] Define CHAL mount and partition interfaces for ROM, parameter disk, grounding corpus, and writeback memory.
- [x]  Upgrade KAL into a CHAL memory controller. Session log: 2026-05-28 Knowledge Cloud mount table.

- [x]  Add mount table boot sequence. Session log: 2026-05-28 Knowledge Cloud mount table.

- [x]  Add partition integrity checks against Knowledge Cloud manifests. Session log: 2026-05-28 Knowledge Cloud mount table added runtime manifest SHA-256/size verification; 2026-05-28 Daily Knowledge Hardware Health Check tracked a current standalone artifact FAISS/embedder dim mismatch separately.

- [x]  Add cache locality and hot-context retrieval. Session log: 2026-05-30 Knowledge Hardware Hot-Context Validation.

- [ ]  Add provenance traces to final response metadata.

- [x]  Add tests for mounted Knowledge Cloud partitions. Session log: 2026-05-28 Knowledge Cloud mount table.

## Phase 6: Legacy Template Path Removal

- [ ] 

- \[\~\] Convert PPBRS normal-path output into non-user-facing firmware signals.

- [ ]  Search and classify every direct fallback/template response path.

- [ ]  Delete unused legacy response emitters.

- [~]  Quarantine safety/platform/explicit NPC-script templates behind labeled interfaces. Session log: 2026-05-28 Agent 4 template guard added `TemplateSurface` labels and hypervisor telemetry; remaining work is classifying older character/template emitters outside the Synthesus 5 hypervisor path.

- [x]  Add regression tests that fail on normal-path template leakage. Session log: 2026-05-28 Agent 4 template guard.

- [x]  Update module docs with the safety/template exception boundary. Session log: 2026-05-28 Agent 4 template guard.

## Phase 7: Memory And Cache Hierarchy

- [ ]  Define L1 turn cache, L2 session cache, L3 project/user cache, and L4 Knowledge Cloud cache.

- [ ]  Add writeback rules from reasoning traces into episodic/crystallized memory.

- [ ]  Add memory provenance and TTL policy.

- [~]  Add replayable trace storage for comparison harnesses. Session log: 2026-05-30 Agent 9 added deterministic organ-training trace replay metadata and scorecard coverage; broader runtime conversation trace replay remains.

- \[\~\] Add save/load tests across CHAL memory partitions. Session log: 2026-05-27 Agent 8 AIVM snapshot integrity added default VMD snapshot/restore parity and tamper rejection; broader CHAL partition save/load remains.

## Phase 8: GPT-4-Class Evaluation Harness

- [ ] 

- [x]  Add legacy-vs-CHAL conversation comparison harness. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add Synthesus 5 vs legacy comparison mode. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add cross-domain reasoning prompts. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add grounded retrieval prompts. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add NPC/persona behavior prompts. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add business-bot task prompts. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add scoring for usefulness, grounding, naturalness, latency, template leakage, and safety. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Store benchmark summaries in ignored artifacts and commit only harness source/docs. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

## Phase 9: Product Runtime Polish

- \[\~\] Wire Synthesus 5 path into API entrypoints. Session log: 2026-05-28 Agent 1 API CHAL mode added explicit `/api/v1/query` `mode="chal"` routing through `CognitiveHypervisor`; default `auto` cutover remains.

- [x]  Document the current `/api/v1/query` `mode="chal"` debug contract as `CognitiveHypervisorTrace` in OpenAPI/schema mirrors. Session log: 2026-05-29 Agent 10 hypervisor trace schema.

- [ ]  Add frontend control/trace view for CHAL route decisions.

- [ ]  Add NPC runtime toggle for Synthesus 5 path.

- [ ]  Add business-bot preset path.

- [ ]  Add graceful degraded-state messaging without legacy templates.

## Phase 10: Hardening And Release

- [ ]  Add full focused test suite for Synthesus 5 path.

- [ ]  Add smoke command that runs an end-to-end Synthesus 5 conversation.

- [ ]  Add performance baseline and regression guard.

- [ ]  Validate Knowledge Cloud bundle integrity from cold start.

- [ ]  Publish release notes describing Synthesus 5 behavior and limitations.

- [ ]  Tag a Synthesus 5 release candidate.

## Current Priority Queue

1. Wire `CognitiveHypervisor` into a public runtime/API entrypoint.
2. Connect Quad Brain dispatch to CHAL frames and CGPU rendering.
3. Add a mount table boot sequence with Knowledge Cloud manifest integrity checks.
4. Upgrade the comparison harness from 4.1 CHAL to explicit Synthesus 5 mode.
5. Complete the legacy template path audit and regression guard.
