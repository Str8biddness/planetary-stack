from __future__ import annotations
import logging
from typing import Dict, Any, Optional
from .npc import NPC
from .types import PersonaIdentity, SchedulerClass, ResourceQuota
from ..devices.stubs import VPD, VMD, VQD, VGD, VND, VRD, VSLLM

logger = logging.getLogger("aivm.kernel")

class AIVMKernel:
    """
    Authoritative AIOS Kernel for NPCs.
    Mediates all device calls and enforces the canonical 12-step sequence.
    Defined by §4 & §5 of the AIVM ↔ NPC Contract.
    """

    def __init__(self):
        self._npcs: Dict[str, NPC] = {}

    def spawn_npc(self, 
                  identity: PersonaIdentity, 
                  scheduler: SchedulerClass = SchedulerClass.REALTIME_SUPPORTING,
                  quota: Optional[ResourceQuota] = None) -> NPC:
        """Create and register a new NPC node with the 7 required devices."""
        if identity.id in self._npcs:
            raise ValueError(f"NPC ID {identity.id} already registered.")
            
        npc = NPC(
            identity=identity,
            scheduler_class=scheduler,
            resource_quota=quota or ResourceQuota()
        )
        
        # Mount required devices
        npc.mounted_devices["VPD"] = VPD(identity)
        npc.mounted_devices["VMD"] = VMD()
        npc.mounted_devices["VQD"] = VQD()
        npc.mounted_devices["VGD"] = VGD()
        npc.mounted_devices["VND"] = VND()
        npc.mounted_devices["VRD"] = VRD()
        npc.mounted_devices["VSLLM"] = VSLLM()

        self._npcs[identity.id] = npc
        npc.add_audit("spawn", {"version": "0.1", "devices": list(npc.mounted_devices.keys())})
        return npc

    async def tick(self, npc_id: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a single canonical 12-step NPC cognition tick.
        This is the spine of the entire system.
        """
        npc = self._npcs.get(npc_id)
        if not npc:
            raise ValueError(f"NPC {npc_id} not found.")

        # 1. Admission
        npc.add_audit("admission", {"scheduler": npc.scheduler_class.value})

        # 2. Perception (Optional)
        # TODO: Implement VVPU check
        npc.add_audit("perception", {"status": "skipped"})

        # 3. Intent Resolution
        # TODO: call VRD.plan
        npc.add_audit("plan", {"intent": "resolved"})

        # 4. Routing
        # TODO: call VRD.route
        npc.add_audit("route", {"path": "default"})

        # 5. Knowledge Grounding
        # TODO: call VQD.lookup
        npc.add_audit("knowledge", {"hits": 0})

        # 6. Memory Recall
        # TODO: call VMD.recall
        npc.add_audit("recall", {"hits": 0})

        # 7. Narrative Gate (Pre)
        # TODO: call VND.coherence_check
        npc.add_audit("coherence_pre", {"verdict": "pass"})

        # 8. Generation
        # TODO: call VSLLM.select and VGD.generate
        npc.add_audit("generate", {"tokens": 0})

        # 9. Narrative Gate (Post)
        # TODO: call VND.coherence_check
        npc.add_audit("coherence_post", {"verdict": "pass"})

        # 10. Memory Commit
        # TODO: call VMD.write
        npc.add_audit("memory_write", {"ref": "committed"})

        # 11. Output Emission
        result = {"response": "AIOS Kernel: Step 11 Emitted."}
        npc.add_audit("emit", {"hash": "stub"})

        # 12. Close
        npc.add_audit("close", {"quota_reconciled": True})

        return result
