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
from services.private_mesh.node_agent import (
    NodeAdmissionResult,
    NodeAgentStatus,
    NodeExecutionResult,
)
from services.private_mesh.ssh_smoke import NodeTarget, SshCarrier


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
        return model_class.model_validate_json(doc if isinstance(doc, (str, bytes)) else bytes(doc))
    if isinstance(doc, Mapping):
        return model_class.model_validate(dict(doc))
    # Another Pydantic model — go through json to avoid cross-model field conflicts
    return model_class.model_validate_json(doc.model_dump_json(by_alias=True))


class RemoteExecutionBackend:
    """A generic JobExecutionBackend that triggers remote executions via SshCarrier."""

    def __init__(
        self,
        *,
        carrier: SshCarrier,
        target: NodeTarget,
        account_id: str,
        keys: list[dict[str, Any]],
        inventory: ResourceInventory | dict[str, Any],
    ) -> None:
        self.carrier = carrier
        self.target = target
        self.account_id = account_id
        self.keys = list(keys)
        self.inventory = _to_dict(inventory)
        self._pending_jobs: dict[str, dict[str, Any]] = {}

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
        except Exception as e:
            return NodeAdmissionResult(
                status=NodeAgentStatus.MALFORMED_DOCUMENT,
                accepted=False,
                reason=f"malformed document: {e}",
            )

        lease_id = lease_obj.lease_id
        if not lease_id:
            return NodeAdmissionResult(
                status=NodeAgentStatus.MALFORMED_DOCUMENT,
                accepted=False,
                reason="lease document missing lease_id",
            )

        lease_sha256 = document_sha256(lease_obj)
        request_sha256 = document_sha256(request_obj)

        # Store as dicts for wire serialisation during execute()
        self._pending_jobs[lease_id] = {
            "lease": _to_dict(lease_obj),
            "request": _to_dict(request_obj),
            "capability": _to_dict(capability_obj),
        }

        # Optimistically return admitted, real admission happens on execute via worker CLI
        return NodeAdmissionResult(
            status=NodeAgentStatus.ADMITTED,
            accepted=True,
            lease_id=lease_id,
            lease_sha256=lease_sha256,
            request_sha256=request_sha256,
            workload_id=f"workload:{request_sha256[:24]}",
        )

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

        job = {
            "schema": "planetary.private_mesh.ssh_job.v1",
            "account_id": self.account_id,
            "node_id": self.target.node_id,
            "audience": self.target.node_id,
            "keys": self.keys,
            "inventory": self.inventory,
            "request": pending["request"],
            "capability": pending["capability"],
            "lease": pending["lease"],
            "bundle_base64": base64.urlsafe_b64encode(bytes(bundle)).rstrip(b"=").decode("ascii"),
        }

        try:
            result = self.carrier.execute(self.target, job)
        except Exception as e:
            return NodeExecutionResult(
                status=NodeAgentStatus.UNAVAILABLE,
                accepted=False,
                reason=f"carrier execution failed: {e}",
            )

        if not isinstance(result, dict):
            return NodeExecutionResult(
                status=NodeAgentStatus.UNAVAILABLE,
                accepted=False,
                reason="carrier returned invalid result type",
            )

        admission = result.get("admission")
        if not isinstance(admission, dict) or not admission.get("accepted"):
            reason = admission.get("reason", "remote admission rejected") if isinstance(admission, dict) else "missing remote admission"
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

        status_str = execution.get("status")
        try:
            status = NodeAgentStatus(status_str)
        except (ValueError, TypeError):
            status = NodeAgentStatus.UNAVAILABLE

        response_data = execution.get("response")
        response = (
            ChalResponse.model_validate_json(json.dumps(response_data, allow_nan=False))
            if response_data
            else None
        )

        events_data = execution.get("lifecycle_events", [])
        events = tuple(
            LifecycleEvent.model_validate_json(json.dumps(e, allow_nan=False))
            for e in events_data
        )

        error_data = execution.get("error")
        error = (
            ErrorFrame.model_validate_json(json.dumps(error_data, allow_nan=False))
            if error_data
            else None
        )

        report_b64 = execution.get("report_base64")
        report = None
        if report_b64:
            report = base64.urlsafe_b64decode(report_b64 + "==")

        return NodeExecutionResult(
            status=status,
            accepted=execution.get("accepted", False),
            response=response,
            lifecycle_events=events,
            report=report,
            error=error,
            reason=execution.get("reason"),
        )

    def cancel(
        self,
        *,
        lease_id: str,
        lease_sha256: str,
        fencing_token: int,
    ) -> NodeExecutionResult:
        self._pending_jobs.pop(lease_id, None)
        return NodeExecutionResult(
            status=NodeAgentStatus.CANCELLED,
            accepted=True,
        )
