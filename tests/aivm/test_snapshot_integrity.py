import json
import sys
from pathlib import Path

import pytest

PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJ_ROOT / "packages"))

from aivm.kernel.core import AIVMKernel
from aivm.kernel.types import PersonaIdentity
from aivm.snapshot.manager import SnapshotManager


class FakeKnowledgeCloud:
    def search(self, query: str, top_k: int = 5):
        return [
            {"content": f"{query} knowledge hit", "rank": idx}
            for idx in range(top_k)
        ]


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
    npc.mounted_devices["VCD"].put("turn-plan", {"route": "quad_brain_path"}, tier="L1")
    npc.mounted_devices["VWD"].stage(
        {"trace_id": "trace-1", "event": "critic.accepted"},
        target="crystallized",
        provenance="critic.selected_response",
    )

    blob = SnapshotManager.capture(npc)
    data = json.loads(blob.decode())

    assert set(data["device_fingerprints"]) == set(data["devices"])
    assert data["device_fingerprints"]["VPD"] == npc.mounted_devices["VPD"].fingerprint()
    assert data["device_fingerprints"]["VMD"] == npc.mounted_devices["VMD"].fingerprint()
    assert data["device_fingerprints"]["VQD"] == npc.mounted_devices["VQD"].fingerprint()
    assert data["device_fingerprints"]["VCD"] == npc.mounted_devices["VCD"].fingerprint()
    assert data["device_fingerprints"]["VWD"] == npc.mounted_devices["VWD"].fingerprint()
    assert data["device_manifest"]["version"] == SnapshotManager.DEVICE_MANIFEST_VERSION
    assert data["device_manifest"]["devices"] == sorted(data["devices"])
    assert data["device_manifest"]["fingerprints"] == data["device_fingerprints"]
    assert (
        data["device_manifest"]["manifest_hash"]
        == SnapshotManager.build_device_manifest(data["devices"], data["device_fingerprints"])["manifest_hash"]
    )

    restored = AIVMKernel(enable_scheduler=False).restore_npc(blob)
    assert restored.mounted_devices["VCD"].get("turn-plan") == {"route": "quad_brain_path"}
    assert restored.mounted_devices["VWD"].pending() == [
        {
            "ref": "fp_npc:writeback:0",
            "target": "crystallized",
            "provenance": "critic.selected_response",
            "content": {"trace_id": "trace-1", "event": "critic.accepted"},
        }
    ]
    for name, expected in data["device_fingerprints"].items():
        assert restored.mounted_devices[name].fingerprint() == expected


def test_snapshot_restore_rejects_device_manifest_fingerprint_set_mismatch_with_valid_outer_seal():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="manifest_tamper_npc", name="Manifest Tamper", archetype="scribe"))

    data = json.loads(SnapshotManager.capture(npc).decode())
    data["device_fingerprints"]["VMD"] = "forged"
    data["footer"]["fingerprint"] = SnapshotManager._fingerprint_payload(data)

    with pytest.raises(ValueError, match="device manifest fingerprint set mismatch"):
        AIVMKernel(enable_scheduler=False).restore_npc(json.dumps(data, sort_keys=True).encode())


def test_snapshot_restore_rejects_device_manifest_missing_device_with_valid_outer_seal():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="manifest_missing_npc", name="Manifest Missing", archetype="scribe"))

    data = json.loads(SnapshotManager.capture(npc).decode())
    del data["devices"]["VQD"]
    data["footer"]["fingerprint"] = SnapshotManager._fingerprint_payload(data)

    with pytest.raises(ValueError, match="device manifest device set mismatch"):
        AIVMKernel(enable_scheduler=False).restore_npc(json.dumps(data, sort_keys=True).encode())


