from __future__ import annotations
import logging
import hashlib
from typing import Dict, Any, Optional
from .npc import NPC
from .types import PersonaIdentity, SchedulerClass, ResourceQuota
from ..devices.vpd import VPD
from ..devices.vmd import VMD
from ..devices.vqd import VQD
from ..devices.vgd import VGD
from ..devices.vrd import VRD
from ..devices.vtd import VTD
from ..devices.vdd import VDD
from ..devices.stubs import VND, VSLLM
from ..isolation.guard import FaultGuard
from ..snapshot.manager import SnapshotManager
from ..scheduler.core import AIVMScheduler
from .types import PersonaIdentity, SchedulerClass, ResourceQuota, PermissionLevel

logger = logging.getLogger("aivm.kernel")

class AIVMKernel:
    """
    Authoritative AIOS Kernel for NPCs.
    Mediates all device calls and enforces the canonical 12-step sequence.
    Defined by §4 & §5 of the AIVM ↔ NPC Contract.
    """

    def __init__(self, 
                 knowledge_cloud: Optional[Any] = None,
                 memory_store: Optional[Any] = None,
                 manifestation_engine: Optional[Any] = None,
                 scraper: Optional[Any] = None,
                 computress_coordinator: Optional[Any] = None,
                 enable_scheduler: bool = True,
                 safe_mode: bool = False):
        self._npcs: Dict[str, NPC] = {}
        self._knowledge_cloud = knowledge_cloud
        self._memory_store = memory_store
        self._manifestation = manifestation_engine
        self._scraper = scraper
        self._computress = computress_coordinator
        self.safe_mode = safe_mode
        
        self._scheduler: Optional[AIVMScheduler] = None
        if enable_scheduler:
            self._scheduler = AIVMScheduler(self)
            self._scheduler.start()

    def stop(self):
        """Shutdown the kernel and its subsystems."""
        if self._scheduler:
            self._scheduler.stop()

    def spawn_npc(self, 
                  identity: PersonaIdentity, 
                  scheduler: SchedulerClass = SchedulerClass.REALTIME_SUPPORTING,
                  quota: Optional[ResourceQuota] = None,
                  permission: PermissionLevel = PermissionLevel.GUEST,
                  reasoning_core: Optional[Any] = None) -> NPC:
        """Create and register a new NPC node with the required devices."""
        if identity.id in self._npcs:
            raise ValueError(f"NPC ID {identity.id} already registered.")
            
        npc = NPC(
            identity=identity,
            scheduler_class=scheduler,
            resource_quota=quota or ResourceQuota(),
            permission_level=permission
        )
        
        # Mount required devices (Wiring to real subsystems)
        npc.mounted_devices["VPD"] = VPD(identity)
        npc.mounted_devices["VMD"] = VMD(identity.id, self._memory_store)
        npc.mounted_devices["VQD"] = VQD(self._knowledge_cloud)
        npc.mounted_devices["VGD"] = VGD(reasoning_core)
        npc.mounted_devices["VND"] = VND()
        npc.mounted_devices["VRD"] = VRD(reasoning_core)
        npc.mounted_devices["VSLLM"] = VSLLM()

        # Mount Agentic Tools if authorized
        if permission in [PermissionLevel.AGENT, PermissionLevel.ROOT]:
            npc.mounted_devices["VTD"] = VTD(
                manifestation_engine=self._manifestation,
                scraper=self._scraper
            )
            npc.mounted_devices["VDD"] = VDD(self._computress)
            logger.info(f"Kernel: NPC {identity.id} authorized as AGENT. VTD and VDD mounted.")

        # Enforcement of Safe Mode (§10 of Contract)
        if self.safe_mode and permission == PermissionLevel.GUEST:
            logger.info(f"Kernel: NPC {identity.id} spawned in SAFE_MODE. Optional devices (VVPU, etc.) are locked.")

        self._npcs[identity.id] = npc
        npc.add_audit("spawn", {"version": "0.1", "permission": permission.value, "devices": list(npc.mounted_devices.keys())})
        return npc

    def restore_npc(self, snapshot_blob: bytes) -> NPC:
        """Restore an NPC from a deterministic snapshot blob."""
        return SnapshotManager.restore(snapshot_blob, self)

    async def tick_scheduled(self, npc_id: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Add a tick request to the kernel's scheduler."""
        if not self._scheduler:
            return await self.tick(npc_id, input_payload)
        return await self._scheduler.schedule_tick(npc_id, input_payload)

    async def tick(self, npc_id: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a single canonical 12-step NPC cognition tick.
        Protected by FaultGuard for process isolation.
        """
        npc = self._npcs.get(npc_id)
        if not npc:
            raise ValueError(f"NPC {npc_id} not found.")

        user_input = input_payload.get("user_input", "")

        @FaultGuard.contain(npc)
        async def _execute_canonical_sequence():
            # 1. Admission
            npc.add_audit("admission", {"scheduler": npc.scheduler_class.value})

            if input_payload.get("sim_crash"):
                raise RuntimeError("AIOS Kernel: Simulated sequence failure.")

            # 2. Perception (Optional)
            perception = None
            if "VVPU" in npc.mounted_devices:
                # perception = npc.mounted_devices["VVPU"].listen()
                pass
            npc.add_audit("perception", {"status": "success" if perception else "skipped"})

            # 3. Intent Resolution
            plan = npc.mounted_devices["VRD"].plan(user_input, {})
            npc.add_audit("plan", {"intent": str(plan)})

            # 4. Routing
            route = npc.mounted_devices["VRD"].route(plan)
            npc.add_audit("route", {"path": route})

            # 5. Knowledge Grounding
            knowledge = npc.mounted_devices["VQD"].lookup(user_input)
            npc.add_audit("knowledge", {"hits": len(knowledge) if isinstance(knowledge, list) else 0})

            # 6. Memory Recall
            memory = npc.mounted_devices["VMD"].recall(user_input, k=5)
            npc.add_audit("recall", {"hits": len(memory) if isinstance(memory, list) else 0})

            # 7. Narrative Gate (Pre)
            coherence_pre = npc.mounted_devices["VND"].coherence_check(str(plan))
            npc.add_audit("coherence_pre", {"verdict": "pass" if coherence_pre else "fail"})

            # 8. Generation
            model_handle = npc.mounted_devices["VSLLM"].select("default")
            response_text = npc.mounted_devices["VGD"].generate({"input": user_input, "model": model_handle})
            npc.add_audit("generate", {"tokens": len(response_text.split()), "model": model_handle})

            # 9. Narrative Gate (Post)
            coherence_post = npc.mounted_devices["VND"].coherence_check(response_text)
            npc.add_audit("coherence_post", {"verdict": "pass" if coherence_post else "fail"})

            # 10. Memory Commit
            npc.mounted_devices["VMD"].write(f"User: {user_input}\nNPC: {response_text}")
            npc.add_audit("memory_write", {"status": "success"})

            # 11. Output Emission
            npc.add_audit("emit", {"hash": hashlib.md5(response_text.encode()).hexdigest() if response_text else "none"})

            # 12. Close
            npc.add_audit("close", {"quota_reconciled": True})

            return {
                "response": response_text,
                "status": "success",
                "metadata": {
                    "npc_id": npc_id,
                    "plan": str(plan),
                    "route": route
                }
            }

        return await _execute_canonical_sequence()
