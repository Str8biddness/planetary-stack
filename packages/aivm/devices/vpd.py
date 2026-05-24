from __future__ import annotations
import json
import hashlib
from typing import Dict, Any, Optional
from .base import Device
from ..kernel.types import PersonaIdentity

class VPD(Device):
    """
    Virtual Persona Device - §3.1
    Identity, traits, voice, role, snapshot/restore.
    """
    
    def __init__(self, identity: PersonaIdentity, 
                 traits: Optional[Dict[str, float]] = None,
                 role: str = "default",
                 voice_profile: Optional[Dict[str, Any]] = None):
        self._identity = identity
        self._traits = traits or {}
        self._role = role
        self._voice_profile = voice_profile or {}

    def identity(self) -> PersonaIdentity:
        return self._identity

    def traits(self) -> Dict[str, float]:
        return self._traits

    def role(self) -> str:
        return self._role

    def voice_profile(self) -> Dict[str, Any]:
        return self._voice_profile

    def snapshot(self) -> bytes:
        data = {
            "identity": {
                "id": self._identity.id,
                "name": self._identity.name,
                "archetype": self._identity.archetype,
                "version": self._identity.version
            },
            "traits": self._traits,
            "role": self._role,
            "voice": self._voice_profile
        }
        return json.dumps(data, sort_keys=True).encode()

    def restore(self, blob: bytes) -> None:
        data = json.loads(blob.decode())
        self._identity = PersonaIdentity(**data["identity"])
        self._traits = data["traits"]
        self._role = data["role"]
        self._voice_profile = data["voice"]

    def fingerprint(self) -> str:
        return hashlib.sha256(self.snapshot()).hexdigest()
