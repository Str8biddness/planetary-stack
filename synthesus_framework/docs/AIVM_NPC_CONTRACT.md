# AIVM ↔ NPC Contract

**Status:** Draft v0.1
**Owner:** Dakin Ellegood
**Last updated:** 2026-05-24
**Scope:** Defines the runtime contract between an NPC (bounded synthetic intelligence node) and the AIVM kernel inside Synthesus 4.0.

This document is the spine. If it is real, the AIOS-for-NPCs thesis is real. If it is aspirational, the thesis is aspirational. Every line below should be implementable, testable, and inspectable.

---

## 1. Purpose

Define, with no ambiguity, what an NPC *is* in Synthesus, what the kernel *provides*, what the NPC *must implement*, and how a single tick of NPC cognition flows from input to output.

This contract has three jobs:

1. Make the AIVM the real call path, not a parallel narrative beside Python code.
2. Give studios a stable, inspectable, snapshot-able NPC abstraction.
3. Constrain the platform's surface area so it stays bounded, auditable, and shippable.

## 2. Conceptual model

An **NPC** is a bounded synthetic intelligence node. Operationally, an NPC is the tuple:

```markdown
NPC = (identity, mounted_devices, scheduler_class, resource_quota, audit_stream)
```

It is not a model. It is not a prompt. It is a process-isolated runtime with a set of virtual devices mapped into it. The model is one device among several. The prompt is state held by another device. Identity, memory, knowledge access, generation, narrative continuity, perception, and reasoning are each mediated through a typed device interface.

The kernel mediates every call. There is no path from one NPC to another, or from an NPC to a shared resource, that bypasses the kernel.

### 2.1 Devices an NPC is composed of

| Device | Symbol | Responsibility | Required? |
| --- | --- | --- | --- |
| Virtual Persona Device | `VPD` | Identity, traits, voice, role, snapshot/restore | Yes |
| Virtual Memory Device | `VMD` | Per-character episodic + working memory, with quota and audit | Yes |
| Virtual Knowledge Device | `VQD` | Grounded retrieval via KAL, scoped per character | Yes |
| Virtual Generation Device | `VGD` | Token generation with style enforcement and budget | Yes |
| Virtual Narrative Device | `VND` | Right-hemisphere narrative coherence over session | Yes |
| Virtual Reasoning Device | `VRD` | Planner / domain router / synthesizer | Yes |
| Virtual SLLM Device | `VSLLM` | Hot-swappable model backend selection | Yes |
| Virtual Voice/Perception Unit | `VVPU` | Multimodal IO (voice in/out, vision) | Optional |

An NPC with only the seven required devices is a fully functional character. `VVPU` is mounted only when the NPC needs multimodal IO.

### 2.2 Shared substrate vs isolated state

The kernel distinguishes two classes of resource:

- **Shared substrate** — model weights, world lore in the knowledge cloud, shared organ backbone, shared embeddings. Read-mostly. Multiple NPCs may reference, never mutate directly.
- **Isolated state** — VPD identity payload, VMD memory contents, VND narrative arc, VRD plan stack, conversation history, audit stream. Owned by exactly one NPC. The kernel guarantees no cross-NPC reach into this state.

A studio-visible rule of thumb: anything a character *knows about itself* is isolated. Anything a character *could look up* is shared and accessed through `VQD`.

## 3. Device interfaces

All interfaces are stable, typed, and versioned. Breaking changes require a contract version bump. Implementations live under `synthesus_framework/aivm/devices/`.

### 3.1 VPD — Virtual Persona Device

```python
class VPD(Device):
    def identity(self) -> PersonaIdentity: ...
    def traits(self) -> dict[str, float]: ...
    def voice_profile(self) -> VoiceProfile: ...
    def role(self) -> str: ...
    def snapshot(self) -> bytes: ...
    def restore(self, blob: bytes) -> None: ...
    def fingerprint(self) -> str: ...   # content hash of current persona state
```

**Invariants**

- `snapshot()` followed by `restore()` in a fresh process must produce a `fingerprint()` equal to the original.
- `identity()` is immutable after mount. Traits, voice, role may drift; identity may not.

### 3.2 VMD — Virtual Memory Device

