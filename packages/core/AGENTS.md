# AGENTS.md
# Synthesus 4.0 - Autonomous Agent Handoff

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
4. [TODO] Implement `packages/aivm/snapshot/` and `packages/aivm/isolation/` layers.
5. [TODO] Migrate existing `packages/core/` NPCs to use the AIVM Kernel.
