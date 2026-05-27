# AGENTS.md
# Synthesus 5 CHAL - Core Package Agent Handoff

Core-package work is governed first by the repo-root `AGENTS.md`, `README.md`, `docs/roadmap/SYNTHESUS_5_CHAL_BLUEPRINT.md`, and `docs/roadmap/SYNTHESUS_5_IMPLEMENTATION_CHECKLIST.md`.

For `packages/core/`, the active target is the Synthesus 5 control plane:

- Cognitive Hypervisor orchestration.
- Quad Brain dispatch and serialized arbitration.
- CHAL memory/cache/parameter interfaces.
- CGPU render handoff.
- critic/metacognitive rewrite loop.
- deletion or quarantine of normal-path template fallback behavior.

Update the Synthesus 5 checklist and `docs/agents/AGENT_LOG.md` before ending any core-package session.

## 🏛 Architectural Spine: AIVM ↔ NPC Contract
Every agent session MUST read and adhere to the [AIVM ↔ NPC Contract](../../docs/architecture/AIVM_NPC_CONTRACT.md). This document defines the authoritative runtime contract between NPCs and the AIOS kernel.

### Non-Negotiable Invariants:
1. **Kernel Mediation**: All device calls (Memory, Persona, Knowledge) MUST flow through the kernel.
2. **12-Step Sequence**: Every NPC tick MUST follow the canonical sequence defined in §5 of the contract.
3. **Strict Isolation**: Cross-NPC memory or knowledge reach is a contract violation.

## 🛠 Active Package Map
- `packages/kernel/`: C++ hardware drivers and pybind11 bridges.
- `packages/aivm/`: NPC Runtime implementation (Contract Spine).
- `packages/core/`: High-level orchestrators and SynthRuntime.
- `packages/knowledge/`: KAL/KN data layers.
- `packages/reasoning/`: Causal simulation and pattern synthesis.

## 🚧 Current Mission
Transitioning the system to the formal AIVM NPC Runtime.
1. [DONE] Land Contract v0.1.
2. [DONE] Implement `packages/aivm/kernel/` core orchestration.
3. [DONE] Implement `packages/aivm/devices/` interface stubs.
4. [DONE] Implement `packages/aivm/snapshot/` and `packages/aivm/isolation/` layers.
5. [DONE] Implement `packages/aivm/scheduler/` for priority-based multi-NPC ticks.
6. [DONE] Implement `aivm/devices/vdd.py` and Computress Virtual Computer MVP (Phase 1).
7. [DONE] Migrate `SynthRuntime` to use the formal AIVM Kernel (Verified).
