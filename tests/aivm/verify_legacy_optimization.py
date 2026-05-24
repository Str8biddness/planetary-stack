import asyncio
import sys
import os
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
from aivm.kernel.types import PermissionLevel, SchedulerClass

async def verify_legacy_optimization():
    print("--- AIVM Legacy Character Optimization Verification ---")
    runtime = SynthRuntime(data_dir="/tmp/aivm_legacy_test")
    
    # 1. Load Legacy Character 'synth' (which was optimized)
    print("[1/3] Loading optimized legacy character 'synth'...")
    runtime.load_character("synth")
    
    # 2. Check if NPC exists in AIVM Kernel with correct 4.0 metadata
    npc = runtime._aivm_kernel._npcs.get("synth")
    if npc:
        print(f"      SUCCESS: NPC 'synth' found in kernel.")
        print(f"      Permission: {npc.permission_level.value}")
        print(f"      Scheduler: {npc.scheduler_class.value}")
        print(f"      Devices: {list(npc.mounted_devices.keys())}")
        
        assert npc.permission_level == PermissionLevel.AGENT
        assert npc.scheduler_class == SchedulerClass.REALTIME_PRINCIPAL
        assert "VTD" in npc.mounted_devices
    else:
        print("      FAILURE: NPC 'synth' not found in kernel.")
        sys.exit(1)
        
    # 3. Verify 'breach' (Agent/Principal)
    print("[2/3] Loading optimized legacy character 'breach'...")
    runtime.load_character("breach")
    b_npc = runtime._aivm_kernel._npcs.get("breach")
    assert b_npc.permission_level == PermissionLevel.AGENT
    print("      SUCCESS: 'breach' authorized as AGENT.")

    # 4. Verify 'garen' (Guest/Supporting)
    print("[3/3] Loading optimized legacy character 'garen'...")
    runtime.load_character("garen")
    g_npc = runtime._aivm_kernel._npcs.get("garen")
    assert g_npc.permission_level == PermissionLevel.GUEST
    assert g_npc.scheduler_class == SchedulerClass.REALTIME_SUPPORTING
    print("      SUCCESS: 'garen' bounded as GUEST.")

    print("\n✅ SUCCESS: Legacy Characters optimized and running in AIVM Kernel.")

if __name__ == "__main__":
    asyncio.run(verify_legacy_optimization())
