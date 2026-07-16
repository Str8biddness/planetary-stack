from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

class SchedulerClass(Enum):
    REALTIME_PRINCIPAL = "realtime_principal"
    REALTIME_SUPPORTING = "realtime_supporting"
    AMBIENT = "ambient"
    OFFLINE = "offline"

class PermissionLevel(Enum):
    GUEST = "guest"     # Strictly bounded, no tool access
    AGENT = "agent"     # Capable of tool use and system calls
    ROOT = "root"       # Full kernel control (Reserved)

@dataclass
class ResourceQuota:
    memory_bytes: int = 1024 * 1024 * 10  # 10MB default
    max_tokens: int = 2048
    max_reasoning_depth: int = 5
    latency_ceiling_ms: int = 500

@dataclass
class AuditEntry:
    timestamp: str
    step: str
    details: Dict[str, Any] = field(default_factory=dict)
    npc_id: str = ""

@dataclass
class PersonaIdentity:
    id: str
    name: str
    archetype: str
    version: int = 1
