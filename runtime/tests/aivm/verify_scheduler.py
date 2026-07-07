import asyncio
import sys
import time
from pathlib import Path

# Absolute Pathing for Monorepo Packages
PROJ_ROOT = Path("/home/dakin/Desktop/Synthesus_4.0")
PACKAGES_DIR = PROJ_ROOT / "packages"

paths_to_add = [
    str(PACKAGES_DIR),
    str(PACKAGES_DIR / "core"),
    str(PACKAGES_DIR / "aivm"),
    "/home/dakin/drive_A/synthesus3.0/venv/lib/python3.12/site-packages"
]
for p in reversed(paths_to_add):
    if p not in sys.path:
        sys.path.insert(0, p)

from aivm.kernel.core import AIVMKernel
from aivm.kernel.types import PersonaIdentity, SchedulerClass

async def verify_scheduler():
    print("--- AIVM Scheduler Priority Verification ---")
    
    # Initialize Kernel with Scheduler (concurrency=1 for strict priority test)
    from aivm.scheduler.core import AIVMScheduler
    kernel = AIVMKernel(enable_scheduler=False) # Create manually to control concurrency
    scheduler = AIVMScheduler(kernel, concurrency_limit=1)
    kernel._scheduler = scheduler
    scheduler.start()
    
    # 1. Spawn NPCs with different priorities
    print("[1/3] Spawning NPCs (Principal, Supporting, Ambient)...")
    p_identity = PersonaIdentity(id="boss", name="Boss", archetype="lead")
    s_identity = PersonaIdentity(id="guard", name="Guard", archetype="support")
    a_identity = PersonaIdentity(id="villager", name="Villager", archetype="ambient")
    
    kernel.spawn_npc(p_identity, scheduler=SchedulerClass.REALTIME_PRINCIPAL)
    kernel.spawn_npc(s_identity, scheduler=SchedulerClass.REALTIME_SUPPORTING)
    kernel.spawn_npc(a_identity, scheduler=SchedulerClass.AMBIENT)
    
    # 2. Queue multiple ticks simultaneously
    print("[2/3] Queueing concurrent ticks (Ambient first, then Principal)...")
    
    results = []
    
    # We use a wrapper to track completion order
    async def run_tick(npc_id, label):
        start = time.time()
        await kernel.tick_scheduled(npc_id, {"user_input": "test"})
        end = time.time()
        results.append(npc_id)
        print(f"      - {label} ({npc_id}) finished.")

    # Fill the worker (concurrency=1) with Ambient
    # Then Principal should jump Supporting
    
    # Launch them almost together
    t1 = asyncio.create_task(run_tick("villager", "Ambient  "))
    await asyncio.sleep(0.05) # Ensure villager gets the first slot
    t2 = asyncio.create_task(run_tick("guard",    "Supporting"))
    t3 = asyncio.create_task(run_tick("boss",     "Principal "))
    
    await asyncio.gather(t1, t2, t3)
    
    # 3. Verify Execution Order
    print("[3/3] Verifying execution order...")
    # Expected order: villager (was first and got slot), boss (priority jump), guard
    expected_order = ["villager", "boss", "guard"]
    
    if results == expected_order:
        print("\n✅ SUCCESS: AIVM Scheduler enforced priority correctly.")
        print(f"      Execution Order: {' -> '.join(results)}")
    else:
        print("\n❌ FAILURE: Priority jump failed.")
        print(f"      Expected: {' -> '.join(expected_order)}")
        print(f"      Actual:   {' -> '.join(results)}")
        sys.exit(1)

    kernel.stop()

if __name__ == "__main__":
    asyncio.run(verify_scheduler())