```python
class VMD(Device):
    def write(self, event: MemoryEvent) -> MemoryRef: ...
    def recall(self, query: MemoryQuery, k: int) -> list[MemoryHit]: ...
    def forget(self, ref: MemoryRef) -> None: ...
    def quota(self) -> MemoryQuota: ...
    def audit(self) -> Iterator[MemoryAuditEntry]: ...
    def snapshot(self) -> bytes: ...
    def restore(self, blob: bytes) -> None: ...
```

**Invariants**

- Every `write`/`recall`/`forget` emits an audit entry. No silent memory mutation.
- `quota()` is enforced by the kernel, not by the device. The device only reports.
- Cross-NPC recall is impossible by construction. `recall` only sees this NPC's memory plus what `VQD` returns.

### 3.3 VQD — Virtual Knowledge Device

```python
class VQD(Device):
    def lookup(self, query: KnowledgeQuery) -> KnowledgeResult: ...
    def scope(self) -> KnowledgeScope: ...   # which sources this character may read
    def policy(self) -> RetrievalPolicy: ... # pruning, chain length, gating
```

**Invariants**

- `scope()` is set at mount time and is enforced by KAL, not by trust in the device.
- The blacksmith cannot retrieve from the wizard's grimoire unless its `scope()` allows it.
- All retrievals are logged to the NPC's audit stream.

### 3.4 VGD — Virtual Generation Device

```python
class VGD(Device):
    def generate(self, request: GenerationRequest) -> GenerationResult: ...
    def style(self) -> StyleConstraint: ...
    def budget(self) -> GenerationBudget: ...  # tokens, latency, cost ceiling
```

**Invariants**

- Style constraint is enforced device-side, not via prompt. Out-of-style output is rejected and regenerated or downgraded.
- Budget exhaustion returns a graceful degradation result (terse in-character reply), never a crash.

### 3.5 VND — Virtual Narrative Device

```python
class VND(Device):
    def open_arc(self, arc: NarrativeArc) -> ArcHandle: ...
    def advance(self, handle: ArcHandle, beat: Beat) -> None: ...
    def coherence_check(self, draft: str) -> CoherenceVerdict: ...
    def session_summary(self) -> NarrativeSummary: ...
```

**Invariants**

- A draft that breaks an open arc must be flagged before `VGD` finalizes output.
- Arcs survive snapshot/restore.

### 3.6 VRD — Virtual Reasoning Device

```python
class VRD(Device):
    def plan(self, intent: Intent, context: Context) -> Plan: ...
    def route(self, plan: Plan) -> Route: ...    # which domain handlers / organs
    def synthesize(self, partials: list[Partial]) -> Synthesis: ...
```

**Invariants**

- Every plan emits a trace consumable by the inspector.
- Planning is bounded in depth and time by `resource_quota.reasoning`.

### 3.7 VSLLM — Virtual SLLM Device

```python
class VSLLM(Device):
    def select(self, hint: ModelHint) -> ModelHandle: ...
    def call(self, handle: ModelHandle, prompt: Prompt) -> ModelResult: ...
    def tiers(self) -> list[ModelTier]: ...
```

**Invariants**

- Model selection is observable: which model served which call is part of the audit stream.
- Hot swap is non-destructive. An in-flight call completes on the prior handle.

### 3.8 VVPU — Virtual Voice/Perception Unit (optional)

```python
class VVPU(Device):
    def listen(self) -> Iterator[AudioFrame]: ...
    def speak(self, utterance: Utterance) -> None: ...
    def see(self, frame: VisionFrame) -> Perception: ...
```

## 4. Kernel responsibilities

The kernel provides exactly the following. NPCs may not assume anything else.

1. **Mount / unmount** devices into an NPC's address space.
2. **Route** every device call. The NPC never reaches a device directly; it issues a kernel call with a device handle.
3. **Enforce isolation** between NPCs. Two NPCs share only what the kernel explicitly routes through `VQD` or the shared substrate.
4. **Enforce quotas** per NPC: memory bytes, generation tokens, reasoning depth, per-tick latency.
5. **Schedule** NPCs across ticks under a stated scheduler class.
6. **Emit audit events** for every device call, mount, snapshot, restore, and quota event.
7. **Snapshot / restore** an entire NPC by snapshotting all mounted devices in a defined order.
8. **Recover from device errors** by routing to a safe-default behavior per device type.

The kernel does *not*:

- Hold persona-specific knowledge.
- Cache generation results across NPCs.
- Make model selection decisions (that is VSLLM's job).
- Interpret narrative content.

## 5. Per-tick call sequence

A single NPC tick. This is the canonical flow. Any production code path that diverges from this is a bug or a kernel-mediated extension.

```markdown
1. Kernel admits tick for NPC_n under scheduler_class.
   Kernel allocates tick budget (tokens, ms, reasoning depth).

2. Perception (optional)
   VVPU.listen() / VVPU.see() → Perception
   → audit("perception", payload_ref)

3. Intent resolution
   VRD.plan(intent, context) → Plan
   → audit("plan", plan_id)

4. Routing
   VRD.route(plan) → Route
   → audit("route", route_id)

5. Knowledge grounding
   For each step in route requiring facts:
     VQD.lookup(query) → KnowledgeResult
     → audit("knowledge", query_id, scope_ok)

6. Memory recall
   VMD.recall(query, k) → MemoryHits
   → audit("recall", query_id)

7. Narrative gate (pre)
   VND.coherence_check(draft_plan) → verdict
   → audit("coherence_pre", verdict)

8. Generation
   VSLLM.select(hint) → handle
   VGD.generate(request_built_from_steps_1_7) → draft
   → audit("generate", tokens, latency, model_handle)

9. Narrative gate (post)
   VND.coherence_check(draft) → verdict
   If reject and budget remains: regenerate (step 8) with constraint.
   If reject and budget exhausted: degrade gracefully.
   → audit("coherence_post", verdict)

10. Memory commit
    VMD.write(event_describing_tick) → ref
    → audit("memory_write", ref)

11. Output emission
    Kernel returns final utterance + side-effects to caller.
    → audit("emit", utterance_hash)

12. Kernel closes tick. Quotas reconciled. Scheduler updates.
```

No step in this sequence may be skipped except those marked optional. Skipping is a contract violation and must surface in the inspector.

## 6. Isolation guarantees

The kernel guarantees, and CI must verify, the following:

1. **No cross-NPC memory reach.** NPC A's `VMD.recall` never returns NPC B's events.
2. **No scope escape on** `VQD`**.** A retrieval outside `scope()` is refused at the kernel, not at the device.
3. **No shared mutable state outside the kernel.** Shared substrate is read-only from the NPC's perspective.
4. **No prompt injection bridge.** Content from `VQD` cannot rewrite `VPD` identity or `VND` arcs. Injection-shaped content is quarantined and surfaced to the audit stream.
5. **Process-level isolation minimum, KVM optional.** Crashing one NPC must not crash another or the host process.
6. **Audit streams are append-only and per-NPC.** A character's audit stream is owned by that character's runtime; the kernel writes; nobody else.

## 7. Snapshot / restore semantics

A snapshot is a deterministic, lossless capture of an NPC's full runtime state.

**Snapshot order (canonical):**

```markdown
snapshot(npc) =
  header(npc.id, contract_version, scheduler_class, quota)
  || VPD.snapshot()
  || VMD.snapshot()
  || VND.snapshot()
  || VRD.snapshot()
  || VSLLM.snapshot()      # selected tier, not model weights
  || VVPU.snapshot() if mounted
  || footer(fingerprint, signature)
```

**Restore requirements:**

- Restore in a fresh process. Resume an in-flight conversation. The next tick must be indistinguishable in behavior from a tick taken on the original process, given the same input.
- A snapshot is portable across machines that share the same shared substrate version.
- A snapshot is a single sealed blob with a content hash and an optional signature.

**Acceptance test:** snapshot mid-tick-9, kill the process, restore on a fresh process, run one more user turn, diff audit streams. The post-restore audit must continue cleanly from the snapshot point.

## 8. Scheduler and budgets

The kernel exposes scheduler classes per NPC:

| Class | Use case | Per-tick budget profile |
| --- | --- | --- |
| `realtime_principal` | Boss, key story NPC, voiced lead | Highest tokens, lowest latency ceiling, premium VSLLM tier |
| `realtime_supporting` | Quest-giver, named character | Mid tokens, mid latency, mid tier |
| `ambient` | Crowd, villager, background | Low tokens, relaxed latency, cheapest tier, may be coalesced |
| `offline` | Sim/training role, batch playback | No latency ceiling, full reasoning depth, audited |

**Hard rules:**

- Total per-frame NPC cost is capped by a frame budget. If the cast exceeds budget, `ambient` NPCs are skipped or coalesced *before* any `realtime_*` NPC is degraded.
- A `realtime_principal` NPC missing its tick is a logged incident, not a silent skip.

## 9. Error semantics

Every device call has three possible outcomes: `ok`, `degrade`, `fail`.

- `degrade` returns a typed, in-contract fallback (terse reply, empty recall, default plan). The tick continues.
- `fail` aborts the tick with a `SafeDefaultBehavior` selected by the NPC's `VPD` (e.g., "the innkeeper nods but says nothing"). The fail is audited. The NPC stays alive.
- The host process never crashes from a single NPC failure. Verified by chaos test in CI.

## 10. What this contract does NOT cover

Out of scope for v0.1. Listed explicitly so they cannot quietly creep into the contract.

- Training the underlying models. `VSLLM` consumes models; it does not produce them.
- World simulation outside NPC cognition. Physics, pathfinding, animation are the game engine's job.
- Multi-NPC dialogue choreography above the kernel. Belongs to a higher-level Director module, not the contract.
- Cross-session world memory. Belongs to KAL / world knowledge cloud, accessed via `VQD` scopes.
- Hardware-isolated KVM guests at the per-NPC level. The contract is satisfied by process isolation in v0.1. KVM is a v0.2 commitment if a buyer requires it.

## 11. Acceptance criteria

The contract is **real** when all of the following pass in CI on every commit to `main`:

1. **Mount/unmount round-trip** — mount the seven required devices, unmount, no leaks, kernel reports zero residual handles.
2. **Per-tick sequence trace** — a sample NPC produces an audit stream that matches the canonical 12-step sequence, in order, with no skipped non-optional steps.
3. **Isolation suite**
   - NPC A writes a secret memory. NPC B cannot recall it via any device.
   - NPC A's `VQD` cannot retrieve from a scope reserved to NPC B.
   - Crashing NPC A does not affect NPC B or the host.
4. **Snapshot/restore parity** — snapshot mid-tick, restore in a fresh process, identical fingerprint, next-turn audit continues cleanly.
5. **Quota enforcement** — an NPC attempting to exceed its memory or generation budget receives a `degrade` result, the kernel logs the event, the tick completes.
6. **Style enforcement** — a forced out-of-style generation is rejected by `VGD`, the regeneration path runs, the final output passes `VND.coherence_check`.
7. **Inspector exposure** — every device call from the per-tick sequence appears in the inspector for that NPC within 100 ms of emission.
8. **Chaos test** — induce `fail` on each device in turn; the host stays up; the NPC degrades to its `SafeDefaultBehavior`.

Until all eight pass, AIOS-for-NPCs is a thesis, not a product. When all eight pass, it is a product, and the pitch deck writes itself.

## 12. Versioning

- This document is **v0.1**.
- Contract version is a single integer, embedded in every snapshot header and every audit stream.
- Breaking changes to any device interface bump the contract version. Snapshots across versions are migrated by an explicit `kernel.migrate_snapshot(blob, from_version, to_version)` call. There is no implicit migration.

---

## Appendix A — Module placement

Implementation lives in:

```markdown
synthesus_framework/
  aivm/
    kernel/                # mount, route, isolate, schedule, audit
    devices/
      vpd.py
      vmd.py
      vqd.py
      vgd.py
      vnd.py
      vrd.py
      vsllm.py
      vvpu.py
    scheduler/
    isolation/
    snapshot/
    inspector/
  tests/
    aivm/
      test_mount_roundtrip.py
      test_tick_sequence.py
      test_isolation.py
      test_snapshot_restore.py
      test_quota.py
      test_style.py
      test_inspector.py
      test_chaos.py
```

Any code outside `aivm/` that reaches around the kernel is, by definition, a contract violation and must be migrated or deleted before v1.0.

## Appendix B — Open questions for v0.2

- Do `VQD` scopes compose? (Multiple inherited scopes, with explicit precedence.)
- Does `VND` arc state participate in cross-NPC scenes, or stay strictly per-NPC?
- KVM-per-NPC for UGC / mod-safe deployments — under what threat model is it required?
- Per-tick scheduler preemption — does an ambient NPC mid-generation get preempted, or run to completion at lower priority?

These are deliberately unresolved. Resolving them prematurely poisons the contract.