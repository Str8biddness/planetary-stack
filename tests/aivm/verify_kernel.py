import asyncio
import sys
from pathlib import Path

# Add monorepo packages to path
PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJ_ROOT / "packages"))

from aivm.kernel.core import AIVMKernel
from aivm.kernel.types import PersonaIdentity, SchedulerClass

async def verify_canonical_sequence():
    print("--- AIVM Kernel Sequence Verification ---")
    kernel = AIVMKernel()
    identity = PersonaIdentity(id="test_npc", name="Test NPC", archetype="villager")
    
    # 1. Spawn NPC
    print("[1/3] Spawning NPC...")
    npc = kernel.spawn_npc(identity, scheduler=SchedulerClass.REALTIME_SUPPORTING)
    
    # 2. Execute Tick
    print("[2/3] Executing canonical 12-step tick...")
    await kernel.tick("test_npc", {"input": "hello"})
    
    # 3. Verify Audit Trace
    print("[3/3] Verifying audit trace...")
    audit_steps = [entry.step for entry in npc.audit_stream if entry.step != "spawn"]
    
    expected_sequence = [
        "admission", "perception", "plan", "route", "knowledge",
        "recall", "coherence_pre", "generate", "coherence_post",
        "memory_write", "emit", "close"
    ]
    
    if audit_steps == expected_sequence:
        print("\n✅ SUCCESS: AIVM Kernel correctly enforced the 12-step sequence.")
        for i, step in enumerate(audit_steps, 1):
            print(f"  {i}. {step}")
    else:
        print("\n❌ FAILURE: Audit trace mismatch.")
        print(f"Expected: {expected_sequence}")
        print(f"Actual:   {audit_steps}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(verify_canonical_sequence())
