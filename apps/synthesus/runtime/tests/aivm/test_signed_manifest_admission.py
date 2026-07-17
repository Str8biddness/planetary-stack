from __future__ import annotations

import base64
import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import ValidationError

from aivm.admission import (
    AIVMAdmissionController,
    AdmissionPolicy,
    AdmissionStatus,
    DocumentVerification,
    HostIsolationCapabilities,
)
from contracts.aivm.v1 import AIVMWorkloadManifest, signing_bytes


NOW = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)
PAYLOAD = b"print-free deterministic workload bundle"


class Ed25519FixtureVerifier:
    def __init__(self, public_key: Ed25519PublicKey, *, key_id: str = "key:owner:001"):
        self.public_key = public_key
        self.key_id = key_id

    def verify_manifest(
        self,
        manifest: AIVMWorkloadManifest,
        payload: bytes,
    ) -> DocumentVerification:
        if manifest.signature.key_id != self.key_id:
            return DocumentVerification(False, "unknown_key", error="unknown key id")
        try:
            signature = base64.urlsafe_b64decode(manifest.signature.value + "==")
            self.public_key.verify(signature, payload)
        except InvalidSignature:
            return DocumentVerification(False, "invalid_signature", key_id=self.key_id)
        return DocumentVerification(True, "verified", key_id=self.key_id)


def _b64_signature(signature: bytes) -> str:
    return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


def _artifact_payload() -> dict[str, Any]:
    return {
        "schema": "planetary.aivm.artifact.v1",
        "artifact_id": "artifact:bundle",
        "uri": "artifact://private/bundle",
        "kind": "workload_bundle",
        "sha256": hashlib.sha256(PAYLOAD).hexdigest(),
        "size_bytes": len(PAYLOAD),
        "media_type": "application/vnd.planetary.aivm.bundle",
        "content_encoding": "identity",
        "created_at": "2026-07-17T11:59:00Z",
        "mount_path": "/work/input/bundle",
        "readonly": True,
    }


def _manifest_payload() -> dict[str, Any]:
    return {
        "schema": "planetary.aivm.workload.v1",
        "manifest_id": "manifest:001",
        "account_id": "account:owner:001",
        "workload_id": "workload:001",
        "issued_at": "2026-07-17T11:59:00Z",
        "expires_at": "2026-07-17T12:30:00Z",
        "signer_key_id": "key:owner:001",
        "runtime_image": {
            "image_id": "aivm-python-safe",
            "digest": "sha256:" + "1" * 64,
            "media_type": "application/vnd.oci.image.manifest.v1+json",
            "user": "aivm",
            "privileged": False,
            "host_network": False,
            "host_pid": False,
            "host_ipc": False,
            "devices": [],
        },
        "entrypoint_id": "npc.tick.v1",
        "resources": {
            "cpu_millicores": 1000,
            "memory_bytes": 268_435_456,
            "time_limit_seconds": 30,
            "process_limit": 16,
            "open_file_limit": 64,
            "output_bytes": 1_048_576,
            "scratch_bytes": 1_048_576,
            "gpu_count": 0,
            "gpu_memory_bytes": 0,
        },
        "filesystem": {
            "rootfs": "readonly",
            "writable_paths": ["/scratch/workload"],
            "host_mounts": [],
        },
        "network": {"mode": "deny", "allowlist": []},
        "artifacts": [_artifact_payload()],
        "inputs": ["artifact:bundle"],
        "outputs": ["output:result"],
        "signature": {
            "algorithm": "ed25519",
            "key_id": "key:owner:001",
            "value": _b64_signature(b"\x00" * 64),
        },
    }


def _signed_manifest(private_key: Ed25519PrivateKey, payload: dict[str, Any] | None = None) -> AIVMWorkloadManifest:
    wire = copy.deepcopy(payload or _manifest_payload())
    provisional = AIVMWorkloadManifest.model_validate_json(json.dumps(wire, separators=(",", ":")))
    wire["signature"]["value"] = _b64_signature(private_key.sign(signing_bytes(provisional)))
    return AIVMWorkloadManifest.model_validate_json(json.dumps(wire, separators=(",", ":")))


def _policy() -> AdmissionPolicy:
    return AdmissionPolicy(
        allowed_runtime_images=frozenset({"aivm-python-safe@sha256:" + "1" * 64}),
        allowed_entrypoints=frozenset({"npc.tick.v1"}),
        max_cpu_millicores=2000,
        max_memory_bytes=536_870_912,
        max_time_limit_seconds=60,
        max_process_limit=32,
        max_output_bytes=2_097_152,
    )


