"""Per-device permission policy.

These tests exist for the refusals, not the happy path: default-deny, the
source/peer boundary, and failing safe when the policy cannot be read.
"""

from __future__ import annotations

import json
import os
import stat

import pytest

from device_policy import (
    POLICY_SCHEMA,
    DevicePolicyError,
    DevicePolicyStore,
)

WORKER = "node:private-mesh:dakin-ms-7c95"
CAMERA = "device:camera:front-door"


@pytest.fixture
def store(tmp_path):
    return DevicePolicyStore(tmp_path / "policy" / "device-policy.json")


def test_absent_policy_denies_everything(store):
    """No policy file means nothing is permitted, never everything."""
    assert store.devices() == []
    assert store.is_allowed(WORKER, "run_inference") is False
    assert store.is_allowed(WORKER, "return_results") is False
    # ...but evidence enforcement defaults ON.
    assert store.require_verified_evidence() is True


def test_added_device_starts_with_every_capability_off(store):
    device = store.add_device(
        device_id=WORKER, display_name="Workshop PC", role="peer"
    )
    assert device["capabilities"] == {"run_inference": False, "return_results": False}
    assert store.is_allowed(WORKER, "run_inference") is False


def test_toggling_a_capability_grants_only_that_capability(store):
    store.add_device(device_id=WORKER, display_name="Workshop PC", role="peer")
    store.set_capabilities(WORKER, {"run_inference": True})
    assert store.is_allowed(WORKER, "run_inference") is True
    assert store.is_allowed(WORKER, "return_results") is False


def test_a_source_device_can_never_run_inference_or_return_results(store):
    """The camera/TV boundary is enforced here, not in the UI."""
    store.add_device(device_id=CAMERA, display_name="Front door camera", role="source")
    for capability in ("run_inference", "return_results"):
        with pytest.raises(DevicePolicyError, match="cannot be granted"):
            store.set_capabilities(CAMERA, {capability: True})
        assert store.is_allowed(CAMERA, capability) is False
    # It can do the one thing a source is for.
    store.set_capabilities(CAMERA, {"provide_input": True})
    assert store.is_allowed(CAMERA, "provide_input") is True


def test_a_peer_cannot_be_granted_a_source_capability(store):
    store.add_device(device_id=WORKER, display_name="Workshop PC", role="peer")
    with pytest.raises(DevicePolicyError, match="cannot be granted"):
        store.set_capabilities(WORKER, {"provide_input": True})


def test_unknown_capability_is_rejected_and_denied(store):
    store.add_device(device_id=WORKER, display_name="Workshop PC", role="peer")
    with pytest.raises(DevicePolicyError, match="unknown capability"):
        store.set_capabilities(WORKER, {"read_all_files": True})
    assert store.is_allowed(WORKER, "read_all_files") is False


def test_unknown_device_is_denied_even_when_others_are_allowed(store):
    store.add_device(device_id=WORKER, display_name="Workshop PC", role="peer")
    store.set_capabilities(WORKER, {"run_inference": True})
    assert store.is_allowed("node:private-mesh:stranger", "run_inference") is False


def test_removed_device_loses_its_permissions(store):
    store.add_device(device_id=WORKER, display_name="Workshop PC", role="peer")
    store.set_capabilities(WORKER, {"run_inference": True})
    store.remove_device(WORKER)
    assert store.is_allowed(WORKER, "run_inference") is False
    with pytest.raises(DevicePolicyError, match="not present"):
        store.remove_device(WORKER)


def test_evidence_enforcement_toggles_and_persists(store):
    assert store.require_verified_evidence() is True
    store.set_require_verified_evidence(False)
    assert store.require_verified_evidence() is False
    # A fresh store over the same path sees the persisted choice.
    assert DevicePolicyStore(store.path).require_verified_evidence() is False


def test_corrupt_policy_fails_safe(store, tmp_path):
    store.add_device(device_id=WORKER, display_name="Workshop PC", role="peer")
    store.set_capabilities(WORKER, {"run_inference": True})
    store.path.write_text("{ this is not json", encoding="utf-8")

    # Unreadable policy grants nothing and enforces evidence.
    assert store.is_allowed(WORKER, "run_inference") is False
    assert store.require_verified_evidence() is True
    with pytest.raises(DevicePolicyError):
        store.devices()


def test_tampered_policy_granting_a_source_execution_is_rejected(store):
    """Hand-editing the file cannot buy a capability the role forbids."""
    store.add_device(device_id=CAMERA, display_name="Front door camera", role="source")
    forged = {
        "schema": POLICY_SCHEMA,
        "require_verified_evidence": True,
        "devices": {
            CAMERA: {
                "device_id": CAMERA,
                "display_name": "Front door camera",
                "role": "source",
                "capabilities": {"provide_input": True, "run_inference": True},
            }
        },
    }
    store.path.write_text(json.dumps(forged), encoding="utf-8")
    assert store.is_allowed(CAMERA, "run_inference") is False
    with pytest.raises(DevicePolicyError, match="capabilities of its role"):
        store.devices()


def test_policy_file_is_owner_only(store):
    store.add_device(device_id=WORKER, display_name="Workshop PC", role="peer")
    mode = stat.S_IMODE(os.lstat(store.path).st_mode)
    assert mode == 0o600, oct(mode)


def test_invalid_device_ids_and_roles_are_rejected(store):
    with pytest.raises(DevicePolicyError, match="valid identifier"):
        store.add_device(device_id="../etc/passwd", display_name="x", role="peer")
    with pytest.raises(DevicePolicyError, match="role is unsupported"):
        store.add_device(device_id=WORKER, display_name="x", role="admin")
    with pytest.raises(DevicePolicyError, match="display_name is required"):
        store.add_device(device_id=WORKER, display_name="   ", role="peer")


def test_duplicate_device_is_rejected(store):
    store.add_device(device_id=WORKER, display_name="Workshop PC", role="peer")
    with pytest.raises(DevicePolicyError, match="already present"):
        store.add_device(device_id=WORKER, display_name="Again", role="peer")
