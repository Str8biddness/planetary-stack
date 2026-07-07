import asyncio
import sys
import logging
from pathlib import Path

# Absolute Pathing for Monorepo Packages
PROJ_ROOT = Path("/home/dakin/Desktop/Synthesus_4.0")
PACKAGES_DIR = PROJ_ROOT / "packages"

paths_to_add = [
    str(PACKAGES_DIR),
    str(PACKAGES_DIR / "core"),
    str(PACKAGES_DIR / "knowledge"),
    str(PACKAGES_DIR / "reasoning"),
    str(PACKAGES_DIR / "kernel"),
    str(PACKAGES_DIR / "aivm"),
    "/home/dakin/drive_A/synthesus3.0/venv/lib/python3.12/site-packages"
]
for p in reversed(paths_to_add):
    if p not in sys.path:
        sys.path.insert(0, p)

from synth_runtime import SynthRuntime

async def verify_agentic_iso():
    print("--- AIVM Agentic NPC (ISO Simulation) Verification ---")
    
    # 1. Initialize Runtime in GUEST_MODE (as if on ISO)
    # But we want to test if an AGENT can still use tools.
    print("[1/4] Initializing Runtime in ISO mode...")
    runtime = SynthRuntime(data_dir="/tmp/aivm_iso_test", guest_mode=True)
    
    # 2. Create a GUEST NPC (Bounded)
    print("[2/4] Spawning GUEST NPC 'villager'...")
    runtime.create_character("villager", "Villager", archetype="ambient", permission="guest")
    v_npc = runtime._aivm_kernel._npcs.get("villager")
    
    # 3. Create an AGENT NPC (Privileged)
    print("[3/4] Spawning AGENT NPC 'atlas'...")
    runtime.create_character("atlas", "Atlas", archetype="strategic", permission="agent")
    a_npc = runtime._aivm_kernel._npcs.get("atlas")
    
    # 4. Verify Device Mounting
    print("[4/4] Verifying device authorization...")
    
    # Villager should NOT have VTD
    if "VTD" not in v_npc.mounted_devices:
        print("      SUCCESS: Guest NPC has no VTD.")
    else:
        print("      FAILURE: Guest NPC has VTD mounted!")
        sys.exit(1)
        
    # Atlas SHOULD have VTD
    if "VTD" in a_npc.mounted_devices:
        print("      SUCCESS: Agent NPC has VTD mounted.")
        vtd = a_npc.mounted_devices["VTD"]
        # In a real ISO, manifestation_engine might be None if guest_mode is true.
        # BUT we want the Agent to be able to use it if the kernel has it.
        if runtime._aivm_kernel._manifestation is not None:
             print("      DEBUG: Manifestation Engine is available to Kernel.")
        else:
             print("      DEBUG: Manifestation Engine is None in Kernel (Guest Mode).")
    else:
        print("      FAILURE: Agent NPC has no VTD!")
        sys.exit(1)

    print("\n✅ SUCCESS: AIVM Dual-Mode Authorization verified for ISO.")
    print("      - Guests are strictly bounded (No VTD).")
    print("      - Agents are authorized for system tools (VTD Mounted).")

if __name__ == "__main__":
    asyncio.run(verify_agentic_iso())
