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

- [x]  Create this implementation checklist as the cross-agent progress ledger. Session log: 2026-06-03 Weekly Heavy Maintenance normalized malformed blank/escaped checklist markers after drift scan.

- [x]  Ensure all scheduled automations are retargeted from Synthesus 4.1 to Synthesus 5 and restricted to Codex-class or Google/Gemini CLI/CML models.

- [x]  Commit and push Phase 0 control-plane files to GitHub.

## Phase 1: CHAL Frame Contract


- [x]  Define reusable CHAL task, plan, module message, checkpoint, telemetry, and firmware signal objects. Session log: 2026-05-30 Agent 6 PPBRS CHAL serialization.

- [x]  Consolidate CHAL frame definitions into a stable package boundary shared by `packages/core`, `packages/reasoning`, and `packages/knowledge`. Session log: 2026-05-31 Agent 4 canonical `core.chal.frames` boundary.

- [x]  Add serialization/deserialization tests for CHAL frames. Session log: 2026-05-30 Agent 6 PPBRS CHAL serialization.

- [x]  Add trace IDs and budget fields to every CHAL frame. Session log: 2026-05-31 Agent 6 CHAL interface trace/budget metadata.

- [x]  Document CHAL frame schemas in `docs/modules/`. Session log: 2026-05-30 Agent 6 documented the PPBRS firmware-signal frame schema and round-trip validation; 2026-05-31 Agent 4 moved firmware frames to the shared `core.chal.frames` package boundary; 2026-05-31 Agent 6 documented the remaining core/KAL interface trace and budget metadata.

## Phase 2: Cognitive Hypervisor MVP

- [x]  Implement `CognitiveHypervisor` as the central scheduler/control layer.

- [x]  Add route modes: fast path, grounded path, deep reasoning path, Quad Brain path, safety path.

- [x]  Add budget control for latency, retrieval depth, candidate count, and critic passes.

- [x]  Add per-device isolation and timeout handling. Session log: 2026-05-27 Agent 8 AIVM hypervisor isolation.

- [x]  Emit trace records for route decisions and budget exhaustion. Session log: 2026-05-27 Agent 8 AIVM hypervisor isolation.

- [x]  Add focused tests for route selection and timeout degradation. Session log: 2026-05-27 Agent 8 AIVM hypervisor isolation.

## Phase 3: Quad Brain MVP

- [x]  Implement Brain 1: Knowledge / Grounding as a CHAL device consumer. Session log: 2026-05-28 Agent 7 Quad Brain arbiter added `chal://knowledge/grounding` output frames inside serialized arbitration; 2026-05-31 Agent 7 added per-role Quad Brain state transitions that expose Knowledge/Grounding inputs and outputs in trace metadata.

- [x]  Implement Brain 2: Executive Reasoning as planner/constraint controller. Session log: 2026-05-28 Agent 7 Quad Brain arbiter added `chal://reasoning/executive` plan frames; 2026-05-31 Agent 7 added trace-verified `executive.response_plan` and constraint state outputs.

- [x]  Implement Brain 3: CGPU Simulation / Rendering as candidate generator. Session log: 2026-05-28 Agent 7 Quad Brain arbiter now invokes `CGPURenderer` from the Quad Brain path; 2026-05-31 Agent 7 added trace-verified `cgpu.candidates` and `cgpu.selected_candidate` state outputs.

- [x]  Implement Brain 4: Critic / Safety / Metacognition as evaluator/rewrite trigger. Session log: 2026-05-28 Agent 7 Quad Brain arbiter added critic/metacognition template-guard arbitration; 2026-05-31 Agent 7 added trace-verified `critic.selected_response` and `critic.template_guard` final-output contract.

- [x]  Add serialized arbiter that merges four brain outputs into a single response frame. Session log: 2026-05-28 Agent 7 Quad Brain arbiter; 2026-06-01 Agent 7 added critic handoff proof tying `cgpu.selected_candidate` to `critic.selected_response` in inspectable trace metadata; 2026-06-02 Agent 7 added state-contract integrity checks for role completeness, serial ordering, transition mirroring, critic handoff, and final-output ownership.

