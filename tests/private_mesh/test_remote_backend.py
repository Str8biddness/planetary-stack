"""Unit tests for the remote execution backend's v2 dispatch and parsing.

End-to-end execution against a real enrolled worker is proven physically
(docs/evidence/F020_DESKTOP_REMOTE_JOB_PHYSICAL_2026-07-18.md). These tests pin the
backend's new logic: it must build a v2 executor job whose spec is derived
from the workload manifest, fail closed on a mismatched image or a
non-model manifest, and map the worker's signed response envelope back to
node-agent result types without fabricating success.
"""

from __future__ import annotations

import base64
import json

import pytest

import hashlib

from contracts.aivm.v1 import canonical_document_bytes
from services.private_mesh.node_agent import NodeAgentStatus
from services.private_mesh.ssh_smoke import NodeTarget
from services.remote_backend import RemoteBackendError, RemoteExecutionBackend
from tests.private_mesh.test_execution_wiring import (
    DOCUMENT_ARTIFACT_ID,
    IMAGE_DIGEST,
    IMMUTABLE_IMAGE,
    MODEL_ARTIFACT_ID,
    OUTPUT_ID,
    _workload_manifest,
)
from tests.vsource.test_local_control_plane import (
    ACCOUNT,
    SUBJECT,
    allocate_once,
    capability_doc,
    inventory_doc,
    mesh_context,
    request_doc,
)

_WORKER_NODE = "node:owner:a"


def _backend(carrier=None, *, node_id: str = "node:private-mesh:ms7c95") -> RemoteExecutionBackend:
    return RemoteExecutionBackend(
        carrier=carrier,
        target=NodeTarget(
            node_id,
            "worker",
            "SHA256:" + "a" * 43,
            "/usr/bin/python",
            "/repo",
            "/state",
        ),
        account_id="account:owner:001",
        keys=[],
        inventory={"schema": "planetary.vsource.inventory.v1"},
        image_ref=IMMUTABLE_IMAGE,
        image_digest=IMAGE_DIGEST,
    )


def _bundle() -> bytes:
    return canonical_document_bytes(_workload_manifest())


def test_constructor_rejects_mutable_or_mismatched_image():
    with pytest.raises(RemoteBackendError):
        RemoteExecutionBackend(
            carrier=None,
            target=NodeTarget("node:x", "w", "SHA256:" + "a" * 43, "/p", "/r", "/s"),
            account_id="account:owner:001",
            keys=[],
            inventory={},
            image_ref="localhost/aivm-text-classify:latest",
            image_digest=IMAGE_DIGEST,
        )


def test_executor_spec_is_derived_from_the_manifest():
    spec = _backend()._executor_spec(_bundle())
    assert spec["profile"] == "text-classification.v1"
    assert spec["image_ref"] == IMMUTABLE_IMAGE
    assert spec["image_digest"] == IMAGE_DIGEST
    assert spec["model_artifact_id"] == MODEL_ARTIFACT_ID
    assert spec["document_artifact_id"] == DOCUMENT_ARTIFACT_ID
    assert spec["output_id"] == OUTPUT_ID
    assert spec["artifact_sha256s"] == sorted(spec["artifact_sha256s"])
    assert len(spec["artifact_sha256s"]) == 2


def test_executor_spec_fails_closed_on_image_mismatch():
    wire = _workload_manifest().model_dump(mode="json", by_alias=True)
    wire["runtime_image"]["digest"] = "sha256:" + "9" * 64
    bundle = json.dumps(wire, separators=(",", ":")).encode()
    with pytest.raises(RemoteBackendError, match="runtime image"):
        _backend()._executor_spec(bundle)


def test_executor_spec_rejects_non_model_manifest():
    with pytest.raises(RemoteBackendError, match="model profile|artifacts|JSON"):
        _backend()._executor_spec(b'{"artifacts": [], "outputs": []}')


