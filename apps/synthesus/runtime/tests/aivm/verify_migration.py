import asyncio
import sys
import os
from pathlib import Path

# Absolute Pathing for Monorepo Packages
PROJ_ROOT = Path("/home/dakin/Desktop/Synthesus_4.0")
PACKAGES_DIR = PROJ_ROOT / "packages"

# THE HYBRID PATH
# Add 'packages' to find packages (aivm, core, etc.)
# Add 'packages/core', 'packages/knowledge', etc. to find modules (hemisphere_bridge, etc.)
# BUT do NOT add 'packages/aivm' to avoid shadowing the 'aivm' package.
paths_to_add = [
    str(PACKAGES_DIR),
    str(PACKAGES_DIR / "core"),
    str(PACKAGES_DIR / "knowledge"),
    str(PACKAGES_DIR / "reasoning"),
    str(PACKAGES_DIR / "kernel"),
    "/home/dakin/drive_A/synthesus3.0/venv/lib/python3.12/site-packages"
]

for p in reversed(paths_to_add):
    if p not in sys.path:
        sys.path.insert(0, p)

from synth_runtime import SynthRuntime
from aivm.kernel.types import PersonaIdentity, SchedulerClass

async def verify_migration():
    print("--- AIVM NPC Migration Verification ---")
    runtime = SynthRuntime(data_dir="/tmp/aivm_test_data")
    
    # 1. Create Character (This should spawn NPC in Kernel)
    print("[1/3] Creating character 'migrated_npc'...")
    runtime.create_character(
        character_id="migrated_npc",
        name="Migrated NPC",
        archetype="test_archetype"
    )
    
    # 2. Check if NPC exists in AIVM Kernel
    npc = runtime._aivm_kernel._npcs.get("migrated_npc")
    if npc:
        print(f"      SUCCESS: NPC found in kernel with {len(npc.mounted_devices)} devices.")
    else:
        print("      FAILURE: NPC not found in kernel.")
        sys.exit(1)
        
    # 3. Execute 'respond' (This should trigger kernel tick)
    print("[2/3] Executing 'respond' via AIVM Kernel...")
    result = await runtime.respond_async("migrated_npc", "Hello kernel!")
    print(f"      NPC Response: {result.final_response}")
    
    # 4. Verify Audit Stream
    print("[3/3] Verifying audit stream for the tick...")
    audit_trace = [e.step for e in npc.audit_stream if e.step != "spawn"]
    print(f"      Audit Trace: {audit_trace}")
    
    if "admission" in audit_trace and "emit" in audit_trace:
        print("\n✅ SUCCESS: NPC successfully migrated to AIVM Kernel.")
        print("      - Character spawned formally.")
    else:
        print("\n❌ FAILURE: Audit trace incomplete.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(verify_migration())