- [x]  Mirror serialized Quad Brain arbitration telemetry in OpenAPI/API schema docs as `QuadBrainArbitration` under `CognitiveHypervisorTrace.quad_brain`. Session log: 2026-05-31 Agent 10 Quad Brain trace schema; 2026-06-01 Agent 10 typed `QuadBrainStateTransition` and the required final-output state contract fields.

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


- [x]  Define CHAL mount and partition interfaces for ROM, parameter disk, grounding corpus, provenance, cache, and writeback memory. Session log: 2026-05-31 Knowledge Hardware Complete Mount Interface; 2026-06-01 Agent 5 added artifact-free volatile cache/writeback mounts to manifest-backed boot.
- [x]  Upgrade KAL into a CHAL memory controller. Session log: 2026-05-28 Knowledge Cloud mount table.

- [x]  Add mount table boot sequence. Session log: 2026-05-28 Knowledge Cloud mount table; 2026-06-01 Agent 5 extended manifest-backed boot with `/mnt/cache/hot_context` and `/mnt/mem/writeback` CHAL boundaries; 2026-06-02 Agent 5 added manifest coverage reporting for known-but-absent Knowledge Cloud hardware partitions.

- [x]  Add partition integrity checks against Knowledge Cloud manifests. Session log: 2026-05-28 Knowledge Cloud mount table added runtime manifest SHA-256/size verification; 2026-05-28 Daily Knowledge Hardware Health Check tracked a current standalone artifact FAISS/embedder dim mismatch separately; 2026-06-01 Agent 5 added runtime cold-start retrieval-semantic integrity checks for FAISS/metadata counts and FAISS/embedder dimensions.

- [x]  Add cache locality and hot-context retrieval. Session log: 2026-05-30 Knowledge Hardware Hot-Context Validation.

- [x]  Add provenance traces to final response metadata. Session log: 2026-05-31 Knowledge Hardware Provenance Trace.

- [x]  Add tests for mounted Knowledge Cloud partitions. Session log: 2026-05-28 Knowledge Cloud mount table; 2026-06-01 Agent 5 validated volatile cache/writeback boundaries stay active and artifact-free; 2026-06-02 Agent 5 validated manifest coverage telemetry for missing optional and complete known artifact partitions.

- [x]  Add source-plane license/provenance validation for Knowledge Cloud hardware manifests before public sources can be treated as mounted CHAL substrate. Session log: 2026-06-01 Knowledge Cloud Source Provenance Gate; 2026-06-02 Knowledge Hardware Source-Manifest Fingerprint added `build.source_manifest` provenance fingerprints so stamped runtime bundles point back to the exact source-plane hash set; 2026-06-02 Knowledge Hardware Profile-Dim Gate made profile-aware build/stamp refuse internally aligned retrieval bundles whose persisted embedder dimension disagrees with the selected build profile.

## Phase 6: Legacy Template Path Removal


- [~] Convert PPBRS normal-path output into non-user-facing firmware signals. Session log: 2026-06-01 Agent 6 added fanout-aware PPBRS pattern candidate pruning so shared broad tokens no longer expand normal firmware matching to full-corpus scoring while preserving broad-token-only fallback behavior.

- [x]  Search and classify every direct fallback/template response path. Session log: 2026-05-31 Agent 6 template surface audit.

- [x]  Delete or convert unused legacy response emitters. Session log: 2026-06-02 Agent 6 converted the remaining legacy API emitters into labeled explicit NPC-script/non-user-facing storage boundaries and removed visible `[FALLBACK]` normal-path signatures from the FastAPI fallback stream.

- [x]  Quarantine safety/platform/explicit NPC-script templates behind labeled interfaces. Session log: 2026-05-28 Agent 4 template guard added `TemplateSurface` labels and hypervisor telemetry; 2026-06-01 generation spine fallback is now labeled as an explicit degraded state with non-legacy wording; 2026-06-01 Agent 4 labeled `ResponseCompositor` output as an explicit NPC-script surface with cognitive-engine debug metadata; 2026-06-02 Knowledge Hardware Hygiene run labeled `ELSBridge` candidate exports and integrations as non-user-facing `els_candidate_writeback` substrate; 2026-06-02 Agent 1 labeled `PatternEngine` learned templates as non-user-facing candidate storage with read-time backfill for legacy rows; 2026-06-02 Agent 4 labeled terminal `CognitiveEngine` character fallback and escalation-stall output as explicit NPC-script surfaces; 2026-06-02 Agent 6 labeled the remaining FastAPI and production API pattern/fallback surfaces as explicit NPC-script or non-user-facing storage boundaries, leaving 0 `legacy_quarantine_required` audit paths.

