"""Adversarial tests for the persistent node-side execution authority."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aivm.admission import AdmissionDecision, AdmissionStatus
from aivm.execution import (
    AdmittedExecutionRequest,
    AuthorityRegistrationError,
    AuthorityStatus,
    LeaseAuthority,
    PersistentExecutionAuthority,
)
from contracts.aivm.v1 import AIVMWorkloadManifest, document_sha256


PAYLOAD = b"authority test payload\n"
IMAGE_DIGEST = "sha256:" + "7" * 64
NOW = datetime(2026, 7, 18, 12, 10, tzinfo=UTC)
EXPIRES = datetime(2026, 7, 18, 12, 30, tzinfo=UTC)


def _manifest() -> AIVMWorkloadManifest:
    payload_sha = hashlib.sha256(PAYLOAD).hexdigest()
    wire = {
        "schema": "planetary.aivm.workload.v1",
        "manifest_id": "manifest:cpu:001",
        "account_id": "account:owner:001",
        "workload_id": "workload:cpu:001",
        "issued_at": "2026-07-18T12:00:00Z",
        "expires_at": "2026-07-18T12:30:00Z",
        "signer_key_id": "key:owner:001",
        "runtime_image": {
            "image_id": "aivm-cpu-safe",
            "digest": IMAGE_DIGEST,
            "media_type": "application/vnd.oci.image.manifest.v1+json",
            "user": "aivm",
            "privileged": False,
            "host_network": False,
            "host_pid": False,
            "host_ipc": False,
            "devices": [],
        },
        "entrypoint_id": "aivm.sha256.v1",
        "resources": {
            "cpu_millicores": 500,
            "memory_bytes": 67_108_864,
            "time_limit_seconds": 5,
            "process_limit": 8,
            "open_file_limit": 64,
            "output_bytes": 256,
            "scratch_bytes": 0,
            "gpu_count": 0,
            "gpu_memory_bytes": 0,
        },
        "filesystem": {"rootfs": "readonly", "writable_paths": [], "host_mounts": []},
        "network": {"mode": "deny", "allowlist": []},
        "artifacts": [
            {
                "schema": "planetary.aivm.artifact.v1",
                "artifact_id": "artifact:input:001",
                "uri": "artifact://private/input",
                "kind": "input",
                "sha256": payload_sha,
                "size_bytes": len(PAYLOAD),
                "media_type": "application/octet-stream",
                "content_encoding": "identity",
                "created_at": "2026-07-18T11:59:00Z",
                "mount_path": "/work/input/payload",
                "readonly": True,
            }
        ],
        "inputs": ["artifact:input:001"],
        "outputs": ["output:result:001"],
        "signature": {
            "algorithm": "ed25519",
            "key_id": "key:owner:001",
            "value": "A" * 86,
        },
    }
    return AIVMWorkloadManifest.model_validate_json(json.dumps(wire, separators=(",", ":")))


def _admitted(manifest: AIVMWorkloadManifest) -> AdmissionDecision:
    return AdmissionDecision(
        AdmissionStatus.ADMITTED,
        "manifest admitted",
        manifest_id=manifest.manifest_id,
        workload_id=manifest.workload_id,
        account_id=manifest.account_id,
        evidence={
            "runtime_image": f"{manifest.runtime_image.image_id}@{manifest.runtime_image.digest}",
            "entrypoint_id": manifest.entrypoint_id,
            "guard_status": "ok",
        },
    )


def _request(*, fence: int = 7, lease_sha256: str = "3" * 64) -> AdmittedExecutionRequest:
    manifest = _manifest()
    lease = LeaseAuthority(
        account_id="account:owner:001",
        workload_id="workload:cpu:001",
        node_id="node:local:001",
        lease_id="lease:cpu:001",
        lease_sha256=lease_sha256,
        fencing_token=fence,
    )
    return AdmittedExecutionRequest(manifest, _admitted(manifest), lease)


def _authority(tmp_path: Path) -> PersistentExecutionAuthority:
    state = tmp_path / "authority"
    state.mkdir(mode=0o700, exist_ok=True)
    state.chmod(0o700)
    return PersistentExecutionAuthority(state, verifier_id="verifier:node:001")


def _register(
    authority: PersistentExecutionAuthority,
    request: AdmittedExecutionRequest,
    *,
    expires_at: datetime = EXPIRES,
    now: datetime = NOW,
) -> None:
    authority.register(
        account_id=request.lease.account_id,
        node_id=request.lease.node_id,
        lease_id=request.lease.lease_id,
        lease_sha256=request.lease.lease_sha256,
        fencing_token=request.lease.fencing_token,
        manifest_sha256=request.manifest_sha256,
        workload_id=request.manifest.workload_id,
        expires_at=expires_at,
        now=now,
    )


def test_registered_binding_is_consumed_exactly_once(tmp_path):
    authority = _authority(tmp_path)
    request = _request()
    _register(authority, request)

    first = authority.verify_and_consume(
        request,
        expected_account_id="account:owner:001",
        expected_node_id="node:local:001",
        now=NOW,
    )
    replay = authority.verify_and_consume(
        request,
        expected_account_id="account:owner:001",
        expected_node_id="node:local:001",
        now=NOW,
    )

    assert first.status is AuthorityStatus.VERIFIED
    assert first.consumed is True
    assert first.manifest_sha256 == document_sha256(_manifest())
    assert replay.status is AuthorityStatus.REJECTED


def test_consumption_survives_process_restart(tmp_path):
    request = _request()
    first_instance = _authority(tmp_path)
    _register(first_instance, request)
    consumed = first_instance.verify_and_consume(
        request,
        expected_account_id="account:owner:001",
        expected_node_id="node:local:001",
        now=NOW,
    )
    assert consumed.status is AuthorityStatus.VERIFIED

    reopened = _authority(tmp_path)
    replay = reopened.verify_and_consume(
        request,
        expected_account_id="account:owner:001",
        expected_node_id="node:local:001",
        now=NOW,
    )
    assert replay.status is AuthorityStatus.REJECTED
    with pytest.raises(AuthorityRegistrationError, match="lease_scope_already_consumed"):
        _register(reopened, request)


def test_unregistered_or_mismatched_bindings_are_rejected(tmp_path):
    authority = _authority(tmp_path)
    request = _request()

    unregistered = authority.verify_and_consume(
        request,
        expected_account_id="account:owner:001",
        expected_node_id="node:local:001",
        now=NOW,
    )
    assert unregistered.status is AuthorityStatus.REJECTED

    _register(authority, request)
    substituted = authority.verify_and_consume(
        _request(lease_sha256="9" * 64),
        expected_account_id="account:owner:001",
        expected_node_id="node:local:001",
        now=NOW,
    )
    assert substituted.status is AuthorityStatus.REJECTED

    wrong_node = authority.verify_and_consume(
        request,
        expected_account_id="account:owner:001",
        expected_node_id="node:other:002",
        now=NOW,
    )
    assert wrong_node.status is AuthorityStatus.REJECTED

    still_available = authority.verify_and_consume(
        request,
        expected_account_id="account:owner:001",
        expected_node_id="node:local:001",
        now=NOW,
    )
    assert still_available.status is AuthorityStatus.VERIFIED


def test_only_the_newest_registered_fence_can_consume(tmp_path):
    authority = _authority(tmp_path)
    old_revision = _request(fence=7)
    new_revision = _request(fence=8, lease_sha256="4" * 64)
    _register(authority, old_revision)
    _register(authority, new_revision)

    stale = authority.verify_and_consume(
        old_revision,
        expected_account_id="account:owner:001",
        expected_node_id="node:local:001",
        now=NOW,
    )
    assert stale.status is AuthorityStatus.REJECTED

    current = authority.verify_and_consume(
        new_revision,
        expected_account_id="account:owner:001",
        expected_node_id="node:local:001",
        now=NOW,
    )
    assert current.status is AuthorityStatus.VERIFIED

    with pytest.raises(AuthorityRegistrationError, match="lease_scope_already_consumed"):
        _register(authority, _request(fence=9, lease_sha256="5" * 64))


def test_registration_rejects_stale_conflicting_or_expired_revisions(tmp_path):
    authority = _authority(tmp_path)
    request = _request(fence=8)
    _register(authority, request)

    _register(authority, request)  # identical re-registration is idempotent

    with pytest.raises(AuthorityRegistrationError, match="stale_fencing_token"):
        _register(authority, _request(fence=7))

    with pytest.raises(AuthorityRegistrationError, match="conflicting_lease_revision"):
        _register(authority, _request(fence=8, lease_sha256="9" * 64))

    with pytest.raises(AuthorityRegistrationError, match="binding_already_expired"):
        _register(
            authority,
            _request(fence=9, lease_sha256="4" * 64),
            expires_at=NOW - timedelta(seconds=1),
        )


def test_expired_binding_cannot_be_consumed(tmp_path):
    authority = _authority(tmp_path)
    request = _request()
    _register(authority, request, expires_at=NOW + timedelta(seconds=30))

    late = authority.verify_and_consume(
        request,
        expected_account_id="account:owner:001",
        expected_node_id="node:local:001",
        now=NOW + timedelta(seconds=31),
    )
    assert late.status is AuthorityStatus.REJECTED
