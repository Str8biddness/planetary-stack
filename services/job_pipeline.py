"""Authenticated local job pipeline from desktop intent to verified result.

This is the Release A single-cell composition behind the synthesusd job API:
one signed CHAL request per job, vSource placement and a signed fenced lease,
node-agent admission, real workload execution behind the injected node-agent
executor boundary, and a signed lease-bound response whose outputs are
content-addressed result references.  The pipeline never fabricates results:
every state transition it reports is backed by a signed contract document or
an explicit fail-closed reason.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from threading import RLock
from typing import Any, Protocol

from contracts.chal_vsource.v1.canonical import document_sha256
from contracts.chal_vsource.v1.models import (
    CapabilityDocument,
    ChalRequest,
    LeaseDocument,
    LeaseRevocationReason,
    WorkloadKind,
)
from services.private_mesh.node_agent import (
    NodeAdmissionResult,
    NodeAgentStatus,
    NodeExecutionResult,
)
from services.vsource.control_plane import (
    DocumentSigner,
    LocalVSourceControlPlane,
    sign_contract_document,
)

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{2,127}$")
_DEFAULT_MAX_BUNDLE_BYTES = 8 * 1024 * 1024
_WIRE_TIME = "%Y-%m-%dT%H:%M:%SZ"


class JobExecutionBackend(Protocol):
    def admit_lease(
        self,
        lease: LeaseDocument | Mapping[str, Any] | str | bytes,
        request: ChalRequest | Mapping[str, Any] | str | bytes,
        capability: CapabilityDocument | Mapping[str, Any] | str | bytes,
        *,
        authenticated_subject_id: str,
    ) -> NodeAdmissionResult: ...

    def execute(
        self,
        *,
        lease_id: str,
        lease_sha256: str,
        fencing_token: int,
        bundle: bytes | bytearray | memoryview,
    ) -> NodeExecutionResult: ...

    def cancel(
        self,
        *,
        lease_id: str,
        lease_sha256: str,
        fencing_token: int,
    ) -> NodeExecutionResult: ...


class JobState(StrEnum):
    ADMITTED = "admitted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


_TERMINAL_STATES = {
    JobState.COMPLETED,
    JobState.FAILED,
    JobState.CANCELLED,
    JobState.REJECTED,
}


@dataclass
class JobRecord:
    job_id: str
    state: JobState
    reason: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    lease_id: str | None = None
    lease_sha256: str | None = None
    fencing_token: int | None = None
    renewal_sequence: int | None = None
    created_at: str | None = None
    completed_at: str | None = None
    outputs: tuple[Mapping[str, Any], ...] = ()
    report: bytes | None = None
    _lease: LeaseDocument | None = field(default=None, repr=False)
    _bundle: bytes | None = field(default=None, repr=False)

    def to_wire(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state.value,
            "reason": self.reason,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "lease_id": self.lease_id,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "outputs": [dict(output) for output in self.outputs],
        }


class LocalJobPipeline:
    """Drive one authenticated desktop job through the full local cell."""

    def __init__(
        self,
        *,
        control_plane: LocalVSourceControlPlane,
        backend: JobExecutionBackend,
        request_signer: DocumentSigner,
        capability_provider: Callable[[], CapabilityDocument],
        authenticated_subject_id: str,
        account_id: str,
        capability_id: str,
        device_uri: str = "chal://aivm/inference",
        clock: Callable[[], datetime],
        resource_vector: Mapping[str, int],
        max_bundle_bytes: int = _DEFAULT_MAX_BUNDLE_BYTES,
        max_jobs: int = 1024,
        result_loader: Callable[[str], bytes | None] | None = None,
    ) -> None:
        if control_plane is None or backend is None or request_signer is None:
            raise ValueError("control plane, backend, and signer are required")
        if capability_provider is None or clock is None:
            raise ValueError("capability provider and clock are required")
        if not _IDENTIFIER_RE.fullmatch(account_id):
            raise ValueError("account_id must be a canonical identifier")
        if not _IDENTIFIER_RE.fullmatch(capability_id):
            raise ValueError("capability_id must be a canonical identifier")
        if max_bundle_bytes < 1 or max_jobs < 1:
            raise ValueError("bundle and job limits must be positive")
        self._control_plane = control_plane
        self._backend = backend
        self._request_signer = request_signer
        self._capability_provider = capability_provider
        self._subject_id = authenticated_subject_id
        self._account_id = account_id
        self._capability_id = capability_id
        self._device_uri = device_uri
        self._clock = clock
        self._resource_vector = dict(resource_vector)
        self._max_bundle_bytes = max_bundle_bytes
        self._max_jobs = max_jobs
        self._result_loader = result_loader
        self._jobs: dict[str, JobRecord] = {}
        self._lock = RLock()

    def _now_wire(self) -> tuple[datetime, str]:
        now = self._clock()
        return now, now.strftime(_WIRE_TIME)

    def _request_payload(
        self,
        *,
        job_id: str,
        bundle_sha256: str,
        bundle_size: int,
        workload_kind: WorkloadKind,
        issued_at: str,
    ) -> dict[str, Any]:
        suffix = job_id.split(":", 1)[1]
        return {
            "schema": "planetary.chal.request.v1",
            "request_id": f"request:{suffix}",
            "trace_id": f"trace:{suffix}",
            "parent_request_id": None,
            "issued_at": issued_at,
            "ttl_seconds": 300,
            "idempotency_key": f"idempotency:{suffix}",
            "account_id": self._account_id,
            "capability_id": self._capability_id,
            "device_uri": self._device_uri,
            "workload_kind": workload_kind.value,
            "workload_manifest": {
                "uri": f"artifact://private-mesh/workload/{bundle_sha256}",
                "sha256": bundle_sha256,
                "size_bytes": bundle_size,
                "media_type": "application/vnd.planetary.manifest+json",
                "classification": "private",
            },
            "inputs": [],
            "parameters": {
                "batch_size": None,
                "max_tokens": None,
                "temperature": None,
                "top_k": None,
                "seed": 0,
                "precision": "auto",
                "checkpoint_interval_seconds": None,
                "replica_count": None,
                "chunk_size": None,
                "width": None,
                "height": None,
                "steps": None,
                "deterministic": True,
            },
            "constraints": {
                "resources": dict(self._resource_vector),
                "latency_budget_ms": 300_000,
                "grounding_required": True,
                "template_leakage_allowed": False,
                "network_access": "none",
                "checkpoint_required": False,
            },
        }

    def submit(
        self,
        *,
        bundle: bytes,
        workload_kind: str = "inference",
        start: bool = True,
    ) -> JobRecord:
        if not isinstance(bundle, (bytes, bytearray, memoryview)):
            return JobRecord(
                job_id=f"job:invalid:{secrets.token_hex(6)}",
                state=JobState.REJECTED,
                reason="bundle must be bytes",
            )
        data = bytes(bundle)
        if not data or len(data) > self._max_bundle_bytes:
            return JobRecord(
                job_id=f"job:invalid:{secrets.token_hex(6)}",
                state=JobState.REJECTED,
                reason="bundle size is out of policy",
            )
        try:
            kind = WorkloadKind(workload_kind)
        except ValueError:
            return JobRecord(
                job_id=f"job:invalid:{secrets.token_hex(6)}",
                state=JobState.REJECTED,
                reason="unsupported workload kind",
            )
        bundle_sha256 = hashlib.sha256(data).hexdigest()
        job_id = f"job:{bundle_sha256[:16]}-{secrets.token_hex(4)}"
        with self._lock:
            if len(self._jobs) >= self._max_jobs:
                return JobRecord(
                    job_id=job_id,
                    state=JobState.REJECTED,
                    reason="job store is full",
                )
            try:
                now, now_wire = self._now_wire()
            except Exception:
                return JobRecord(
                    job_id=job_id,
                    state=JobState.UNAVAILABLE,
                    reason="clock unavailable",
                )
            try:
                capability = self._capability_provider()
                request = sign_contract_document(
                    ChalRequest,
                    self._request_payload(
                        job_id=job_id,
                        bundle_sha256=bundle_sha256,
                        bundle_size=len(data),
                        workload_kind=kind,
                        issued_at=now_wire,
                    ),
                    self._request_signer,
                )
            except Exception:
                return JobRecord(
                    job_id=job_id,
                    state=JobState.UNAVAILABLE,
                    reason="request signing unavailable",
                )
            allocation = self._control_plane.allocate(
                request,
                capability,
                authenticated_subject_id=self._subject_id,
            )
            if not allocation.accepted or allocation.lease is None:
                record = JobRecord(
                    job_id=job_id,
                    state=JobState.REJECTED,
                    reason=allocation.reason or allocation.status.value,
                    request_id=request.request_id,
                    trace_id=request.trace_id,
                    created_at=now_wire,
                )
                self._jobs[job_id] = record
                return record
            lease = allocation.lease
            admission = self._backend.admit_lease(
                lease,
                request,
                capability,
                authenticated_subject_id=self._subject_id,
            )
            if not admission.accepted:
                record = JobRecord(
                    job_id=job_id,
                    state=JobState.REJECTED,
                    reason=admission.reason or admission.status.value,
                    request_id=request.request_id,
                    trace_id=request.trace_id,
                    lease_id=lease.lease_id,
                    created_at=now_wire,
                )
                self._jobs[job_id] = record
                self._release_lease_quietly(lease)
                return record
            record = JobRecord(
                job_id=job_id,
                state=JobState.ADMITTED,
                request_id=request.request_id,
                trace_id=request.trace_id,
                lease_id=lease.lease_id,
                lease_sha256=document_sha256(lease),
                fencing_token=lease.fencing_token,
                renewal_sequence=lease.renewal_sequence,
                created_at=now_wire,
                _lease=lease,
                _bundle=data,
            )
            self._jobs[job_id] = record
            if start:
                return self._run_locked(record)
            return record

    def run(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            if record.state is not JobState.ADMITTED:
                return record
            return self._run_locked(record)

    def _run_locked(self, record: JobRecord) -> JobRecord:
        assert record._lease is not None and record._bundle is not None
        assert record.lease_sha256 is not None and record.fencing_token is not None
        result = self._backend.execute(
            lease_id=record._lease.lease_id,
            lease_sha256=record.lease_sha256,
            fencing_token=record.fencing_token,
            bundle=record._bundle,
        )
        _, now_wire = self._now_wire()
        if result.status is NodeAgentStatus.EXECUTED and result.response is not None:
            record.state = JobState.COMPLETED
            record.completed_at = now_wire
            record.outputs = tuple(
                output.model_dump(mode="json") for output in result.response.outputs
            )
            record.report = result.report
            record.reason = None
            self._release_lease_quietly(record._lease)
        elif result.status is NodeAgentStatus.UNAVAILABLE:
            record.state = JobState.ADMITTED
            record.reason = result.reason or "execution unavailable"
        else:
            record.state = JobState.FAILED
            record.completed_at = now_wire
            record.reason = result.reason or result.status.value
            self._release_lease_quietly(record._lease)
        if record.state in _TERMINAL_STATES:
            record._bundle = None
        return record

    def cancel(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            if record.state is not JobState.ADMITTED:
                return record
            assert record._lease is not None
            assert record.lease_sha256 is not None and record.fencing_token is not None
            cancelled = self._backend.cancel(
                lease_id=record._lease.lease_id,
                lease_sha256=record.lease_sha256,
                fencing_token=record.fencing_token,
            )
            if cancelled.status is not NodeAgentStatus.CANCELLED:
                record.reason = cancelled.reason or cancelled.status.value
                return record
            _, now_wire = self._now_wire()
            revoked = self._control_plane.revoke_lease(
                record._lease.lease_id,
                lease_sha256=record.lease_sha256,
                fencing_token=record.fencing_token,
                renewal_sequence=record._lease.renewal_sequence,
                revocation_reason=LeaseRevocationReason.OWNER_REQUEST,
            )
            record.state = JobState.CANCELLED
            record.completed_at = now_wire
            record.reason = None if revoked.accepted else "lease revocation degraded"
            record._bundle = None
            return record

    def status(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def result(self, job_id: str, output_sha256: str) -> tuple[bytes, str] | None:
        """Return exact verified result bytes for one completed-job output.

        Only digests recorded in the job's signed response outputs are
        servable, and the loaded bytes must re-hash to the requested digest;
        anything else returns None rather than unverified content.
        """

        if self._result_loader is None:
            return None
        if not isinstance(output_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", output_sha256
        ):
            return None
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None or record.state is not JobState.COMPLETED:
                return None
            matching = next(
                (
                    output
                    for output in record.outputs
                    if output.get("sha256") == output_sha256
                ),
                None,
            )
        if matching is None:
            return None
        try:
            payload = self._result_loader(output_sha256)
        except Exception:
            return None
        if not isinstance(payload, (bytes, bytearray)):
            return None
        data = bytes(payload)
        if hashlib.sha256(data).hexdigest() != output_sha256:
            return None
        media_type = str(matching.get("media_type") or "application/octet-stream")
        return data, media_type

    def _release_lease_quietly(self, lease: LeaseDocument) -> None:
        try:
            self._control_plane.release_lease(
                lease.lease_id,
                lease_sha256=document_sha256(lease),
                fencing_token=lease.fencing_token,
                renewal_sequence=lease.renewal_sequence,
            )
        except Exception:
            pass