def test_snapshot_restore_preserves_vqd_scope_policy_and_lookup_trace():
    kernel = AIVMKernel(knowledge_cloud=FakeKnowledgeCloud(), enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="vqd_npc", name="VQD NPC", archetype="archivist"))
    vqd = npc.mounted_devices["VQD"]
    vqd.set_scope(["kc://rom/lore", "kc://provenance/source-plane"])
    vqd.set_policy({"pruning": "semantic", "chain_length": 2, "gating": "scoped"})

    assert len(vqd.lookup("chal mount", limit=2)) == 2

    restored = AIVMKernel(enable_scheduler=False).restore_npc(SnapshotManager.capture(npc))
    restored_vqd = restored.mounted_devices["VQD"]

    assert restored_vqd.scope() == ["kc://rom/lore", "kc://provenance/source-plane"]
    assert restored_vqd.policy() == {"pruning": "semantic", "chain_length": 2, "gating": "scoped"}
    assert restored_vqd.lookup_count() == 1
    assert restored_vqd.last_lookup() == {
        "query": "chal mount",
        "limit": 2,
        "hit_count": 2,
        "scope": ["kc://rom/lore", "kc://provenance/source-plane"],
        "backend_mounted": True,
        "status": "ok",
    }


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


def test_snapshot_restore_rejects_cache_partition_payload_mismatch_with_valid_outer_seal():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="cache_tamper_npc", name="Cache Tamper", archetype="scribe"))
    npc.mounted_devices["VCD"].put("grounding", {"hits": 1}, tier="L2")

    data = json.loads(SnapshotManager.capture(npc).decode())
    cache_payload = json.loads(bytes.fromhex(data["devices"]["VCD"]).decode())
    cache_payload["entries"]["grounding"]["value"] = {"hits": 999}
    data["devices"]["VCD"] = json.dumps(cache_payload, sort_keys=True).encode().hex()
    data["footer"]["fingerprint"] = SnapshotManager._fingerprint_payload(data)

    with pytest.raises(ValueError, match="device fingerprint mismatch: VCD"):
        AIVMKernel(enable_scheduler=False).restore_npc(json.dumps(data, sort_keys=True).encode())


def test_snapshot_restore_rejects_writeback_partition_payload_mismatch_with_valid_outer_seal():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="writeback_tamper_npc", name="Writeback Tamper", archetype="scribe"))
    npc.mounted_devices["VWD"].stage({"trace_id": "trace-2"}, target="episodic")

    data = json.loads(SnapshotManager.capture(npc).decode())
    writeback_payload = json.loads(bytes.fromhex(data["devices"]["VWD"]).decode())
    writeback_payload["records"].append({
        "ref": "writeback_tamper_npc:writeback:1",
        "target": "crystallized",
        "provenance": "forged",
        "content": {"trace_id": "forged"},
    })
    data["devices"]["VWD"] = json.dumps(writeback_payload, sort_keys=True).encode().hex()
    data["footer"]["fingerprint"] = SnapshotManager._fingerprint_payload(data)

    with pytest.raises(ValueError, match="device fingerprint mismatch: VWD"):
        AIVMKernel(enable_scheduler=False).restore_npc(json.dumps(data, sort_keys=True).encode())


def test_snapshot_restore_rejects_knowledge_partition_payload_mismatch_with_valid_outer_seal():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="vqd_tamper_npc", name="VQD Tamper", archetype="scribe"))
    npc.mounted_devices["VQD"].set_scope(["kc://rom/core"])

    data = json.loads(SnapshotManager.capture(npc).decode())
    knowledge_payload = json.loads(bytes.fromhex(data["devices"]["VQD"]).decode())
    knowledge_payload["scope"].append("kc://rom/forged")
    data["devices"]["VQD"] = json.dumps(knowledge_payload, sort_keys=True).encode().hex()
    data["footer"]["fingerprint"] = SnapshotManager._fingerprint_payload(data)

    with pytest.raises(ValueError, match="device fingerprint mismatch: VQD"):
        AIVMKernel(enable_scheduler=False).restore_npc(json.dumps(data, sort_keys=True).encode())