def _host(**overrides: bool) -> HostIsolationCapabilities:
    values = {
        "os_enforced_backend": True,
        "cgroup_control": True,
        "namespaces": True,
        "no_new_privileges": True,
        "container_runtime": True,
        "guard_available": True,
        "gpu_isolation": False,
    }
    values.update(overrides)
    return HostIsolationCapabilities(**values)


def _controller(private_key: Ed25519PrivateKey, **host_overrides: bool) -> AIVMAdmissionController:
    return AIVMAdmissionController(
        verifier=Ed25519FixtureVerifier(private_key.public_key()),
        policy=_policy(),
        host=_host(**host_overrides),
    )


def test_canonical_signing_is_stable_and_admits_through_execution_guard():
    private_key = Ed25519PrivateKey.generate()
    first = _signed_manifest(private_key)
    second = _signed_manifest(private_key)

    assert signing_bytes(first) == signing_bytes(second)
    assert first.signature.value == second.signature.value

    decision = _controller(private_key).admit_sync(
        first,
        artifacts={"artifact://private/bundle": PAYLOAD},
        now=NOW,
    )

    assert decision.status == AdmissionStatus.ADMITTED
    assert decision.evidence["guard_status"] == "ok"
    assert decision.evidence["network_mode"] == "deny"


def test_signature_tampering_is_rejected():
    private_key = Ed25519PrivateKey.generate()
    manifest = _signed_manifest(private_key)
    tampered = manifest.model_dump(mode="json", by_alias=True)
    tampered["entrypoint_id"] = "npc.other.v1"
    tampered_manifest = AIVMWorkloadManifest.model_validate_json(json.dumps(tampered, separators=(",", ":")))

    decision = _controller(private_key).admit_sync(
        tampered_manifest,
        artifacts={"artifact://private/bundle": PAYLOAD},
        now=NOW,
    )

    assert decision.status == AdmissionStatus.REJECTED
    assert "signature" in decision.reason


def test_unknown_fields_are_rejected():
    payload = _manifest_payload()
    payload["runtime_image"]["surprise"] = True

    with pytest.raises(ValidationError):
        AIVMWorkloadManifest.model_validate_json(json.dumps(payload, separators=(",", ":")))


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda p: p.update({"entrypoint_id": "bash -c whoami"}), "entrypoint"),
        (lambda p: p.update({"entrypoint_id": "pickle"}), "entrypoint"),
        (lambda p: p["runtime_image"].update({"privileged": True}), "privileged"),
        (lambda p: p["runtime_image"].update({"host_network": True}), "host_network"),
        (lambda p: p["runtime_image"].update({"host_pid": True}), "host_pid"),
        (lambda p: p["runtime_image"].update({"host_ipc": True}), "host_ipc"),
        (lambda p: p["runtime_image"].update({"devices": ["/dev/kvm"]}), "devices"),
        (lambda p: p["artifacts"][0].update({"mount_path": "/work/../secret"}), "mount_path"),
        (lambda p: p["filesystem"].update({"writable_paths": ["/home/user"]}), "writable_paths"),
        (lambda p: p["filesystem"].update({"host_mounts": ["/"]}), "host mounts"),
        (lambda p: p["network"].update({"mode": "allowlist", "allowlist": []}), "allowlist"),
        (lambda p: p["resources"].update({"cpu_millicores": 0}), "cpu"),
        (lambda p: p["resources"].update({"memory_bytes": 1}), "memory"),
        (lambda p: p["resources"].update({"time_limit_seconds": 0}), "time"),
        (lambda p: p["resources"].update({"process_limit": 0}), "process"),
    ],
)
def test_unsafe_manifest_values_fail_closed(mutator, message):
    payload = _manifest_payload()
    mutator(payload)

    with pytest.raises(ValidationError, match=message):
        AIVMWorkloadManifest.model_validate_json(json.dumps(payload, separators=(",", ":")))


def test_expired_manifest_is_rejected():
    private_key = Ed25519PrivateKey.generate()
    payload = _manifest_payload()
    payload["expires_at"] = "2026-07-17T12:00:00Z"
    manifest = _signed_manifest(private_key, payload)

    decision = _controller(private_key).admit_sync(
        manifest,
        artifacts={"artifact://private/bundle": PAYLOAD},
        now=NOW,
    )

    assert decision.status == AdmissionStatus.REJECTED
    assert decision.reason == "manifest expired"


def test_artifact_hash_and_size_are_verified_before_admission():
    private_key = Ed25519PrivateKey.generate()
    manifest = _signed_manifest(private_key)

    size_decision = _controller(private_key).admit_sync(
        manifest,
        artifacts={"artifact://private/bundle": PAYLOAD + b"x"},
        now=NOW,
    )
    hash_decision = _controller(private_key).admit_sync(
        manifest,
        artifacts={"artifact://private/bundle": b"x" * len(PAYLOAD)},
        now=NOW,
    )

    assert size_decision.status == AdmissionStatus.REJECTED
    assert size_decision.reason == "artifact size mismatch: artifact:bundle"
    assert hash_decision.status == AdmissionStatus.REJECTED
    assert hash_decision.reason == "artifact hash mismatch: artifact:bundle"


