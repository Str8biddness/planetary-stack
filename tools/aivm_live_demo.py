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

    questions = [
        "Who bit the man?",          # LEFT symbolic   -> grounded
        "Is a dog an animal?",       # LEFT symbolic   -> grounded
        "Who chases the wolf?",      # RIGHT abstraction-> imagination (inferred)
        "tell me about the wolf and the fox",  # RIGHT Hopfield -> imagination (associative)
        "Who flies the airplane?",   # neither         -> ungrounded (declined)
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
        print(f"   hemisphere={core.last_mechanism:11} tag={tag:12} "
              f"conf={core.last_confidence:.2f} coherence_post={post}")
        print(f"   -> {shown}\n")

    kernel.stop()


if __name__ == "__main__":
    asyncio.run(main())
