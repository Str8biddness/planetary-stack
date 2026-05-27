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

- [x] Create Synthesus 5 CHAL blueprint with architecture, diagrams, terminology, and start-to-finish implementation plan.
- [x] Promote Synthesus 5 as the README-level active target.
- [x] Add root `AGENTS.md` so agent bootstrapping starts from Synthesus 5 law.
- [x] Update agent operating contract to make the blueprint non-negotiable.
- [x] Update handover protocol so every session reads the blueprint and checklist first.
- [x] Create this implementation checklist as the cross-agent progress ledger.
- [x] Ensure all scheduled automations are retargeted from Synthesus 4.1 to Synthesus 5 and restricted to Codex-class or Google/Gemini CLI/CML models.
- [x] Commit and push Phase 0 control-plane files to GitHub.

## Phase 1: CHAL Frame Contract

- [~] Define reusable CHAL task, plan, module message, checkpoint, telemetry, and firmware signal objects.
- [ ] Consolidate CHAL frame definitions into a stable package boundary shared by `packages/core`, `packages/reasoning`, and `packages/knowledge`.
- [ ] Add serialization/deserialization tests for CHAL frames.
- [ ] Add trace IDs and budget fields to every CHAL frame.
- [ ] Document CHAL frame schemas in `docs/modules/`.

## Phase 2: Cognitive Hypervisor MVP

- [x] Implement `CognitiveHypervisor` as the central scheduler/control layer.
- [x] Add route modes: fast path, grounded path, deep reasoning path, Quad Brain path, safety path.
- [x] Add budget control for latency, retrieval depth, candidate count, and critic passes.
- [ ] Add per-device isolation and timeout handling.
- [~] Emit trace records for route decisions and budget exhaustion.
- [ ] Add focused tests for route selection and timeout degradation.

## Phase 3: Quad Brain MVP

- [ ] Implement Brain 1: Knowledge / Grounding as a CHAL device consumer.
- [ ] Implement Brain 2: Executive Reasoning as planner/constraint controller.
- [ ] Implement Brain 3: CGPU Simulation / Rendering as candidate generator.
- [ ] Implement Brain 4: Critic / Safety / Metacognition as evaluator/rewrite trigger.
- [ ] Add serialized arbiter that merges four brain outputs into a single response frame.
- [ ] Add tests showing four-brain dispatch improves or preserves output quality over legacy dual-hemi path.

## Phase 4: CGPU Render Accelerator

- [ ] Define `CGPUFrame` input/output contract.
- [ ] Generate multiple candidate phrasings from grounded state.
- [ ] Add persona/NPC behavior rendering mode.
- [ ] Add business-bot concise answer rendering mode.
- [ ] Add critic feedback loop for rewrite.
- [ ] Ensure CGPU candidates never bypass grounding/safety arbitration.

## Phase 5: Knowledge Cloud Hardware Mount

- [~] Define CHAL mount and partition interfaces for ROM, parameter disk, grounding corpus, and writeback memory.
- [~] Upgrade KAL into a CHAL memory controller.
- [ ] Add mount table boot sequence.
- [ ] Add partition integrity checks against Knowledge Cloud manifests.
- [ ] Add cache locality and hot-context retrieval.
- [ ] Add provenance traces to final response metadata.
- [ ] Add tests for mounted Knowledge Cloud partitions.

## Phase 6: Legacy Template Path Removal

- [~] Convert PPBRS normal-path output into non-user-facing firmware signals.
- [ ] Search and classify every direct fallback/template response path.
- [ ] Delete unused legacy response emitters.
- [ ] Quarantine safety/platform/explicit NPC-script templates behind labeled interfaces.
- [ ] Add regression tests that fail on normal-path template leakage.
- [ ] Update module docs with the safety/template exception boundary.

## Phase 7: Memory And Cache Hierarchy

- [ ] Define L1 turn cache, L2 session cache, L3 project/user cache, and L4 Knowledge Cloud cache.
- [ ] Add writeback rules from reasoning traces into episodic/crystallized memory.
- [ ] Add memory provenance and TTL policy.
- [ ] Add replayable trace storage for comparison harnesses.
- [ ] Add save/load tests across CHAL memory partitions.

## Phase 8: GPT-4-Class Evaluation Harness

- [~] Add legacy-vs-CHAL conversation comparison harness.
- [ ] Add Synthesus 5 vs legacy comparison mode.
- [ ] Add cross-domain reasoning prompts.
- [ ] Add grounded retrieval prompts.
- [ ] Add NPC/persona behavior prompts.
- [ ] Add business-bot task prompts.
- [ ] Add scoring for usefulness, grounding, naturalness, latency, template leakage, and safety.
- [ ] Store benchmark summaries in ignored artifacts and commit only harness source/docs.

## Phase 9: Product Runtime Polish

- [ ] Wire Synthesus 5 path into API entrypoints.
- [ ] Add frontend control/trace view for CHAL route decisions.
- [ ] Add NPC runtime toggle for Synthesus 5 path.
- [ ] Add business-bot preset path.
- [ ] Add graceful degraded-state messaging without legacy templates.

## Phase 10: Hardening And Release

- [ ] Add full focused test suite for Synthesus 5 path.
- [ ] Add smoke command that runs an end-to-end Synthesus 5 conversation.
- [ ] Add performance baseline and regression guard.
- [ ] Validate Knowledge Cloud bundle integrity from cold start.
- [ ] Publish release notes describing Synthesus 5 behavior and limitations.
- [ ] Tag a Synthesus 5 release candidate.

## Current Priority Queue

1. Finish Phase 0 by retargeting automations and pushing docs.
2. Build the `CognitiveHypervisor` MVP.
3. Upgrade the comparison harness from 4.1 CHAL to explicit Synthesus 5 mode.
4. Complete the legacy template path audit and regression guard.
5. Connect Quad Brain dispatch to CHAL frames and CGPU rendering.
