"""Remote JobExecutionBackend: run one desktop job on an enrolled worker.

This backend lets `LocalJobPipeline` dispatch a signed workload to a physical
worker over the pinned administrative carrier as an `ssh_job.v2` executor job,
so the worker runs the real AIVM model profile (not the SHA-256 placeholder)
against artifacts already delivered to its Unisync mesh inbox over mTLS. The
worker performs admission and execution atomically and returns a signed
lease-bound response; this backend parses that envelope back into the
node-agent result types the pipeline already understands.

`admit_lease` records the job for dispatch and reports `ADMITTED` meaning
"allocated and queued for remote dispatch"; the authoritative proof is the
worker's signed COMPLETED/FAILED lifecycle returned from `execute`. No result
state is fabricated: a carrier failure is `UNAVAILABLE`, a worker rejection is
`REJECTED`/`FAILED` with the worker's reason.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from typing import Any

from contracts.chal_vsource.v1.canonical import document_sha256
from contracts.chal_vsource.v1.models import (
    CapabilityDocument,
    ChalRequest,
    ChalResponse,
    ErrorFrame,
    LeaseDocument,
    LifecycleEvent,
    ResourceInventory,
)
from services.private_mesh.evidence_signing import (
    EvidenceSignatureError,
    verify_evidence_signature,
)
from services.private_mesh.node_agent import (
    NodeAdmissionResult,
    NodeAgentStatus,
    NodeExecutionResult,
)
from services.private_mesh.ssh_smoke import NodeTarget, SshCarrier

_MODEL_MOUNT = "/work/input/model.onnx"
_DOCUMENT_MOUNT = "/work/input/document.txt"


def _to_dict(doc: Any) -> dict[str, Any]:
    if isinstance(doc, (str, bytes, bytearray)):
        return json.loads(doc)
    if isinstance(doc, Mapping):
        return dict(doc)
    return doc.model_dump(mode="json", by_alias=True)


def _coerce(doc: Any, model_class: type) -> Any:
    """Return doc as model_class without a lossy dict roundtrip."""
    if isinstance(doc, model_class):
        return doc
    if isinstance(doc, (str, bytes, bytearray)):
        return model_class.model_validate_json(
            doc if isinstance(doc, (str, bytes)) else bytes(doc)
        )
    if isinstance(doc, Mapping):
        # Route through JSON so wire-string enums (e.g. lease state) parse
        # under the contracts' strict validation.
        return model_class.model_validate_json(json.dumps(dict(doc), allow_nan=False))
    return model_class.model_validate_json(doc.model_dump_json(by_alias=True))


class RemoteBackendError(ValueError):
    """Fail-closed configuration or dispatch error with a stable message."""


class RemoteExecutionBackend:
    """JobExecutionBackend that runs the real model profile on a remote worker."""

    def __init__(
        self,
        *,
        carrier: SshCarrier,
        target: NodeTarget,
        account_id: str,
        keys: list[dict[str, Any]],
        inventory: ResourceInventory | dict[str, Any],
        image_ref: str,
        image_digest: str,
        profile: str = "text-classification.v1",
        evidence_public_key: bytes | None = None,
        evidence_key_id: str | None = None,
    ) -> None:
        if "@sha256:" not in image_ref or image_ref.rsplit("@", 1)[1] != image_digest:
            raise RemoteBackendError("image_ref must be immutable and match image_digest")
        self.carrier = carrier
        self.target = target
        self.account_id = account_id
        self.keys = list(keys)
        self.inventory = _to_dict(inventory)
        self.image_ref = image_ref
        self.image_digest = image_digest
        self.profile = profile
        self.evidence_public_key = evidence_public_key
        self.evidence_key_id = evidence_key_id
        self._pending_jobs: dict[str, dict[str, Any]] = {}
        # Provenance outcome of the most recent execution, for callers that
        # want to surface a trust badge. One of: "verified", "unsigned",
        # "unverifiable" (no enrolled key), or "invalid:<reason>".
        self.last_evidence_status: str | None = None

    def admit_lease(
        self,
        lease: LeaseDocument | Mapping[str, Any] | str | bytes,
        request: ChalRequest | Mapping[str, Any] | str | bytes,
        capability: CapabilityDocument | Mapping[str, Any] | str | bytes,
        *,
        authenticated_subject_id: str,
    ) -> NodeAdmissionResult:
        try:
            lease_obj = _coerce(lease, LeaseDocument)
            request_obj = _coerce(request, ChalRequest)
            capability_obj = _coerce(capability, CapabilityDocument)
        except Exception as exc:
            return NodeAdmissionResult(
                status=NodeAgentStatus.MALFORMED_DOCUMENT,
                accepted=False,
                reason=f"malformed document: {exc}",
            )
        lease_id = lease_obj.lease_id
        if not lease_id:
            return NodeAdmissionResult(
                status=NodeAgentStatus.MALFORMED_DOCUMENT,
                accepted=False,
                reason="lease document missing lease_id",
            )
        if lease_obj.node_id != self.target.node_id:
            return NodeAdmissionResult(
                status=NodeAgentStatus.NODE_MISMATCH,
                accepted=False,
                reason="lease node does not match the remote worker",
            )
        lease_sha256 = document_sha256(lease_obj)
        request_sha256 = document_sha256(request_obj)
        self._pending_jobs[lease_id] = {
            "lease": _to_dict(lease_obj),
            "request": _to_dict(request_obj),
            "capability": _to_dict(capability_obj),
        }
        # ADMITTED here means "allocated and queued for remote dispatch"; the
        # worker performs signature-verified admission at execute time.
        return NodeAdmissionResult(
            status=NodeAgentStatus.ADMITTED,
            accepted=True,
            lease_id=lease_id,
            lease_sha256=lease_sha256,
            request_sha256=request_sha256,
            workload_id=f"workload:{request_sha256[:24]}",
        )

    def _executor_spec(self, bundle: bytes) -> dict[str, Any]:
        try:
            manifest = json.loads(bundle)
        except ValueError as exc:
            raise RemoteBackendError("bundle is not a JSON workload manifest") from exc
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise RemoteBackendError("workload manifest has no artifacts")
        model_id = document_id = None
        digests: list[str] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise RemoteBackendError("workload artifact descriptor is invalid")
            digests.append(artifact.get("sha256"))
            mount = artifact.get("mount_path")
            if artifact.get("kind") == "model" or mount == _MODEL_MOUNT:
                model_id = artifact.get("artifact_id")
            elif mount == _DOCUMENT_MOUNT:
                document_id = artifact.get("artifact_id")
        outputs = manifest.get("outputs")
        if model_id is None or document_id is None or not isinstance(outputs, list) or not outputs:
            raise RemoteBackendError("manifest does not match the remote model profile")
        if manifest.get("runtime_image", {}).get("digest") != self.image_digest:
            raise RemoteBackendError("manifest runtime image does not match the trusted image")
        return {
            "profile": self.profile,
            "artifact_sha256s": sorted(set(digests)),
            "image_ref": self.image_ref,
            "image_digest": self.image_digest,
            "model_artifact_id": model_id,
            "document_artifact_id": document_id,
            "output_id": outputs[0],
        }

    def execute(
        self,
        *,
        lease_id: str,
        lease_sha256: str,
        fencing_token: int,
        bundle: bytes | bytearray | memoryview,
    ) -> NodeExecutionResult:
        pending = self._pending_jobs.pop(lease_id, None)
        if not pending:
            return NodeExecutionResult(
                status=NodeAgentStatus.REJECTED,
                accepted=False,
                reason="lease not admitted locally",
            )
        data = bytes(bundle)
        try:
            executor = self._executor_spec(data)
        except RemoteBackendError as exc:
            return NodeExecutionResult(
                status=NodeAgentStatus.REJECTED,
                accepted=False,
                reason=str(exc),
            )
        job = {
            "schema": "planetary.private_mesh.ssh_job.v2",
            "account_id": self.account_id,
            "node_id": self.target.node_id,
            "audience": self.target.node_id,
            "keys": self.keys,
            "inventory": self.inventory,
            "request": pending["request"],
            "capability": pending["capability"],
            "lease": pending["lease"],
            "bundle_base64": base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii"),
            "executor": executor,
        }
        try:
            result = self.carrier.execute(self.target, job)
        except Exception as exc:
            return NodeExecutionResult(
                status=NodeAgentStatus.UNAVAILABLE,
                accepted=False,
                reason=f"carrier execution failed: {exc}",
            )
        if not isinstance(result, dict):
            return NodeExecutionResult(
                status=NodeAgentStatus.UNAVAILABLE,
                accepted=False,
                reason="carrier returned invalid result type",
            )
        admission = result.get("admission")
        if not isinstance(admission, dict) or not admission.get("accepted"):
            reason = (
                admission.get("reason", "remote admission rejected")
                if isinstance(admission, dict)
                else "missing remote admission"
            )
            return NodeExecutionResult(
                status=NodeAgentStatus.REJECTED,
                accepted=False,
                reason=reason,
            )
        execution = result.get("execution")
        if not isinstance(execution, dict):
            return NodeExecutionResult(
                status=NodeAgentStatus.UNAVAILABLE,
                accepted=False,
                reason="remote execution returned no execution data",
            )
        try:
            status = NodeAgentStatus(execution.get("status"))
        except (ValueError, TypeError):
            status = NodeAgentStatus.UNAVAILABLE
        response_data = execution.get("response")
        response = (
            ChalResponse.model_validate_json(json.dumps(response_data, allow_nan=False))
            if response_data
            else None
        )
        events = tuple(
            LifecycleEvent.model_validate_json(json.dumps(event, allow_nan=False))
            for event in execution.get("lifecycle_events", [])
        )
        error_data = execution.get("error")
        error = (
            ErrorFrame.model_validate_json(json.dumps(error_data, allow_nan=False))
            if error_data
            else None
        )
        report_b64 = execution.get("report_base64")
        report = base64.urlsafe_b64decode(report_b64 + "==") if report_b64 else None
        self.last_evidence_status = self._check_evidence(
            execution.get("evidence_signature"), report
        )
        return NodeExecutionResult(
            status=status,
            accepted=execution.get("accepted", False),
            response=response,
            lifecycle_events=events,
            report=report,
            error=error,
            reason=execution.get("reason"),
        )

    def _check_evidence(self, envelope: Any, report: bytes | None) -> str:
        """Verify the worker's detached evidence signature; never raise.

        Verification always runs and its outcome is always recorded, so a
        caller that chooses not to *enforce* provenance can still show the user
        which state a result is in. Enforcement belongs to the caller.
        """

        if report is None:
            return "unsigned"
        if envelope is None:
            return "unsigned"
        if self.evidence_public_key is None:
            return "unverifiable"
        try:
            verify_evidence_signature(
                envelope,
                report,
                account_id=self.account_id,
                node_id=self.target.node_id,
                public_key=self.evidence_public_key,
                key_id=self.evidence_key_id,
            )
        except EvidenceSignatureError as exc:
            return f"invalid:{exc}"
        return "verified"

    def cancel(
        self,
        *,
        lease_id: str,
        lease_sha256: str,
        fencing_token: int,
    ) -> NodeExecutionResult:
        # Cancel is only meaningful before dispatch; a dispatched v2 job runs
        # to a signed terminal state on the worker. Dropping the pending job
        # here lets the pipeline durably revoke the (scheduler-signed) lease,
        # which is the authoritative cancellation proof.
        existed = self._pending_jobs.pop(lease_id, None) is not None
        if not existed:
            return NodeExecutionResult(
                status=NodeAgentStatus.REJECTED,
                accepted=False,
                reason="lease not admitted locally",
            )
        return NodeExecutionResult(
            status=NodeAgentStatus.CANCELLED,
            accepted=True,
        )
