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
    REPLAY_TRACE_VERSION = "aivm.snapshot_replay.v1"
    DEVICE_MANIFEST_VERSION = "aivm.device_manifest.v1"
    CANONICAL_TICK_SEQUENCE = [
        "admission",
        "perception",
        "plan",
        "route",
        "knowledge",
        "recall",
        "coherence_pre",
        "generate",
        "coherence_post",
        "memory_write",
        "emit",
        "close",
    ]

    @staticmethod
    def _fingerprint_payload(payload: Dict[str, Any]) -> str:
        unsigned = dict(payload)
        unsigned.pop("footer", None)
        json_payload = json.dumps(unsigned, sort_keys=True)
        return hashlib.sha256(json_payload.encode()).hexdigest()

    @staticmethod
    def _fingerprint_replay_events(events: list[dict[str, Any]]) -> str:
        json_payload = json.dumps(events, sort_keys=True)
        return hashlib.sha256(json_payload.encode()).hexdigest()

    @staticmethod
    def _fingerprint_replay_record(record: dict[str, Any]) -> str:
        unsigned = dict(record)
        unsigned.pop("record_hash", None)
        json_payload = json.dumps(unsigned, sort_keys=True)
        return hashlib.sha256(json_payload.encode()).hexdigest()

    @staticmethod
    def _fingerprint_device_manifest(manifest: dict[str, Any]) -> str:
        unsigned = dict(manifest)
        unsigned.pop("manifest_hash", None)
        json_payload = json.dumps(unsigned, sort_keys=True)
        return hashlib.sha256(json_payload.encode()).hexdigest()

    @staticmethod
    def build_device_manifest(device_blobs: dict[str, str], device_fingerprints: dict[str, str]) -> dict[str, Any]:
        manifest = {
            "version": SnapshotManager.DEVICE_MANIFEST_VERSION,
            "devices": sorted(device_blobs),
            "fingerprints": {name: device_fingerprints[name] for name in sorted(device_fingerprints)},
        }
        manifest["manifest_hash"] = SnapshotManager._fingerprint_device_manifest(manifest)
        return manifest

    @staticmethod
    def build_replay_trace(npc: NPC) -> dict[str, Any]:
        """
        Build a compact, replay-oriented tick trace without storing full prompt
        or response text.
        """
        audit_entries = [entry for entry in npc.audit_stream if entry.step != "spawn"]
        events = [
            {
                "index": index,
                "timestamp": entry.timestamp,
                "step": entry.step,
                "details": dict(entry.details),
            }
            for index, entry in enumerate(audit_entries)
        ]
        steps = [event["step"] for event in events]
        emit_hashes = [
            event["details"].get("hash")
            for event in events
            if event["step"] == "emit" and event["details"].get("hash")
        ]
        canonical_start = SnapshotManager.CANONICAL_TICK_SEQUENCE

        record = {
            "version": SnapshotManager.REPLAY_TRACE_VERSION,
            "npc_id": npc.identity.id,
            "scheduler_class": npc.scheduler_class.value,
            "event_count": len(events),
            "steps": steps,
            "canonical_tick_sequence": canonical_start,
            "canonical_sequence_observed": steps[:len(canonical_start)] == canonical_start,
            "emit_hashes": emit_hashes,
            "events": events,
            "events_hash": SnapshotManager._fingerprint_replay_events(events),
        }
        record["record_hash"] = SnapshotManager._fingerprint_replay_record(record)
        return record

    @staticmethod
    def _verify_replay_trace(replay_trace: dict[str, Any]) -> None:
        if not replay_trace:
            return
        if replay_trace.get("version") != SnapshotManager.REPLAY_TRACE_VERSION:
            raise ValueError("Snapshot replay trace version mismatch")
        events = list(replay_trace.get("events", []))
        expected_hash = replay_trace.get("events_hash")
        actual_hash = SnapshotManager._fingerprint_replay_events(events)
        if expected_hash != actual_hash:
            raise ValueError("Snapshot replay trace fingerprint mismatch")
        expected_record_hash = replay_trace.get("record_hash")
        actual_record_hash = SnapshotManager._fingerprint_replay_record(replay_trace)
        if expected_record_hash != actual_record_hash:
            raise ValueError("Snapshot replay trace record fingerprint mismatch")

    @staticmethod
    def _verify_device_manifest(
        device_manifest: dict[str, Any],
        device_blobs: dict[str, str],
        device_fingerprints: dict[str, str],
    ) -> None:
        if not device_manifest:
            return
        if device_manifest.get("version") != SnapshotManager.DEVICE_MANIFEST_VERSION:
            raise ValueError("Snapshot device manifest version mismatch")
        expected_hash = device_manifest.get("manifest_hash")
        actual_hash = SnapshotManager._fingerprint_device_manifest(device_manifest)
        if expected_hash != actual_hash:
            raise ValueError("Snapshot device manifest fingerprint mismatch")
        if sorted(device_blobs) != list(device_manifest.get("devices", [])):
            raise ValueError("Snapshot device manifest device set mismatch")
        if device_fingerprints != device_manifest.get("fingerprints", {}):
            raise ValueError("Snapshot device manifest fingerprint set mismatch")

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
            "device_manifest": SnapshotManager.build_device_manifest(device_blobs, device_fingerprints),
            "replay_trace": SnapshotManager.build_replay_trace(npc),
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
        SnapshotManager._verify_device_manifest(
            data.get("device_manifest", {}),
            data.get("devices", {}),
            expected_fingerprints,
        )
        for name, expected in expected_fingerprints.items():
            device = npc.mounted_devices.get(name)
            if device is None:
                raise ValueError(f"Snapshot missing restored device: {name}")
            if device.fingerprint() != expected:
                raise ValueError(f"Snapshot device fingerprint mismatch: {name}")

        SnapshotManager._verify_replay_trace(data.get("replay_trace", {}))
        npc.snapshot_replay_trace = dict(data.get("replay_trace", {}))
        npc.add_audit("restore", {"fingerprint": data["footer"]["fingerprint"]})
        return npc