- [x]  Add regression tests that fail on normal-path template leakage. Session log: 2026-05-28 Agent 4 template guard.

- [x]  Update module docs with the safety/template exception boundary. Session log: 2026-05-28 Agent 4 template guard; 2026-06-02 Agent 10 mirrored legacy API `debug.template_surface` exceptions as the reusable `TemplateSurface` OpenAPI/API schema contract.

## Phase 7: Memory And Cache Hierarchy

- [x]  Define L1 turn cache, L2 session cache, L3 project/user cache, and L4 Knowledge Cloud cache. Session log: 2026-06-03 Knowledge Hardware Memory Policy added CHAL tier policies with mount paths, TTLs, provenance requirements, and focused tests.

- [~]  Add writeback rules from reasoning traces into episodic/crystallized memory. Session log: 2026-06-03 Knowledge Hardware Memory Policy added critic/provenance admission rules targeting `/mnt/mem/writeback`; 2026-06-03 Agent 4 added a focused CHAL memory writeback bridge that converts accepted hypervisor traces into provenance-bearing candidates, writes admitted episodic/semantic/procedural/working records through the memory store, and stages/adjoins crystallized candidates through `ConsciousState`; 2026-06-03 Agent 5 wired explicit CHAL/business-bot API calls to invoke the bridge after final Cognitive Hypervisor arbitration, emit typed `memory_writeback` telemetry, and reject degraded/template-rewritten traces before storage; remaining work is selecting non-API and crystallized-state production call sites for automatic bridge invocation.

- [x]  Add memory provenance and TTL policy. Session log: 2026-06-03 Knowledge Hardware Memory Policy added typed `MemoryProvenanceRef`, L1-L4 TTL policy, and writeback rejection reasons for missing/low-confidence provenance.

- [~]  Add replayable trace storage for comparison harnesses. Session log: 2026-05-30 Agent 9 added deterministic organ-training trace replay metadata and scorecard coverage; 2026-05-31 Agent 9 added an organ-evaluation quality gate for replay coverage, numeric consistency, and missing trained models; 2026-06-01 Agent 3 added compact Phase 8 runtime conversation replay JSONL records for the legacy-vs-Synthesus-5 harness; 2026-06-02 Agent 9 added CHAL accelerator frame metadata and coverage gating for current organ-training traces; 2026-06-02 Agent 9 added `organ-triad-replay-v3` candidate refs, selected-candidate refs, critic feedback refs, and a strict evaluator/selfImprove coverage gate; broader persistent runtime conversation trace storage remains.

- [~] Add save/load tests across CHAL memory partitions. Session log: 2026-05-27 Agent 8 AIVM snapshot integrity added default VMD snapshot/restore parity and tamper rejection; 2026-05-31 Agent 8 added per-device fingerprint manifests and restore verification across mounted AIVM devices; 2026-06-01 Agent 8 added explicit AIVM cache/writeback partition devices with snapshot restore parity and tamper rejection; 2026-06-02 Agent 8 added VQD knowledge-scope/policy lookup-trace snapshot restore and tamper rejection; broader persistent runtime trace storage remains.

## Phase 8: GPT-4-Class Evaluation Harness


- [x]  Add legacy-vs-CHAL conversation comparison harness. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add Synthesus 5 vs legacy comparison mode. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add cross-domain reasoning prompts. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add grounded retrieval prompts. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add NPC/persona behavior prompts. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add business-bot task prompts. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add scoring for usefulness, grounding, naturalness, latency, template leakage, and safety. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add a runnable latency baseline and regression guard for the legacy-vs-Synthesus-5 harness. Session log: 2026-05-31 Agent 3 Phase 8 latency regression guard.

- [x]  Store benchmark summaries in ignored artifacts and commit only harness source/docs. Session log: 2026-05-28 Agent 3 Phase 8 evaluation harness.

