from __future__ import annotations
import json
import hashlib
from typing import Dict, Any, TYPE_CHECKING
from ..kernel.npc import NPC
from ..kernel.types import PersonaIdentity, SchedulerClass, ResourceQuota

if TYPE_CHECKING:
    from ..kernel.core import AIVMKernel

class SnapshotManager:
    """
    Handles deterministic, loss-less capture of NPC runtime state.
    Implements §7 of the AIVM ↔ NPC Contract.
    """
    
    CONTRACT_VERSION = 1

    @staticmethod
    def _fingerprint_payload(payload: Dict[str, Any]) -> str:
        unsigned = dict(payload)
        unsigned.pop("footer", None)
        json_payload = json.dumps(unsigned, sort_keys=True)
        return hashlib.sha256(json_payload.encode()).hexdigest()

    @staticmethod
    def capture(npc: NPC) -> bytes:
        """
        Snapshot all mounted devices and kernel state into a sealed blob.
        """
        # Header
        header = {
            "npc_id": npc.identity.id,
            "contract_version": SnapshotManager.CONTRACT_VERSION,
            "scheduler_class": npc.scheduler_class.value,
            "quota": {
                "memory_bytes": npc.resource_quota.memory_bytes,
                "max_tokens": npc.resource_quota.max_tokens,
                "max_reasoning_depth": npc.resource_quota.max_reasoning_depth,
                "latency_ceiling_ms": npc.resource_quota.latency_ceiling_ms
            }
        }

        # Device Blobs
        device_blobs = {}
        device_fingerprints = {}
        for name, device in npc.mounted_devices.items():
            device_blobs[name] = device.snapshot().hex() # Hex encode for JSON compatibility
            device_fingerprints[name] = device.fingerprint()

        # Payload
        payload = {
            "header": header,
            "devices": device_blobs,
            "device_fingerprints": device_fingerprints,
            "identity": {
                "name": npc.identity.name,
                "archetype": npc.identity.archetype,
                "version": npc.identity.version
            }
        }

        # Seal with fingerprint
        payload["footer"] = {
            "fingerprint": SnapshotManager._fingerprint_payload(payload),
            "signature": "AIVM_LLC_ALPHA"
        }

        return json.dumps(payload, sort_keys=True).encode()

    @staticmethod
    def restore(blob: bytes, kernel: AIVMKernel) -> NPC:
        """
        Restore an NPC from a snapshot blob in a fresh state.
        """
        data = json.loads(blob.decode())
        header = data["header"]
        footer = data.get("footer", {})
        expected_fingerprint = footer.get("fingerprint")
        actual_fingerprint = SnapshotManager._fingerprint_payload(data)

        if not expected_fingerprint or expected_fingerprint != actual_fingerprint:
            raise ValueError("Snapshot fingerprint mismatch")
        
        if header["contract_version"] != SnapshotManager.CONTRACT_VERSION:
            raise ValueError(f"Contract version mismatch: {header['contract_version']}")

        identity = PersonaIdentity(
            id=header["npc_id"],
            name=data["identity"]["name"],
            archetype=data["identity"]["archetype"],
            version=data["identity"]["version"]
        )

        quota = ResourceQuota(
            memory_bytes=header["quota"]["memory_bytes"],
            max_tokens=header["quota"]["max_tokens"],
            max_reasoning_depth=header["quota"]["max_reasoning_depth"],
            latency_ceiling_ms=header["quota"]["latency_ceiling_ms"]
        )

        # Re-spawn NPC via kernel
        npc = kernel.spawn_npc(
            identity=identity,
            scheduler=SchedulerClass(header["scheduler_class"]),
            quota=quota
        )

        # Restore Device States
        for name, device_hex in data["devices"].items():
            if name in npc.mounted_devices:
                npc.mounted_devices[name].restore(bytes.fromhex(device_hex))

        expected_fingerprints = data.get("device_fingerprints", {})
        for name, expected in expected_fingerprints.items():
            device = npc.mounted_devices.get(name)
            if device is None:
                raise ValueError(f"Snapshot missing restored device: {name}")
            if device.fingerprint() != expected:
                raise ValueError(f"Snapshot device fingerprint mismatch: {name}")

        npc.add_audit("restore", {"fingerprint": data["footer"]["fingerprint"]})
        return npc
