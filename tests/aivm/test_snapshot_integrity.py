import json
import sys
from pathlib import Path

import pytest

PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJ_ROOT / "packages"))

from aivm.kernel.core import AIVMKernel
from aivm.kernel.types import PersonaIdentity
from aivm.snapshot.manager import SnapshotManager


@pytest.mark.asyncio
async def test_snapshot_restore_preserves_local_memory_without_backend():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="snap_npc", name="Snap NPC", archetype="guard"))

    await kernel.tick("snap_npc", {"input": "remember the sealed gate"})

    blob = SnapshotManager.capture(npc)
    restored = AIVMKernel(enable_scheduler=False).restore_npc(blob)

    hits = restored.mounted_devices["VMD"].recall("sealed gate", k=5)
    assert restored.identity.id == "snap_npc"
    assert hits
    assert "sealed gate" in hits[0]["content"]


def test_snapshot_restore_rejects_tampered_payload():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="tamper_npc", name="Tamper NPC", archetype="guard"))

    data = json.loads(SnapshotManager.capture(npc).decode())
    data["identity"]["name"] = "Mutated NPC"
    tampered_blob = json.dumps(data, sort_keys=True).encode()

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        AIVMKernel(enable_scheduler=False).restore_npc(tampered_blob)


def test_snapshot_records_and_verifies_device_fingerprints():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="fp_npc", name="Fingerprint NPC", archetype="scribe"))
    npc.mounted_devices["VMD"].write("writeback memory partition event")

    blob = SnapshotManager.capture(npc)
    data = json.loads(blob.decode())

    assert set(data["device_fingerprints"]) == set(data["devices"])
    assert data["device_fingerprints"]["VPD"] == npc.mounted_devices["VPD"].fingerprint()
    assert data["device_fingerprints"]["VMD"] == npc.mounted_devices["VMD"].fingerprint()
    assert data["device_fingerprints"]["VQD"] == npc.mounted_devices["VQD"].fingerprint()

    restored = AIVMKernel(enable_scheduler=False).restore_npc(blob)
    for name, expected in data["device_fingerprints"].items():
        assert restored.mounted_devices[name].fingerprint() == expected


def test_snapshot_restore_rejects_device_payload_mismatch_with_valid_outer_seal():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="device_tamper_npc", name="Device Tamper", archetype="scribe"))
    data = json.loads(SnapshotManager.capture(npc).decode())
    original_vmd = json.loads(bytes.fromhex(data["devices"]["VMD"]).decode())
    original_vmd["local_events"].append({
        "ref": "device_tamper_npc:local:0",
        "content": "forged memory event",
        "memory_type": "working",
        "importance": 1.0,
    })
    data["devices"]["VMD"] = json.dumps(original_vmd, sort_keys=True).encode().hex()
    data["footer"]["fingerprint"] = SnapshotManager._fingerprint_payload(data)

    with pytest.raises(ValueError, match="device fingerprint mismatch: VMD"):
        AIVMKernel(enable_scheduler=False).restore_npc(json.dumps(data, sort_keys=True).encode())