def test_runtime_image_and_entrypoint_allowlists_are_enforced():
    private_key = Ed25519PrivateKey.generate()
    manifest = _signed_manifest(private_key)

    image_policy = AdmissionPolicy(
        allowed_runtime_images=frozenset({"other@sha256:" + "2" * 64}),
        allowed_entrypoints=frozenset({"npc.tick.v1"}),
        max_cpu_millicores=2000,
        max_memory_bytes=536_870_912,
        max_time_limit_seconds=60,
        max_process_limit=32,
        max_output_bytes=2_097_152,
    )
    image_decision = AIVMAdmissionController(
        verifier=Ed25519FixtureVerifier(private_key.public_key()),
        policy=image_policy,
        host=_host(),
    ).admit_sync(manifest, artifacts={"artifact://private/bundle": PAYLOAD}, now=NOW)

    entry_policy = AdmissionPolicy(
        allowed_runtime_images=frozenset({"aivm-python-safe@sha256:" + "1" * 64}),
        allowed_entrypoints=frozenset({"npc.other.v1"}),
        max_cpu_millicores=2000,
        max_memory_bytes=536_870_912,
        max_time_limit_seconds=60,
        max_process_limit=32,
        max_output_bytes=2_097_152,
    )
    entry_decision = AIVMAdmissionController(
        verifier=Ed25519FixtureVerifier(private_key.public_key()),
        policy=entry_policy,
        host=_host(),
    ).admit_sync(manifest, artifacts={"artifact://private/bundle": PAYLOAD}, now=NOW)

    assert image_decision.status == AdmissionStatus.REJECTED
    assert image_decision.reason == "runtime image is not allowlisted"
    assert entry_decision.status == AdmissionStatus.REJECTED
    assert entry_decision.reason == "entrypoint_id is not allowlisted"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("cpu_millicores", 2001, "cpu budget exceeds host policy"),
        ("memory_bytes", 536_870_913, "memory budget exceeds host policy"),
        ("time_limit_seconds", 61, "time budget exceeds host policy"),
        ("process_limit", 33, "process budget exceeds host policy"),
        ("output_bytes", 2_097_153, "output budget exceeds host policy"),
    ],
)
def test_resource_limits_are_enforced_by_admission_policy(field, value, reason):
    private_key = Ed25519PrivateKey.generate()
    payload = _manifest_payload()
    payload["resources"][field] = value
    manifest = _signed_manifest(private_key, payload)

    decision = _controller(private_key).admit_sync(
        manifest,
        artifacts={"artifact://private/bundle": PAYLOAD},
        now=NOW,
    )

    assert decision.status == AdmissionStatus.REJECTED
    assert decision.reason == reason


def test_future_network_allowlist_descriptor_is_not_enabled_by_default():
    private_key = Ed25519PrivateKey.generate()
    payload = _manifest_payload()
    payload["network"] = {"mode": "allowlist", "allowlist": ["artifact-plane.local"]}
    manifest = _signed_manifest(private_key, payload)

    decision = _controller(private_key).admit_sync(
        manifest,
        artifacts={"artifact://private/bundle": PAYLOAD},
        now=NOW,
    )

    assert decision.status == AdmissionStatus.REJECTED
    assert decision.reason == "network is denied by admission policy"


def test_unsupported_host_returns_unavailable_without_admission():
    private_key = Ed25519PrivateKey.generate()
    manifest = _signed_manifest(private_key)

    decision = _controller(private_key, cgroup_control=False).admit_sync(
        manifest,
        artifacts={"artifact://private/bundle": PAYLOAD},
        now=NOW,
    )

    assert decision.status == AdmissionStatus.UNAVAILABLE
    assert decision.degraded is True
    assert decision.evidence["missing"] == ["cgroup_control"]


def test_missing_verifier_returns_unavailable_without_local_trust_store():
    private_key = Ed25519PrivateKey.generate()
    manifest = _signed_manifest(private_key)
    controller = AIVMAdmissionController(verifier=None, policy=_policy(), host=_host())

    decision = controller.admit_sync(
        manifest,
        artifacts={"artifact://private/bundle": PAYLOAD},
        now=NOW,
    )

    assert decision.status == AdmissionStatus.UNAVAILABLE
    assert decision.degraded is True
    assert decision.evidence["missing"] == ["document_verifier"]
