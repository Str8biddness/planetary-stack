from __future__ import annotations
import logging
from typing import Dict, Any, Optional
from .npc import NPC
from .types import PersonaIdentity, SchedulerClass, ResourceQuota
from ..devices.stubs import VPD, VMD, VQD, VGD, VND, VRD, VSLLM
from ..isolation.guard import FaultGuard
from ..snapshot.manager import SnapshotManager

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

    def restore_npc(self, snapshot_blob: bytes) -> NPC:
        """Restore an NPC from a deterministic snapshot blob."""
        return SnapshotManager.restore(snapshot_blob, self)

    async def tick(self, npc_id: str, input_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a single canonical 12-step NPC cognition tick.
        Protected by FaultGuard for process isolation.
        """
        npc = self._npcs.get(npc_id)
        if not npc:
            raise ValueError(f"NPC {npc_id} not found.")

        @FaultGuard.contain(npc)
        async def _execute_canonical_sequence():
            # 1. Admission
            npc.add_audit("admission", {"scheduler": npc.scheduler_class.value})

            if input_payload.get("sim_crash"):
                raise RuntimeError("AIOS Kernel: Simulated sequence failure.")

            # 2. Perception (Optional)
            npc.add_audit("perception", {"status": "skipped"})

            # 3. Intent Resolution
            npc.add_audit("plan", {"intent": "resolved"})

            # 4. Routing
            npc.add_audit("route", {"path": "default"})

            # 5. Knowledge Grounding
            npc.add_audit("knowledge", {"hits": 0})

            # 6. Memory Recall
            npc.add_audit("recall", {"hits": 0})

            # 7. Narrative Gate (Pre)
            npc.add_audit("coherence_pre", {"verdict": "pass"})

            # 8. Generation
            npc.add_audit("generate", {"tokens": 0})

            # 9. Narrative Gate (Post)
            npc.add_audit("coherence_post", {"verdict": "pass"})

            # 10. Memory Commit
            npc.add_audit("memory_write", {"ref": "committed"})

            # 11. Output Emission
            result = {"response": "AIOS Kernel: Step 11 Emitted."}
            npc.add_audit("emit", {"hash": "stub"})

            # 12. Close
            npc.add_audit("close", {"quota_reconciled": True})

            return result

        return await _execute_canonical_sequence()
