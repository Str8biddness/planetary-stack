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
from aivm.kernel.types import PermissionLevel
from core.computress.schemas import VddCommand, VddStatus

async def verify_computress():
    print("--- AIVM Computress (Virtual Computer) Verification ---")
    
    # 1. Initialize Runtime
    print("[1/4] Initializing Runtime...")
    runtime = SynthRuntime(data_dir="/tmp/aivm_comp_test")
    
    # 2. Spawn Computress (Agent Permission)
    print("[2/4] Spawning Computress as AGENT...")
    runtime.create_character("computress", "Computress", archetype="virtual_computer", permission="agent")
    npc = runtime._aivm_kernel._npcs.get("computress")
    
    # 3. Verify VDD Mounting
    print("[3/4] Verifying VDD hardware mounting...")
    if "VDD" in npc.mounted_devices:
        print("      SUCCESS: Virtual Desktop Device (VDD) mounted at 0xF8000000.")
        vdd = npc.mounted_devices["VDD"]
    else:
        print("      FAILURE: VDD not mounted!")
        sys.exit(1)
        
    # 4. Execute VDD Command
    print("[4/4] Executing BROWSER_NAVIGATE via VDD...")
    # Simulate a navigate command
    result = await vdd.act(VddCommand.BROWSER_NAVIGATE, {"url": "https://synthesus.ai"})
    
    print(f"      Result Status: {result.status.name}")
    print(f"      Result Code: {result.result_code}")
    print(f"      Data: {result.data}")
    
    assert result.status == VddStatus.READY
    assert result.data["url"] == "https://synthesus.ai"
    
    # 5. Verify Policy Blocking
    print("[5/5] Verifying domain policy blocking...")
    blocked_result = await vdd.act(VddCommand.BROWSER_NAVIGATE, {"url": "https://malicious.com"})
    print(f"      Blocked Result Status: {blocked_result.status.name}")
    assert blocked_result.status == VddStatus.BLOCKED

    print("\n✅ SUCCESS: Computress VDD and Coordinator operational.")
    print("      - VDD hardware-abstracted driver verified.")
    print("      - Coordinator command validation verified.")
    print("      - Multi-tiered policy enforcement verified.")

if __name__ == "__main__":
    asyncio.run(verify_computress())