- [x]  Add compact replay trace records and explicit business-bot preset coverage to the legacy-vs-Synthesus-5 comparison harness. Session log: 2026-06-01 Agent 3 Phase 8 replay trace and business preset harness.

- [x]  Add a deterministic GPT-4-class reference expectation scorecard gate for the legacy-vs-Synthesus-5 comparison harness. Session log: 2026-06-02 Agent 3 Phase 8 reference scorecard gate.

- [x]  Add a per-case axis-improvement gate so the legacy-vs-Synthesus-5 harness fails when an individual case regresses on grounding, naturalness, safety, template leakage, or overall score even if aggregate metrics still pass. Session log: 2026-06-03 Agent 3 Phase 8 axis-improvement scorecard gate.

## Phase 9: Product Runtime Polish

- [~] Wire Synthesus 5 path into API entrypoints. Session log: 2026-05-28 Agent 1 API CHAL mode added explicit `/api/v1/query` `mode="chal"` routing through `CognitiveHypervisor`; default `auto` cutover remains.

- [x]  Document the current `/api/v1/query` `mode="chal"` debug contract as `CognitiveHypervisorTrace` in OpenAPI/schema mirrors. Session log: 2026-05-29 Agent 10 hypervisor trace schema; 2026-06-02 Agent 10 documented the `business_bot` preset and canonical runtime-preset normalization in API/schema mirrors.

- [ ]  Add frontend control/trace view for CHAL route decisions.

- [ ]  Add NPC runtime toggle for Synthesus 5 path.

- [x]  Add business-bot preset path. Session log: 2026-06-01 Agent 1 business-bot CHAL preset path.

- [x]  Add graceful degraded-state messaging without legacy templates. Session log: 2026-06-03 Agent 1 typed CHAL degraded-state contract.

## Phase 10: Hardening And Release

- [x]  Add full focused test suite for Synthesus 5 path. Session log: 2026-05-31 Agent 1 focused release suite.

- [x]  Add smoke command that runs an end-to-end Synthesus 5 conversation. Session log: 2026-05-31 Agent 1 CHAL API smoke command.

- [x]  Add performance baseline and regression guard. Session log: 2026-05-31 Agent 3 Phase 8 latency regression guard.

- [x]  Validate Knowledge Cloud bundle integrity from cold start. Session log: 2026-05-31 Agent 5 Knowledge Cloud cold-start integrity gate.

- [~]  Restore Knowledge Cloud golden-query health after artifact rebuild. Blocker note: 2026-06-01 Daily Knowledge Hardware Health Check confirmed manifest/source/bootstrap/cold-start mount validation passes, but golden-query retrieval fails because the current `synthesus-knowledge-cloud/artifacts/faiss.index` is 384-dimensional while `artifacts/models/swarm_embedder.pkl` persists `dim=128`; fix requires regenerating aligned generated artifacts, not a runtime source edit. Session log: 2026-06-01 Knowledge Cloud Provenance Stamp Guard added a source-only hardening gate so `synthesus-kc build --execute` and `synthesus-kc stamp-manifest` refuse to stamp provenance over that semantic mismatch; 2026-06-01 Agent 5 upgraded the Synthesus runtime cold-start gate to fail the same mismatch before declaring mounted Knowledge Cloud hardware ready; 2026-06-02 Daily Knowledge Hardware Health Check aligned the fast health check with the mount-table semantic gate so golden queries are skipped until FAISS/embedder dimensions match; 2026-06-03 Daily Knowledge Hardware Health Check reconfirmed source validation and KAL/mount health pass, while bundle/golden-query health remains blocked by the same FAISS/embedder mismatch and the live artifact manifest is not yet re-stamped with `build.source_manifest`.

- [ ]  Publish release notes describing Synthesus 5 behavior and limitations.

- [ ]  Tag a Synthesus 5 release candidate.

## Current Priority Queue

1. Wire `CognitiveHypervisor` into a public runtime/API entrypoint.
2. Connect Quad Brain dispatch to CHAL frames and CGPU rendering.
3. Add a mount table boot sequence with Knowledge Cloud manifest integrity checks.
4. Upgrade the comparison harness from 4.1 CHAL to explicit Synthesus 5 mode.
5. Complete the legacy template path audit and regression guard.
