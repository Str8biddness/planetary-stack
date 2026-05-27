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
