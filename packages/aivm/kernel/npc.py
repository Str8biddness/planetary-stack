from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Any
from .types import PersonaIdentity, SchedulerClass, ResourceQuota, AuditEntry, PermissionLevel
from ..devices.base import Device

@dataclass
class NPC:
    """
    Bounded Synthetic Intelligence Node.
    Defined by §2 of the AIVM ↔ NPC Contract.
    """
    identity: PersonaIdentity
    scheduler_class: SchedulerClass
    resource_quota: ResourceQuota
    permission_level: PermissionLevel = PermissionLevel.GUEST
    mounted_devices: Dict[str, Device] = field(default_factory=dict)
    audit_stream: List[AuditEntry] = field(default_factory=list)

    def add_audit(self, step: str, details: Dict[str, Any]):
        from datetime import datetime, timezone
        from ..inspector.service import get_inspector
        import asyncio
        
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            step=step,
            details=details,
            npc_id=self.identity.id
        )
        self.audit_stream.append(entry)
        
        # Async broadcast to inspector
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(get_inspector().broadcast_event(self.identity.id, step, {
                **details,
                "timestamp": entry.timestamp
            }))
        except RuntimeError:
            pass # No loop running
