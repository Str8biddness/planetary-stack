#!/usr/bin/env python3
"""
Live AIVM tick with the VSA reasoning core mounted — Synthesus 5
================================================================

Proves the governance/reasoning runs inside the REAL kernel pipeline, not a demo
harness: spawns an NPC whose reasoning_core is SynthesusReasoningCore, runs the
canonical 12-step tick on real questions, and shows
  - VGD.generate producing a grounded answer (was a stub string), and
  - VND.coherence_check actually flipping pass/fail (was `return True`) —
    refusing to emit an ungrounded answer.

Run:  ./venv/bin/python tools/aivm_live_demo.py
"""
import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Telemetry shim: the kernel's audit hook imports the inspector (fastapi-based).
# fastapi isn't needed to run a tick, so provide a minimal stand-in.
if "fastapi" not in sys.modules:
    _f = types.ModuleType("fastapi")
    _f.WebSocket = type("WebSocket", (), {})
    sys.modules["fastapi"] = _f

from packages.aivm.kernel.core import AIVMKernel
from packages.aivm.kernel.types import PersonaIdentity, PermissionLevel
from packages.aivm.devices.synthesus_core import SynthesusReasoningCore


async def main():
    kernel = AIVMKernel(enable_scheduler=False)
    core = SynthesusReasoningCore()
    identity = PersonaIdentity(id="npc-1", name="Aria", archetype="scholar")
    kernel.spawn_npc(identity, permission=PermissionLevel.GUEST, reasoning_core=core)

    print("amplification router GOVERNS the hemispheres.")
    print("learned routing (hemisphere tried first, per query-type):")
    for d, h in core.routing_table().items():
        print(f"   {d:5} -> {h}")
    print()

    questions = [
        "Who bit the man?",          # who  -> symbolic first
        "Is a dog an animal?",       # isa  -> symbolic first
        "Who chases the wolf?",      # who  -> symbolic abstains, imagination inferred
        "tell me about the wolf and the fox",  # open -> hopfield FIRST (governed)
        "Who flies the airplane?",   # nothing grounds or imagines -> declined
    ]

    for q in questions:
        result = await kernel.tick("npc-1", {"user_input": q})
        npc = kernel._npcs["npc-1"]
        verds = {e.step: e.details for e in npc.audit_stream[-12:]}
        post = verds.get("coherence_post", {}).get("verdict")
        resp = result["response"]
        tag = core.last_groundedness.upper()
        shown = resp if resp != "[NO_GROUNDED_ANSWER]" else "(declined)"
        print(f"Q: {q}")
        print(f"   hemisphere={core.last_mechanism:11} attempts={core.last_attempts} "
              f"tag={tag:12} coherence_post={post}")
        print(f"   -> {shown}\n")

    kernel.stop()


if __name__ == "__main__":
    asyncio.run(main())
