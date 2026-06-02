# AIVM ↔ NPC Contract

Status: Draft v0.1
Owner: Dakin Ellegood
Last updated: 2026-05-24
Scope: Defines the runtime contract between an NPC (bounded synthetic intelligence node) and the AIVM kernel inside Synthesus 4.0.

This document is the spine. If it is real, the AIOS-for-NPCs thesis is real. If it is aspirational, the thesis is aspirational. Every line below should be implementable, testable, and inspectable.

## 1. Purpose

Define, with no ambiguity, what an NPC is in Synthesus, what the kernel provides, what the NPC must implement, and how a single tick of NPC cognition flows from input to output.

This contract has three jobs:
1. Make the AIVM the real call path, not a parallel narrative beside Python code.
2. Give studios a stable, inspectable, snapshot-able NPC abstraction.
3. Constrain the platform's surface area so it stays bounded, auditable, and shippable.

## 2. Conceptual model

An NPC is a bounded synthetic intelligence node. Operationally, an NPC is the tuple:
`NPC = (identity, mounted_devices, scheduler_class, resource_quota, audit_stream)`

It is not a model. It is not a prompt. It is a process-isolated runtime with a set of virtual devices mapped into it. The model is one device among several. The prompt is state held by another device. Identity, memory, knowledge access, generation, narrative continuity, perception, and reasoning are each mediated through a typed device interface.

The kernel mediates every call. There is no path from one NPC to another, or from an NPC to a shared resource, that bypasses the kernel.

### 2.1 Devices an NPC is composed of

| Device | Symbol | Responsibility | Required? |
| :--- | :--- | :--- | :--- |
| **Virtual Persona Device** | **VPD** | Identity, traits, voice, role, snapshot/restore | Yes |
| **Virtual Memory Device** | **VMD** | Per-character episodic + working memory, quota | Yes |
| **Virtual Knowledge Device** | **VQD** | Grounded retrieval via KAL, scoped per character | Yes |
| **Virtual Generation Device** | **VGD** | Token generation with style enforcement and budget | Yes |
| **Virtual Narrative Device** | **VND** | Right-hemisphere narrative coherence over session | Yes |
| **Virtual Reasoning Device** | **VRD** | Planner / domain router / synthesizer | Yes |
| **Virtual SLLM Device** | **VSLLM** | Hot-swappable model backend selection | Yes |
| **Virtual Voice/Perception Unit** | **VVPU** | Multimodal IO (voice in/out, vision) | Optional |

### 2.2 Shared substrate vs isolated state

The kernel distinguishes two classes of resource:
1. **Shared substrate**: model weights, world lore in the knowledge cloud, shared organ backbone, shared embeddings. Read-mostly. Multiple NPCs may reference, never mutate directly.
2. **Isolated state**: VPD identity payload, VMD memory contents, VND narrative arc, VRD plan stack, conversation history, audit stream. Owned by exactly one NPC. The kernel guarantees no cross-NPC reach into this state.

## 3. Device interfaces

Implementations live under `packages/aivm/devices/`.

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

### 3.3 VQD — Virtual Knowledge Device
```python
class VQD(Device):
    def lookup(self, query: KnowledgeQuery) -> KnowledgeResult: ...
    def scope(self) -> KnowledgeScope: ...   # which sources this character may read
    def policy(self) -> RetrievalPolicy: ... # pruning, chain length, gating
    def snapshot(self) -> bytes: ...          # scope, policy, and lookup trace
    def restore(self, blob: bytes) -> None: ...
    def fingerprint(self) -> str: ...         # content hash of current knowledge-device state
```

### 3.4 VGD — Virtual Generation Device
```python
class VGD(Device):
    def generate(self, request: GenerationRequest) -> GenerationResult: ...
    def style(self) -> StyleConstraint: ...
    def budget(self) -> GenerationBudget: ...  # tokens, latency, cost ceiling
```

### 3.5 VND — Virtual Narrative Device
```python
class VND(Device):
    def open_arc(self, arc: NarrativeArc) -> ArcHandle: ...
    def advance(self, handle: ArcHandle, beat: Beat) -> None: ...
    def coherence_check(self, draft: str) -> CoherenceVerdict: ...
    def session_summary(self) -> NarrativeSummary: ...
```

### 3.6 VRD — Virtual Reasoning Device
```python
class VRD(Device):
    def plan(self, intent: Intent, context: Context) -> Plan: ...
    def route(self, plan: Plan) -> Route: ...    # which domain handlers / organs
    def synthesize(self, partials: list[Partial]) -> Synthesis: ...
```

### 3.7 VSLLM — Virtual SLLM Device
```python
class VSLLM(Device):
    def select(self, hint: ModelHint) -> ModelHandle: ...
    def call(self, handle: ModelHandle, prompt: Prompt) -> ModelResult: ...
    def tiers(self) -> list[ModelTier]: ...
```

## 5. Per-tick call sequence

1. **Admission**: Kernel admit tick for NPC_n under scheduler_class.
2. **Perception** (optional): VVPU.listen() / VVPU.see() → Perception.
3. **Intent resolution**: VRD.plan(intent, context) → Plan.
4. **Routing**: VRD.route(plan) → Route.
5. **Knowledge grounding**: VQD.lookup(query) → KnowledgeResult.
6. **Memory recall**: VMD.recall(query, k) → MemoryHits.
7. **Narrative gate (pre)**: VND.coherence_check(draft_plan) → verdict.
8. **Generation**: VSLLM.select(hint) → handle, VGD.generate() → draft.
9. **Narrative gate (post)**: VND.coherence_check(draft) → verdict.
10. **Memory commit**: VMD.write(event_describing_tick) → ref.
11. **Output emission**: Kernel returns final utterance + side-effects.
12. **Close**: Quotas reconciled. Scheduler updates.

## 11. Acceptance criteria

The contract is real when all of the following pass in CI:
1. Mount/unmount round-trip.
2. Per-tick sequence trace matches the 12-step sequence.
3. Isolation suite (No cross-NPC memory/VQD scope reach).
4. Snapshot/restore parity, including fingerprint verification before restore.
5. Quota enforcement.
6. Style enforcement.
7. Inspector exposure (< 100ms latency).
8. Chaos test (Device failure → SafeDefaultBehavior).

---
© 2026 AIVM LLC | Mission Critical Autonomous Intelligence