class _CapturingCarrier:
    def __init__(self, response):
        self.response = response
        self.sent = None

    def execute(self, target, job, cancel_event=None):
        self.sent = job
        return self.response


def _real_lease(tmp_path, bundle):
    """Produce a real signed lease/request/capability bound to the worker node."""

    ctx = mesh_context(tmp_path)
    ctx.resolver.add(
        __import__("services.vsource", fromlist=["KeyRecord"]).KeyRecord(
            key_id=ctx.scheduler.key_id,
            public_key=ctx.scheduler.private_key.public_key().public_bytes(
                __import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.Raw,
                __import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.Raw,
            ),
            account_id=ACCOUNT,
            audiences=(SUBJECT,),
        )
    )
    inventory = inventory_doc(ctx)
    ctx.service().register_inventory(inventory)
    request = request_doc(
        ctx,
        workload_digest=hashlib.sha256(bundle).hexdigest(),
        workload_size=len(bundle),
    )
    capability = capability_doc(ctx)
    allocation = allocate_once(ctx, request=request, capability=capability)
    assert allocation.lease is not None
    return allocation.lease, request, capability


def _admit_and_execute(backend, bundle, tmp_path):
    lease, request, capability = _real_lease(tmp_path, bundle)
    admit = backend.admit_lease(
        lease, request, capability, authenticated_subject_id=SUBJECT
    )
    assert admit.accepted, admit.reason
    return backend.execute(
        lease_id=admit.lease_id,
        lease_sha256=admit.lease_sha256,
        fencing_token=lease.fencing_token,
        bundle=bundle,
    )


def test_execute_builds_a_v2_job_and_maps_a_completed_response(tmp_path):
    envelope = {
        "schema": "planetary.private_mesh.ssh_result.v1",
        "hostname": "dakin-MS-7C95",
        "node_id": "node:private-mesh:ms7c95",
        "admission": {"accepted": True, "status": "admitted"},
        "execution": {
            "status": "executed",
            "accepted": True,
            "reason": None,
            "response": None,
            "lifecycle_events": [],
            "report_base64": base64.urlsafe_b64encode(b'{"ok":1}').rstrip(b"=").decode(),
            "error": None,
        },
    }
    carrier = _CapturingCarrier(envelope)
    backend = _backend(carrier, node_id=_WORKER_NODE)
    bundle = _bundle()
    result = _admit_and_execute(backend, bundle, tmp_path)

    assert carrier.sent["schema"] == "planetary.private_mesh.ssh_job.v2"
    assert carrier.sent["executor"]["profile"] == "text-classification.v1"
    assert carrier.sent["executor"]["image_digest"] == IMAGE_DIGEST
    assert base64.urlsafe_b64decode(carrier.sent["bundle_base64"] + "==") == bundle
    assert result.status == NodeAgentStatus.EXECUTED
    assert result.accepted
    assert result.report == b'{"ok":1}'


def test_execute_reports_worker_rejection_without_fabrication(tmp_path):
    envelope = {
        "schema": "planetary.private_mesh.ssh_result.v1",
        "hostname": "dakin-MS-7C95",
        "node_id": "node:private-mesh:ms7c95",
        "admission": {"accepted": False, "reason": "lease was never admitted on this node"},
        "execution": None,
    }
    backend = _backend(_CapturingCarrier(envelope), node_id=_WORKER_NODE)
    result = _admit_and_execute(backend, _bundle(), tmp_path)
    assert not result.accepted
    assert result.status == NodeAgentStatus.REJECTED
    assert result.reason == "lease was never admitted on this node"


def test_execute_reports_carrier_failure_as_unavailable(tmp_path):
    class _FailingCarrier:
        def execute(self, target, job, cancel_event=None):
            raise OSError("ssh connection refused")

    backend = _backend(_FailingCarrier(), node_id=_WORKER_NODE)
    result = _admit_and_execute(backend, _bundle(), tmp_path)
    assert result.status == NodeAgentStatus.UNAVAILABLE
    assert "ssh connection refused" in result.reason