@pytest.mark.asyncio
async def test_snapshot_records_compact_replay_trace_without_response_text():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="replay_npc", name="Replay NPC", archetype="scribe"))

    await kernel.tick("replay_npc", {"input": "record a replayable kernel tick"})

    data = json.loads(SnapshotManager.capture(npc).decode())
    replay_trace = data["replay_trace"]

    assert replay_trace["version"] == SnapshotManager.REPLAY_TRACE_VERSION
    assert replay_trace["npc_id"] == "replay_npc"
    assert replay_trace["event_count"] == 12
    assert replay_trace["steps"] == SnapshotManager.CANONICAL_TICK_SEQUENCE
    assert replay_trace["canonical_sequence_observed"] is True
    assert replay_trace["emit_hashes"]
    assert replay_trace["device_manifest_hash"] == data["device_manifest"]["manifest_hash"]
    assert len(replay_trace["events"]) == 12
    assert replay_trace["events"][0]["step"] == "admission"
    rebuilt_replay_trace = SnapshotManager.build_replay_trace(
        npc,
        data["device_manifest"]["manifest_hash"],
    )
    assert replay_trace["events_hash"] == rebuilt_replay_trace["events_hash"]
    assert replay_trace["record_hash"] == rebuilt_replay_trace["record_hash"]
    assert "Generated response from AIVM VGD." not in json.dumps(replay_trace)

    restored = AIVMKernel(enable_scheduler=False).restore_npc(SnapshotManager.capture(npc))
    assert restored.snapshot_replay_trace == replay_trace
    assert [entry.step for entry in restored.audit_stream] == ["spawn", "restore"]


@pytest.mark.asyncio
async def test_snapshot_restore_rejects_replay_trace_event_mismatch_with_valid_outer_seal():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="replay_tamper_npc", name="Replay Tamper", archetype="scribe"))

    await kernel.tick("replay_tamper_npc", {"input": "seal this replay trace"})
    data = json.loads(SnapshotManager.capture(npc).decode())
    data["replay_trace"]["events"][0]["step"] = "forged_step"
    data["footer"]["fingerprint"] = SnapshotManager._fingerprint_payload(data)

    with pytest.raises(ValueError, match="replay trace fingerprint mismatch"):
        AIVMKernel(enable_scheduler=False).restore_npc(json.dumps(data, sort_keys=True).encode())


@pytest.mark.asyncio
async def test_snapshot_restore_rejects_replay_trace_record_mismatch_with_valid_event_hash():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="replay_record_tamper_npc", name="Replay Record Tamper", archetype="scribe"))

    await kernel.tick("replay_record_tamper_npc", {"input": "seal replay metadata too"})
    data = json.loads(SnapshotManager.capture(npc).decode())
    data["replay_trace"]["scheduler_class"] = "batch"
    data["footer"]["fingerprint"] = SnapshotManager._fingerprint_payload(data)

    with pytest.raises(ValueError, match="replay trace record fingerprint mismatch"):
        AIVMKernel(enable_scheduler=False).restore_npc(json.dumps(data, sort_keys=True).encode())


@pytest.mark.asyncio
async def test_snapshot_restore_rejects_replay_trace_device_manifest_mismatch_with_valid_outer_seal():
    kernel = AIVMKernel(enable_scheduler=False)
    npc = kernel.spawn_npc(PersonaIdentity(id="replay_manifest_npc", name="Replay Manifest", archetype="scribe"))

    await kernel.tick("replay_manifest_npc", {"input": "bind replay to mounted devices"})
    data = json.loads(SnapshotManager.capture(npc).decode())
    data["replay_trace"]["device_manifest_hash"] = "forged-manifest-hash"
    data["replay_trace"]["record_hash"] = SnapshotManager._fingerprint_replay_record(data["replay_trace"])
    data["footer"]["fingerprint"] = SnapshotManager._fingerprint_payload(data)

    with pytest.raises(ValueError, match="replay trace device manifest mismatch"):
        AIVMKernel(enable_scheduler=False).restore_npc(json.dumps(data, sort_keys=True).encode())
