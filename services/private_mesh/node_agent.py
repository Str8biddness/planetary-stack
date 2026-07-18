"""Signed private-mesh node-agent boundary.

This module implements the node-side admission and execution bridge for the
frozen CHAL/vSource v1 contract. It consumes only signed v1 documents, admits
one fenced lease revision at a time, and executes a single deterministic
SHA-256 hash-and-report operation over opaque workload bytes.

The boundary is transport-neutral and in-process: it binds no socket and
spawns nothing. The coordinator later drives two enrolled agents over pinned
SSH/mTLS transports using exactly this interface. Arbitrary entrypoints,
bytecode, pickle, and command execution are not part of this boundary.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import RLock
from typing import Any, Protocol, TypeVar

import rfc8785
from cryptography.exceptions import InvalidSignature
from pydantic import BaseModel, ValidationError

from contracts.chal_vsource.v1.canonical import document_sha256, signing_bytes
from contracts.chal_vsource.v1.models import (
    AttestationLevel,
    CapabilityAction,
    CapabilityDocument,
    ChalRequest,
    ChalResponse,
    ContentReference,
    ErrorCode,
    ErrorFrame,
    LeaseDocument,
    LeaseState,
    LifecycleEvent,
    LifecycleState,
    NodeHealth,
    ResourceInventory,
    ResponseStatus,
    Signature,
    device_uri_matches_prefix,
    resource_vector_within,
    validate_lease_bound_lifecycle,
    validate_lease_bound_response,
)
from services.vsource.control_plane import KeyRecord, sign_contract_document


ModelT = TypeVar("ModelT", bound=BaseModel)

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{2,127}$")
_HOST_RESOURCE_FIELDS = (
    "cpu_millicores",
    "memory_bytes",
    "storage_bytes",
    "ingress_bps",
    "egress_bps",
)
_ATTESTATION_RANK = {
    AttestationLevel.UNVERIFIED: 0,
    AttestationLevel.SOFTWARE_VERIFIED: 1,
    AttestationLevel.HARDWARE_VERIFIED: 2,
}
_DEFAULT_MAX_BUNDLE_BYTES = 64 * 1024 * 1024
_DEFAULT_MAX_ERROR_FRAMES = 64
HASH_REPORT_SCHEMA = "planetary.private_mesh.hash_report.v1"
HASH_REPORT_MEDIA_TYPE = "application/vnd.planetary.hash-report+json"


class NodeAgentStatus(StrEnum):
    ADMITTED = "admitted"
    RENEWED = "renewed"
    EXECUTED = "executed"
    EXECUTION_FAILED = "execution_failed"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"
    MALFORMED_DOCUMENT = "malformed_document"
    UNKNOWN_KEY = "unknown_key"
    KEY_REVOKED = "key_revoked"
    INVALID_SIGNATURE = "invalid_signature"
    ACCOUNT_MISMATCH = "account_mismatch"
    NODE_MISMATCH = "node_mismatch"
    SUBJECT_MISMATCH = "subject_mismatch"
    AUDIENCE_MISMATCH = "audience_mismatch"
    CAPABILITY_MISMATCH = "capability_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"
    TRANSPORT_UNSUPPORTED = "transport_unsupported"
    WORKLOAD_REJECTED = "workload_rejected"
    LEASE_NOT_ACTIVE = "lease_not_active"
    LEASE_REVOKED = "lease_revoked"
    LEASE_EXPIRED = "lease_expired"
    DOCUMENT_EXPIRED = "document_expired"
    CLOCK_SKEW = "clock_skew"
    STALE_LEASE = "stale_lease"
    REPLAY = "replay"
    DUPLICATE_TRANSITION = "duplicate_transition"
    BUNDLE_MISMATCH = "bundle_mismatch"
    REJECTED = "rejected"


_FRAME_ERROR_CODES: dict[NodeAgentStatus, ErrorCode] = {
    NodeAgentStatus.MALFORMED_DOCUMENT: ErrorCode.INVALID_REQUEST,
    NodeAgentStatus.UNKNOWN_KEY: ErrorCode.UNAUTHORIZED,
    NodeAgentStatus.KEY_REVOKED: ErrorCode.UNAUTHORIZED,
    NodeAgentStatus.INVALID_SIGNATURE: ErrorCode.UNAUTHORIZED,
    NodeAgentStatus.ACCOUNT_MISMATCH: ErrorCode.FORBIDDEN,
    NodeAgentStatus.NODE_MISMATCH: ErrorCode.FORBIDDEN,
    NodeAgentStatus.SUBJECT_MISMATCH: ErrorCode.FORBIDDEN,
    NodeAgentStatus.AUDIENCE_MISMATCH: ErrorCode.FORBIDDEN,
    NodeAgentStatus.CAPABILITY_MISMATCH: ErrorCode.FORBIDDEN,
    NodeAgentStatus.DIGEST_MISMATCH: ErrorCode.INTEGRITY_FAILURE,
    NodeAgentStatus.TRANSPORT_UNSUPPORTED: ErrorCode.TRANSPORT_UNAVAILABLE,
    NodeAgentStatus.WORKLOAD_REJECTED: ErrorCode.WORKLOAD_REJECTED,
    NodeAgentStatus.LEASE_NOT_ACTIVE: ErrorCode.LEASE_CONFLICT,
    NodeAgentStatus.LEASE_REVOKED: ErrorCode.LEASE_CONFLICT,
    NodeAgentStatus.LEASE_EXPIRED: ErrorCode.LEASE_EXPIRED,
    NodeAgentStatus.DOCUMENT_EXPIRED: ErrorCode.CAPABILITY_EXPIRED,
    NodeAgentStatus.CLOCK_SKEW: ErrorCode.INVALID_REQUEST,
    NodeAgentStatus.STALE_LEASE: ErrorCode.LEASE_CONFLICT,
    NodeAgentStatus.REPLAY: ErrorCode.LEASE_CONFLICT,
    NodeAgentStatus.DUPLICATE_TRANSITION: ErrorCode.LEASE_CONFLICT,
    NodeAgentStatus.BUNDLE_MISMATCH: ErrorCode.INTEGRITY_FAILURE,
    NodeAgentStatus.EXECUTION_FAILED: ErrorCode.WORKLOAD_FAILED,
    NodeAgentStatus.REJECTED: ErrorCode.WORKLOAD_REJECTED,
}


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current UTC-aware time."""


class KeyResolver(Protocol):
    def resolve_key(self, key_id: str) -> KeyRecord | None:
        """Return key metadata, or None when the key is unknown."""


class DocumentSigner(Protocol):
    @property
    def key_id(self) -> str:
        """Key identifier to place in the contract signature field."""

    def sign(self, payload: bytes) -> bytes:
        """Return an Ed25519 signature for already canonicalized bytes."""


@dataclass(frozen=True)
class VerificationResult:
    status: NodeAgentStatus | None
    digest: str | None = None
    key: KeyRecord | None = None

    @property
    def verified(self) -> bool:
        return self.status is None


class DocumentVerifier(Protocol):
    def verify_document(
        self,
        document: BaseModel,
        *,
        expected_account_id: str,
        expected_node_id: str | None = None,
    ) -> VerificationResult:
        """Verify one signed contract document against enrolled keys."""


def _normalized_now(clock: Clock) -> datetime | None:
    try:
        now = clock.now()
    except Exception:
        return None
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return None
    return now.astimezone(UTC).replace(microsecond=0)


def _wire_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Ed25519DocumentVerifier:
    """Enrollment-backed Ed25519 verifier for signed v1 documents."""

    key_resolver: KeyResolver
    clock: Clock
    audience: str
    max_clock_skew_seconds: int = 60

    def verify_document(
        self,
        document: BaseModel,
        *,
        expected_account_id: str,
        expected_node_id: str | None = None,
    ) -> VerificationResult:
        now = _normalized_now(self.clock)
        if now is None:
            return VerificationResult(NodeAgentStatus.UNAVAILABLE)
        skew = timedelta(seconds=self.max_clock_skew_seconds)
        signature = getattr(document, "signature", None)
        if not isinstance(signature, Signature):
            return VerificationResult(NodeAgentStatus.MALFORMED_DOCUMENT)
        try:
            key = self.key_resolver.resolve_key(signature.key_id)
        except Exception:
            return VerificationResult(NodeAgentStatus.UNAVAILABLE)
        if key is None:
            return VerificationResult(NodeAgentStatus.UNKNOWN_KEY)
        if key.revoked:
            return VerificationResult(NodeAgentStatus.KEY_REVOKED)
        if key.account_id != expected_account_id:
            return VerificationResult(NodeAgentStatus.ACCOUNT_MISMATCH)
        audiences = set(key.audiences)
        if self.audience not in audiences and "*" not in audiences:
            return VerificationResult(NodeAgentStatus.AUDIENCE_MISMATCH)
        if expected_node_id is not None and key.node_id != expected_node_id:
            return VerificationResult(NodeAgentStatus.NODE_MISMATCH)
        if key.not_before is not None and now + skew < key.not_before:
            return VerificationResult(NodeAgentStatus.CLOCK_SKEW)
        if key.not_after is not None and now >= key.not_after:
            return VerificationResult(NodeAgentStatus.KEY_REVOKED)
        if isinstance(document, CapabilityDocument) and (
            document.revocation_epoch < key.minimum_capability_revocation_epoch
        ):
            return VerificationResult(NodeAgentStatus.KEY_REVOKED)
        try:
            signature_bytes = base64.urlsafe_b64decode(signature.value + "==")
            key.ed25519_public_key().verify(signature_bytes, signing_bytes(document))
        except (InvalidSignature, ValueError):
            return VerificationResult(NodeAgentStatus.INVALID_SIGNATURE)
        window = self._validate_window(document, now, skew)
        if window is not None:
            return VerificationResult(window)
        return VerificationResult(None, document_sha256(document), key)

    def _validate_window(
        self,
        document: BaseModel,
        now: datetime,
        skew: timedelta,
    ) -> NodeAgentStatus | None:
        if isinstance(document, ChalRequest):
            return self._ttl_window(document.issued_at, document.ttl_seconds, now, skew)
        if isinstance(document, CapabilityDocument):
            return self._ttl_window(document.not_before, document.ttl_seconds, now, skew)
        if isinstance(document, ResourceInventory):
            return self._ttl_window(document.observed_at, document.ttl_seconds, now, skew)
        return None

    @staticmethod
    def _ttl_window(
        starts_at: datetime,
        ttl_seconds: int,
        now: datetime,
        skew: timedelta,
    ) -> NodeAgentStatus | None:
        if now + skew < starts_at:
            return NodeAgentStatus.CLOCK_SKEW
        if now >= starts_at + timedelta(seconds=ttl_seconds):
            return NodeAgentStatus.DOCUMENT_EXPIRED
        return None


@dataclass(frozen=True)
class NodeAdmissionResult:
    status: NodeAgentStatus
    accepted: bool
    lease_id: str | None = None
    lease_sha256: str | None = None
    request_sha256: str | None = None
    workload_id: str | None = None
    lifecycle_event: LifecycleEvent | None = None
    error: ErrorFrame | None = None
    reason: str | None = None


@dataclass(frozen=True)
class NodeExecutionResult:
    status: NodeAgentStatus
    accepted: bool
    response: ChalResponse | None = None
    lifecycle_events: tuple[LifecycleEvent, ...] = ()
    report: bytes | None = None
    error: ErrorFrame | None = None
    reason: str | None = None


@dataclass(frozen=True)
class WorkloadExecutionOutcome:
    """Result of one real workload execution behind the node agent.

    ``outputs`` must be content references to immutable, content-addressed
    result artifacts.  ``unavailable`` marks environmental failures where the
    executor could not run at all; every other non-ok outcome is a terminal
    workload failure.
    """

    ok: bool
    outputs: tuple[Mapping[str, Any], ...] = ()
    report: bytes | None = None
    reason: str | None = None
    unavailable: bool = False


class WorkloadExecutor(Protocol):
    """Isolated execution boundary invoked after every admission gate passed.

    Implementations must never run manifest text as commands, must enforce
    their own replay/authority consumption, and must return content-addressed
    outputs with provenance evidence.
    """

    def execute_workload(
        self,
        *,
        lease: LeaseDocument,
        request: ChalRequest,
        bundle: bytes,
    ) -> WorkloadExecutionOutcome:
        """Execute the admitted workload bundle exactly once."""


@dataclass
class _AdmittedWorkload:
    lease: LeaseDocument
    lease_sha256: str
    request: ChalRequest
    request_sha256: str
    workload_id: str
    bundle_sha256: str
    bundle_size_bytes: int
    sequence: int
    state: LifecycleState


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON key is not allowed: {key}")
        seen.add(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-I-JSON numeric value is not allowed: {value}")


def _strict_parse(
    model_type: type[ModelT],
    document: ModelT | Mapping[str, Any] | str | bytes | bytearray,
) -> tuple[ModelT | None, NodeAgentStatus | None]:
    try:
        if isinstance(document, model_type):
            return document, None
        if isinstance(document, (str, bytes, bytearray)):
            payload = json.loads(
                document,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_json_constant,
            )
        elif isinstance(document, Mapping):
            payload = dict(document)
        else:
            return None, NodeAgentStatus.MALFORMED_DOCUMENT
        if not isinstance(payload, dict):
            return None, NodeAgentStatus.MALFORMED_DOCUMENT
        encoded = json.dumps(payload, allow_nan=False, separators=(",", ":"))
        return model_type.model_validate_json(encoded), None
    except (TypeError, ValueError, ValidationError):
        return None, NodeAgentStatus.MALFORMED_DOCUMENT


class NodeAgent:
    """Verify-then-execute boundary for one enrolled private-mesh node.

    Every dependency is injected. A missing verifier, signer, clock, or
    signed inventory makes every operation return an explicit unavailable
    result; nothing falls back to a permissive default.
    """

    def __init__(
        self,
        *,
        account_id: str,
        node_id: str,
        inventory: ResourceInventory | Mapping[str, Any] | str | bytes | None,
        verifier: DocumentVerifier | None,
        signer: DocumentSigner | None,
        clock: Clock | None,
        max_clock_skew_seconds: int = 60,
        max_bundle_bytes: int = _DEFAULT_MAX_BUNDLE_BYTES,
        max_error_frames: int = _DEFAULT_MAX_ERROR_FRAMES,
        workload_executor: WorkloadExecutor | None = None,
    ) -> None:
        if not _IDENTIFIER_RE.fullmatch(account_id):
            raise ValueError("account_id must be a valid contract identifier")
        if not _IDENTIFIER_RE.fullmatch(node_id):
            raise ValueError("node_id must be a valid contract identifier")
        if max_clock_skew_seconds < 0:
            raise ValueError("max_clock_skew_seconds must be non-negative")
        if max_bundle_bytes < 1:
            raise ValueError("max_bundle_bytes must be positive")
        if max_error_frames < 0:
            raise ValueError("max_error_frames must be non-negative")
        self.account_id = account_id
        self.node_id = node_id
        self.verifier = verifier
        self.signer = signer
        self.clock = clock
        self.max_clock_skew = timedelta(seconds=max_clock_skew_seconds)
        self.max_bundle_bytes = max_bundle_bytes
        self.max_error_frames = max_error_frames
        self.workload_executor = workload_executor
        self._inventory: ResourceInventory | None = None
        self._config_error: str | None = None
        if inventory is not None:
            parsed, parse_error = _strict_parse(ResourceInventory, inventory)
            if parse_error is not None:
                self._config_error = "configured inventory is malformed"
            else:
                self._inventory = parsed
        self._workloads: dict[str, _AdmittedWorkload] = {}
        self._error_frames_emitted = 0
        self._lock = RLock()

    def admitted_lease_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._workloads))

    def workload_state(self, lease_id: str) -> LifecycleState | None:
        with self._lock:
            entry = self._workloads.get(lease_id)
            return entry.state if entry is not None else None

    def admit_lease(
        self,
        lease: LeaseDocument | Mapping[str, Any] | str | bytes,
        request: ChalRequest | Mapping[str, Any] | str | bytes,
        capability: CapabilityDocument | Mapping[str, Any] | str | bytes,
        *,
        authenticated_subject_id: str,
    ) -> NodeAdmissionResult:
        with self._lock:
            return self._admit_lease_locked(
                lease,
                request,
                capability,
                authenticated_subject_id=authenticated_subject_id,
            )

    def _admit_lease_locked(
        self,
        lease: LeaseDocument | Mapping[str, Any] | str | bytes,
        request: ChalRequest | Mapping[str, Any] | str | bytes,
        capability: CapabilityDocument | Mapping[str, Any] | str | bytes,
        *,
        authenticated_subject_id: str,
    ) -> NodeAdmissionResult:
        unavailable = self._unavailable_reason()
        if unavailable is not None:
            return NodeAdmissionResult(
                NodeAgentStatus.UNAVAILABLE,
                False,
                reason=unavailable,
            )
        assert self.clock is not None
        assert self.verifier is not None
        inventory = self._inventory
        assert inventory is not None
        now = _normalized_now(self.clock)
        if now is None:
            return NodeAdmissionResult(
                NodeAgentStatus.UNAVAILABLE,
                False,
                reason="clock service failed",
            )

        parsed_lease, parse_error = _strict_parse(LeaseDocument, lease)
        if parse_error is not None:
            return NodeAdmissionResult(parse_error, False, reason="lease document")
        parsed_request, parse_error = _strict_parse(ChalRequest, request)
        if parse_error is not None:
            return NodeAdmissionResult(parse_error, False, reason="request document")
        parsed_capability, parse_error = _strict_parse(CapabilityDocument, capability)
        if parse_error is not None:
            return NodeAdmissionResult(parse_error, False, reason="capability document")
        assert parsed_lease is not None
        assert parsed_request is not None
        assert parsed_capability is not None

        request_verified = self._verify_document(
            parsed_request,
            expected_account_id=self.account_id,
        )
        if not request_verified.verified:
            assert request_verified.status is not None
            return NodeAdmissionResult(
                request_verified.status,
                False,
                reason="request verification failed",
            )
        request_sha256 = request_verified.digest
        if request_sha256 is None:
            return NodeAdmissionResult(
                NodeAgentStatus.UNAVAILABLE,
                False,
                reason="request verifier omitted the document digest",
            )

        status, reason, verified_lease_digest = self._verify_admission_chain(
            parsed_lease,
            parsed_request,
            request_sha256,
            parsed_capability,
            inventory,
            authenticated_subject_id,
            now,
        )
        if status is not None:
            return self._admission_rejection(
                status,
                parsed_request,
                request_sha256,
                parsed_lease,
                reason,
            )
        assert verified_lease_digest is not None
        lease_sha256 = verified_lease_digest
        workload_id = f"workload:{request_sha256[:24]}"

        existing = self._workloads.get(parsed_lease.lease_id)
        if existing is not None:
            return self._admit_renewal(
                existing,
                parsed_lease,
                lease_sha256,
                parsed_request,
                request_sha256,
            )

        entry = _AdmittedWorkload(
            lease=parsed_lease,
            lease_sha256=lease_sha256,
            request=parsed_request,
            request_sha256=request_sha256,
            workload_id=workload_id,
            bundle_sha256=parsed_request.workload_manifest.sha256,
            bundle_size_bytes=parsed_request.workload_manifest.size_bytes,
            sequence=0,
            state=LifecycleState.ADMITTED,
        )
        try:
            event = self._signed_lifecycle_event(
                entry,
                sequence=0,
                previous_state=None,
                state=LifecycleState.ADMITTED,
                occurred_at=now,
            )
        except Exception:
            return NodeAdmissionResult(
                NodeAgentStatus.UNAVAILABLE,
                False,
                reason="lifecycle signing failed",
            )
        self._workloads[parsed_lease.lease_id] = entry
        return NodeAdmissionResult(
            NodeAgentStatus.ADMITTED,
            True,
            lease_id=parsed_lease.lease_id,
            lease_sha256=lease_sha256,
            request_sha256=request_sha256,
            workload_id=workload_id,
            lifecycle_event=event,
        )

    def execute(
        self,
        *,
        lease_id: str,
        lease_sha256: str,
        fencing_token: int,
        bundle: bytes | bytearray | memoryview,
    ) -> NodeExecutionResult:
        with self._lock:
            return self._execute_locked(
                lease_id=lease_id,
                lease_sha256=lease_sha256,
                fencing_token=fencing_token,
                bundle=bundle,
            )

    def _execute_locked(
        self,
        *,
        lease_id: str,
        lease_sha256: str,
        fencing_token: int,
        bundle: bytes | bytearray | memoryview,
    ) -> NodeExecutionResult:
        if not isinstance(lease_id, str) or not _IDENTIFIER_RE.fullmatch(lease_id):
            return NodeExecutionResult(
                NodeAgentStatus.REJECTED,
                False,
                reason="lease_id must be a canonical identifier",
            )
        if not isinstance(lease_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", lease_sha256
        ):
            return NodeExecutionResult(
                NodeAgentStatus.REJECTED,
                False,
                reason="lease_sha256 must be a canonical SHA-256 digest",
            )
        if isinstance(fencing_token, bool) or not isinstance(fencing_token, int):
            return NodeExecutionResult(
                NodeAgentStatus.REJECTED,
                False,
                reason="fencing_token must be an integer",
            )
        unavailable = self._unavailable_reason()
        if unavailable is not None:
            return NodeExecutionResult(
                NodeAgentStatus.UNAVAILABLE,
                False,
                reason=unavailable,
            )
        assert self.clock is not None
        now = _normalized_now(self.clock)
        if now is None:
            return NodeExecutionResult(
                NodeAgentStatus.UNAVAILABLE,
                False,
                reason="clock service failed",
            )
        entry = self._workloads.get(lease_id)
        if entry is None:
            return NodeExecutionResult(
                NodeAgentStatus.REJECTED,
                False,
                reason="lease was never admitted on this node",
            )
        if (
            entry.lease_sha256 != lease_sha256
            or entry.lease.fencing_token != fencing_token
        ):
            return self._execution_rejection(
                NodeAgentStatus.STALE_LEASE,
                entry,
                reason="execution context does not match the admitted lease revision",
            )
        if entry.state != LifecycleState.ADMITTED:
            return self._execution_rejection(
                NodeAgentStatus.DUPLICATE_TRANSITION,
                entry,
                reason="workload already left the admitted state",
            )
        skew_status = self._lease_window_status(entry.lease, now)
        if skew_status is not None:
            return self._execution_rejection(
                skew_status,
                entry,
                reason="lease validity window failed at execution time",
            )
        if isinstance(bundle, (bytes, bytearray, memoryview)):
            data = bytes(bundle)
        else:
            return NodeExecutionResult(
                NodeAgentStatus.REJECTED,
                False,
                reason="workload bundle must be opaque bytes",
            )
        if (
            len(data) != entry.bundle_size_bytes
            or hashlib.sha256(data).hexdigest() != entry.bundle_sha256
        ):
            return self._fail_workload(
                entry,
                reason="bundle bytes do not match the signed digest and size",
            )
        return self._complete_workload(entry, data, now)

    def _unavailable_reason(self) -> str | None:
        if self._config_error is not None:
            return self._config_error
        if self.verifier is None:
            return "verifier service is not configured"
        if self.signer is None:
            return "signer service is not configured"
        if self.clock is None:
            return "clock service is not configured"
        if self._inventory is None:
            return "signed inventory is not configured"
        try:
            signer_key_id = self.signer.key_id
        except Exception:
            return "signer service failed"
        if signer_key_id != self._inventory.signature.key_id:
            return "signer key does not match the signed node inventory"
        return None

    def _verify_document(
        self,
        document: BaseModel,
        *,
        expected_account_id: str,
        expected_node_id: str | None = None,
    ) -> VerificationResult:
        if self.verifier is None:
            return VerificationResult(NodeAgentStatus.UNAVAILABLE)
        try:
            result = self.verifier.verify_document(
                document,
                expected_account_id=expected_account_id,
                expected_node_id=expected_node_id,
            )
        except Exception:
            return VerificationResult(NodeAgentStatus.UNAVAILABLE)
        if not isinstance(result, VerificationResult):
            return VerificationResult(NodeAgentStatus.UNAVAILABLE)
        if result.verified and (
            result.digest is None
            or not re.fullmatch(r"[0-9a-f]{64}", result.digest)
        ):
            return VerificationResult(NodeAgentStatus.UNAVAILABLE)
        if result.verified and result.digest != document_sha256(document):
            return VerificationResult(NodeAgentStatus.DIGEST_MISMATCH)
        return result

    def _verify_admission_chain(
        self,
        lease: LeaseDocument,
        request: ChalRequest,
        request_sha256: str,
        capability: CapabilityDocument,
        inventory: ResourceInventory,
        authenticated_subject_id: str,
        now: datetime,
    ) -> tuple[NodeAgentStatus | None, str | None, str | None]:
        assert self.verifier is not None
        capability_verified = self._verify_document(
            capability,
            expected_account_id=self.account_id,
        )
        if not capability_verified.verified:
            return capability_verified.status, "capability verification failed", None
        lease_verified = self._verify_document(
            lease,
            expected_account_id=self.account_id,
        )
        if not lease_verified.verified:
            return lease_verified.status, "lease verification failed", None
        inventory_verified = self._verify_document(
            inventory,
            expected_account_id=self.account_id,
            expected_node_id=self.node_id,
        )
        if not inventory_verified.verified:
            return inventory_verified.status, "inventory verification failed", None
        if not isinstance(inventory_verified.key, KeyRecord):
            return (
                NodeAgentStatus.UNAVAILABLE,
                "inventory verifier omitted enrolled key metadata",
                None,
            )
        fingerprint = hashlib.sha256(
            inventory_verified.key.public_key_bytes()
        ).hexdigest()
        if fingerprint != inventory.public_key_fingerprint:
            return (
                NodeAgentStatus.DIGEST_MISMATCH,
                "inventory fingerprint does not match the enrolled key",
                None,
            )

        if (
            request.account_id != self.account_id
            or capability.account_id != self.account_id
            or lease.account_id != self.account_id
            or inventory.account_id != self.account_id
        ):
            return NodeAgentStatus.ACCOUNT_MISMATCH, "account join failed", None
        if lease.node_id != self.node_id or inventory.node_id != self.node_id:
            return NodeAgentStatus.NODE_MISMATCH, "node join failed", None
        if inventory.health != NodeHealth.READY:
            return (
                NodeAgentStatus.WORKLOAD_REJECTED,
                "configured inventory is not ready for new execution",
                None,
            )
        if lease.request_id != request.request_id:
            return NodeAgentStatus.DIGEST_MISMATCH, "lease request_id join failed", None
        if lease.request_sha256 != request_sha256:
            return (
                NodeAgentStatus.DIGEST_MISMATCH,
                "lease does not bind the verified request digest",
                None,
            )
        if (
            request.capability_id != capability.capability_id
            or lease.capability_id != capability.capability_id
        ):
            return (
                NodeAgentStatus.CAPABILITY_MISMATCH,
                "capability identifier join failed",
                None,
            )
        if authenticated_subject_id != capability.subject_id:
            return (
                NodeAgentStatus.SUBJECT_MISMATCH,
                "authenticated subject does not match the capability subject",
                None,
            )
        if self.node_id not in capability.audience_node_ids:
            return (
                NodeAgentStatus.AUDIENCE_MISMATCH,
                "this node is outside the capability audience",
                None,
            )
        required_actions = {CapabilityAction.RESERVE, CapabilityAction.EXECUTE}
        if not required_actions.issubset(set(capability.actions)):
            return (
                NodeAgentStatus.WORKLOAD_REJECTED,
                "capability must grant reserve and execute actions",
                None,
            )
        if (
            request.workload_kind not in capability.constraints.workload_kinds
            or request.workload_kind not in inventory.workload_kinds
        ):
            return (
                NodeAgentStatus.WORKLOAD_REJECTED,
                "workload kind is outside capability or inventory support",
                None,
            )
        if not any(
            device_uri_matches_prefix(request.device_uri, prefix)
            for prefix in capability.constraints.resource_prefixes
        ):
            return (
                NodeAgentStatus.WORKLOAD_REJECTED,
                "request device is outside capability resource prefixes",
                None,
            )
        if (
            lease.inventory_id != inventory.inventory_id
            or lease.inventory_sha256 != inventory_verified.digest
        ):
            return (
                NodeAgentStatus.DIGEST_MISMATCH,
                "lease does not bind the configured signed inventory",
                None,
            )
        if (
            lease.transport not in inventory.transports
            or lease.transport not in capability.constraints.transports
        ):
            return (
                NodeAgentStatus.TRANSPORT_UNSUPPORTED,
                "lease transport is outside signed inventory or capability",
                None,
            )
        if _ATTESTATION_RANK[inventory.attestation] < _ATTESTATION_RANK[
            capability.constraints.minimum_attestation
        ]:
            return (
                NodeAgentStatus.WORKLOAD_REJECTED,
                "inventory attestation is below the capability minimum",
                None,
            )
        if not resource_vector_within(
            request.constraints.resources,
            capability.constraints.resources,
        ):
            return (
                NodeAgentStatus.WORKLOAD_REJECTED,
                "request resources exceed capability limits",
                None,
            )
        if not resource_vector_within(lease.resources, request.constraints.resources):
            return (
                NodeAgentStatus.WORKLOAD_REJECTED,
                "lease resources exceed the signed request",
                None,
            )
        for resource_field in _HOST_RESOURCE_FIELDS:
            if getattr(lease.resources, resource_field) > getattr(
                inventory.resources.allocatable,
                resource_field,
            ):
                return (
                    NodeAgentStatus.WORKLOAD_REJECTED,
                    f"lease {resource_field} exceeds signed allocatable inventory",
                    None,
                )
        gpu_memory = 0
        for gpu_id in lease.gpu_ids:
            gpu = inventory.resources.gpus.get(gpu_id)
            if gpu is None:
                return (
                    NodeAgentStatus.WORKLOAD_REJECTED,
                    "lease references a GPU absent from signed inventory",
                    None,
                )
            gpu_memory += gpu.allocatable_memory_bytes
        if gpu_memory < lease.resources.gpu_memory_bytes:
            return (
                NodeAgentStatus.WORKLOAD_REJECTED,
                "lease GPU memory exceeds selected signed GPU inventory",
                None,
            )

        if lease.state == LeaseState.REVOKED:
            return NodeAgentStatus.LEASE_REVOKED, "lease is revoked", None
        if lease.state == LeaseState.EXPIRED:
            return NodeAgentStatus.LEASE_EXPIRED, "lease is marked expired", None
        if lease.state != LeaseState.ACTIVE:
            return (
                NodeAgentStatus.LEASE_NOT_ACTIVE,
                f"lease state {lease.state.value} is not executable",
                None,
            )
        window_status = self._lease_window_status(lease, now)
        if window_status is not None:
            return window_status, "lease validity window failed", None

        if request.workload_manifest.size_bytes > self.max_bundle_bytes:
            return (
                NodeAgentStatus.REJECTED,
                "workload bundle exceeds the configured size bound",
                None,
            )
        return None, None, lease_verified.digest

    def _lease_window_status(
        self,
        lease: LeaseDocument,
        now: datetime,
    ) -> NodeAgentStatus | None:
        if now + self.max_clock_skew < lease.not_before:
            return NodeAgentStatus.CLOCK_SKEW
        if now >= lease.not_before + timedelta(seconds=lease.ttl_seconds):
            return NodeAgentStatus.LEASE_EXPIRED
        return None

    def _admit_renewal(
        self,
        existing: _AdmittedWorkload,
        lease: LeaseDocument,
        lease_sha256: str,
        request: ChalRequest,
        request_sha256: str,
    ) -> NodeAdmissionResult:
        if existing.state != LifecycleState.ADMITTED:
            return self._admission_rejection(
                NodeAgentStatus.DUPLICATE_TRANSITION,
                request,
                request_sha256,
                lease,
                "workload already left the admitted state",
            )
        if lease_sha256 == existing.lease_sha256:
            return self._admission_rejection(
                NodeAgentStatus.REPLAY,
                request,
                request_sha256,
                lease,
                "exact lease revision was already admitted",
            )
        if (
            lease.fencing_token <= existing.lease.fencing_token
            or lease.renewal_sequence <= existing.lease.renewal_sequence
        ):
            return self._admission_rejection(
                NodeAgentStatus.STALE_LEASE,
                request,
                request_sha256,
                lease,
                "fencing token and renewal sequence must strictly increase",
            )
        if request_sha256 != existing.request_sha256:
            return self._admission_rejection(
                NodeAgentStatus.DIGEST_MISMATCH,
                request,
                request_sha256,
                lease,
                "renewal binds a different request digest",
            )
        existing.lease = lease
        existing.lease_sha256 = lease_sha256
        return NodeAdmissionResult(
            NodeAgentStatus.RENEWED,
            True,
            lease_id=lease.lease_id,
            lease_sha256=lease_sha256,
            request_sha256=request_sha256,
            workload_id=existing.workload_id,
        )

    def _admission_rejection(
        self,
        status: NodeAgentStatus,
        request: ChalRequest,
        request_sha256: str,
        lease: LeaseDocument,
        reason: str | None,
    ) -> NodeAdmissionResult:
        error = self._signed_error_frame(
            status,
            request_id=request.request_id,
            request_sha256=request_sha256,
            trace_id=request.trace_id,
            device_uri=request.device_uri,
        )
        return NodeAdmissionResult(
            status,
            False,
            lease_id=lease.lease_id,
            request_sha256=request_sha256,
            error=error,
            reason=reason,
        )

    def _execution_rejection(
        self,
        status: NodeAgentStatus,
        entry: _AdmittedWorkload,
        *,
        reason: str,
    ) -> NodeExecutionResult:
        error = self._signed_error_frame(
            status,
            request_id=entry.request.request_id,
            request_sha256=entry.request_sha256,
            trace_id=entry.request.trace_id,
            device_uri=entry.request.device_uri,
        )
        return NodeExecutionResult(status, False, error=error, reason=reason)

    def _fail_workload(
        self,
        entry: _AdmittedWorkload,
        *,
        reason: str,
    ) -> NodeExecutionResult:
        error = self._signed_error_frame(
            NodeAgentStatus.BUNDLE_MISMATCH,
            request_id=entry.request.request_id,
            request_sha256=entry.request_sha256,
            trace_id=entry.request.trace_id,
            device_uri=entry.request.device_uri,
        )
        if error is None:
            return NodeExecutionResult(
                NodeAgentStatus.BUNDLE_MISMATCH,
                False,
                reason=reason,
            )
        # A mismatched bundle is rejected before execution and must not consume
        # the admitted lease.  The caller may retry with the exact signed bytes.
        return NodeExecutionResult(
            NodeAgentStatus.BUNDLE_MISMATCH,
            False,
            error=error,
            reason=reason,
        )

    def _complete_workload(
        self,
        entry: _AdmittedWorkload,
        data: bytes,
        now: datetime,
    ) -> NodeExecutionResult:
        if self.workload_executor is not None:
            return self._complete_with_executor(entry, data, now)
        bundle_sha256 = hashlib.sha256(data).hexdigest()
        report_payload = {
            "schema": HASH_REPORT_SCHEMA,
            "account_id": entry.lease.account_id,
            "node_id": entry.lease.node_id,
            "workload_id": entry.workload_id,
            "request_id": entry.request.request_id,
            "request_sha256": entry.request_sha256,
            "trace_id": entry.request.trace_id,
            "lease_id": entry.lease.lease_id,
            "lease_sha256": entry.lease_sha256,
            "fencing_token": entry.lease.fencing_token,
            "algorithm": "sha256",
            "bundle_sha256": bundle_sha256,
            "bundle_size_bytes": len(data),
        }
        report_bytes = rfc8785.dumps(report_payload)
        report_sha256 = hashlib.sha256(report_bytes).hexdigest()
        output = {
            "uri": f"artifact://private-mesh/hash-report/{report_sha256}",
            "sha256": report_sha256,
            "size_bytes": len(report_bytes),
            "media_type": HASH_REPORT_MEDIA_TYPE,
            "classification": "private",
        }
        try:
            staged = self._signed_lifecycle_event(
                entry,
                sequence=entry.sequence + 1,
                previous_state=LifecycleState.ADMITTED,
                state=LifecycleState.STAGED,
                occurred_at=now,
            )
            running = self._signed_lifecycle_event(
                entry,
                sequence=entry.sequence + 2,
                previous_state=LifecycleState.STAGED,
                state=LifecycleState.RUNNING,
                occurred_at=now,
            )
            completed = self._signed_lifecycle_event(
                entry,
                sequence=entry.sequence + 3,
                previous_state=LifecycleState.RUNNING,
                state=LifecycleState.COMPLETED,
                occurred_at=now,
                outputs=(output,),
            )
            response = self._signed_response(
                entry,
                status=ResponseStatus.SUCCEEDED,
                completed_at=now,
                outputs=(output,),
                error=None,
            )
        except Exception:
            return NodeExecutionResult(
                NodeAgentStatus.UNAVAILABLE,
                False,
                reason="result signing failed",
            )
        entry.sequence += 3
        entry.state = LifecycleState.COMPLETED
        return NodeExecutionResult(
            NodeAgentStatus.EXECUTED,
            True,
            response=response,
            lifecycle_events=(staged, running, completed),
            report=report_bytes,
        )

    def _complete_with_executor(
        self,
        entry: _AdmittedWorkload,
        data: bytes,
        now: datetime,
    ) -> NodeExecutionResult:
        assert self.workload_executor is not None
        try:
            outcome = self.workload_executor.execute_workload(
                lease=entry.lease,
                request=entry.request,
                bundle=data,
            )
        except Exception:
            outcome = None
        if type(outcome) is not WorkloadExecutionOutcome:
            return NodeExecutionResult(
                NodeAgentStatus.UNAVAILABLE,
                False,
                reason="workload executor failed",
            )
        if not outcome.ok:
            if outcome.unavailable:
                # The executor could not run at all; nothing was consumed, so
                # the admitted lease remains retryable.  A retry after partial
                # consumption is rejected by the execution authority and then
                # terminalizes below.
                return NodeExecutionResult(
                    NodeAgentStatus.UNAVAILABLE,
                    False,
                    reason=outcome.reason or "workload executor unavailable",
                )
            return self._fail_workload_terminal(
                entry,
                now,
                reason=outcome.reason or "workload execution failed",
            )
        outputs: list[Mapping[str, Any]] = []
        for candidate in outcome.outputs:
            if not isinstance(candidate, Mapping):
                return self._fail_workload_terminal(
                    entry, now, reason="executor returned an invalid output reference"
                )
            parsed, parse_error = _strict_parse(ContentReference, dict(candidate))
            if parse_error is not None or parsed is None:
                return self._fail_workload_terminal(
                    entry, now, reason="executor returned an invalid output reference"
                )
            outputs.append(parsed.model_dump(mode="json"))
        if not outputs:
            return self._fail_workload_terminal(
                entry, now, reason="executor returned no output references"
            )
        report = outcome.report
        if report is not None and (
            not isinstance(report, (bytes, bytearray, memoryview))
            or len(bytes(report)) > self.max_bundle_bytes
        ):
            return self._fail_workload_terminal(
                entry, now, reason="executor returned an invalid evidence report"
            )
        try:
            staged = self._signed_lifecycle_event(
                entry,
                sequence=entry.sequence + 1,
                previous_state=LifecycleState.ADMITTED,
                state=LifecycleState.STAGED,
                occurred_at=now,
            )
            running = self._signed_lifecycle_event(
                entry,
                sequence=entry.sequence + 2,
                previous_state=LifecycleState.STAGED,
                state=LifecycleState.RUNNING,
                occurred_at=now,
            )
            completed = self._signed_lifecycle_event(
                entry,
                sequence=entry.sequence + 3,
                previous_state=LifecycleState.RUNNING,
                state=LifecycleState.COMPLETED,
                occurred_at=now,
                outputs=tuple(outputs),
            )
            response = self._signed_response(
                entry,
                status=ResponseStatus.SUCCEEDED,
                completed_at=now,
                outputs=tuple(outputs),
                error=None,
            )
        except Exception:
            return NodeExecutionResult(
                NodeAgentStatus.UNAVAILABLE,
                False,
                reason="result signing failed",
            )
        entry.sequence += 3
        entry.state = LifecycleState.COMPLETED
        return NodeExecutionResult(
            NodeAgentStatus.EXECUTED,
            True,
            response=response,
            lifecycle_events=(staged, running, completed),
            report=bytes(report) if report is not None else None,
        )

    def _fail_workload_terminal(
        self,
        entry: _AdmittedWorkload,
        now: datetime,
        *,
        reason: str,
    ) -> NodeExecutionResult:
        error = self._signed_error_frame(
            NodeAgentStatus.EXECUTION_FAILED,
            request_id=entry.request.request_id,
            request_sha256=entry.request_sha256,
            trace_id=entry.request.trace_id,
            device_uri=entry.request.device_uri,
        )
        if error is None:
            # A signed FAILED transition requires an error frame; without one
            # nothing durable can be recorded, so fail closed without claiming
            # a state change.
            return NodeExecutionResult(
                NodeAgentStatus.UNAVAILABLE,
                False,
                reason="failure signing unavailable",
            )
        try:
            failed = self._signed_lifecycle_event(
                entry,
                sequence=entry.sequence + 1,
                previous_state=LifecycleState.ADMITTED,
                state=LifecycleState.FAILED,
                occurred_at=now,
                error=error,
            )
            response = self._signed_response(
                entry,
                status=ResponseStatus.FAILED,
                completed_at=now,
                outputs=(),
                error=error,
            )
        except Exception:
            return NodeExecutionResult(
                NodeAgentStatus.UNAVAILABLE,
                False,
                reason="result signing failed",
            )
        entry.sequence += 1
        entry.state = LifecycleState.FAILED
        return NodeExecutionResult(
            NodeAgentStatus.EXECUTION_FAILED,
            False,
            response=response,
            lifecycle_events=(failed,),
            error=error,
            reason=reason,
        )

    def cancel(
        self,
        *,
        lease_id: str,
        lease_sha256: str,
        fencing_token: int,
    ) -> NodeExecutionResult:
        """Cancel one admitted workload before execution with a signed event."""

        with self._lock:
            if not isinstance(lease_id, str) or not _IDENTIFIER_RE.fullmatch(lease_id):
                return NodeExecutionResult(
                    NodeAgentStatus.REJECTED,
                    False,
                    reason="lease_id must be a canonical identifier",
                )
            if not isinstance(lease_sha256, str) or not re.fullmatch(
                r"[0-9a-f]{64}", lease_sha256
            ):
                return NodeExecutionResult(
                    NodeAgentStatus.REJECTED,
                    False,
                    reason="lease_sha256 must be a canonical SHA-256 digest",
                )
            if isinstance(fencing_token, bool) or not isinstance(fencing_token, int):
                return NodeExecutionResult(
                    NodeAgentStatus.REJECTED,
                    False,
                    reason="fencing_token must be an integer",
                )
            unavailable = self._unavailable_reason()
            if unavailable is not None:
                return NodeExecutionResult(
                    NodeAgentStatus.UNAVAILABLE,
                    False,
                    reason=unavailable,
                )
            assert self.clock is not None
            now = _normalized_now(self.clock)
            if now is None:
                return NodeExecutionResult(
                    NodeAgentStatus.UNAVAILABLE,
                    False,
                    reason="clock service failed",
                )
            entry = self._workloads.get(lease_id)
            if entry is None:
                return NodeExecutionResult(
                    NodeAgentStatus.REJECTED,
                    False,
                    reason="lease was never admitted on this node",
                )
            if (
                entry.lease_sha256 != lease_sha256
                or entry.lease.fencing_token != fencing_token
            ):
                return self._execution_rejection(
                    NodeAgentStatus.STALE_LEASE,
                    entry,
                    reason="cancel context does not match the admitted lease revision",
                )
            if entry.state != LifecycleState.ADMITTED:
                return self._execution_rejection(
                    NodeAgentStatus.DUPLICATE_TRANSITION,
                    entry,
                    reason="workload already left the admitted state",
                )
            try:
                cancelled = self._signed_lifecycle_event(
                    entry,
                    sequence=entry.sequence + 1,
                    previous_state=LifecycleState.ADMITTED,
                    state=LifecycleState.CANCELLED,
                    occurred_at=now,
                )
            except Exception:
                return NodeExecutionResult(
                    NodeAgentStatus.UNAVAILABLE,
                    False,
                    reason="result signing failed",
                )
            entry.sequence += 1
            entry.state = LifecycleState.CANCELLED
            return NodeExecutionResult(
                NodeAgentStatus.CANCELLED,
                True,
                lifecycle_events=(cancelled,),
            )

    def _signed_lifecycle_event(
        self,
        entry: _AdmittedWorkload,
        *,
        sequence: int,
        previous_state: LifecycleState | None,
        state: LifecycleState,
        occurred_at: datetime,
        outputs: tuple[Mapping[str, Any], ...] = (),
        error: ErrorFrame | None = None,
    ) -> LifecycleEvent:
        assert self.signer is not None
        payload = {
            "schema": "planetary.vsource.lifecycle.v1",
            "event_id": f"event:{entry.lease_sha256[:20]}:{sequence:04d}",
            "sequence": sequence,
            "workload_id": entry.workload_id,
            "request_id": entry.request.request_id,
            "request_sha256": entry.request_sha256,
            "trace_id": entry.request.trace_id,
            "placement_id": entry.lease.placement_id,
            "lease_id": entry.lease.lease_id,
            "lease_sha256": entry.lease_sha256,
            "fencing_token": entry.lease.fencing_token,
            "node_id": entry.lease.node_id,
            "inventory_id": entry.lease.inventory_id,
            "inventory_sha256": entry.lease.inventory_sha256,
            "account_id": entry.lease.account_id,
            "previous_state": previous_state.value if previous_state else None,
            "state": state.value,
            "occurred_at": _wire_time(occurred_at),
            "checkpoint": None,
            "outputs": [dict(output) for output in outputs],
            "error": (
                error.model_dump(mode="json", by_alias=True)
                if error is not None
                else None
            ),
        }
        event = sign_contract_document(LifecycleEvent, payload, self.signer)
        validate_lease_bound_lifecycle(event, entry.lease)
        verified = self._verify_document(
            event,
            expected_account_id=self.account_id,
            expected_node_id=self.node_id,
        )
        if not verified.verified:
            raise RuntimeError("node lifecycle signature did not self-verify")
        return event

    def _signed_response(
        self,
        entry: _AdmittedWorkload,
        *,
        status: ResponseStatus,
        completed_at: datetime,
        outputs: tuple[Mapping[str, Any], ...],
        error: ErrorFrame | None,
    ) -> ChalResponse:
        assert self.signer is not None
        payload = {
            "schema": "planetary.chal.response.v1",
            "response_id": f"response:{entry.lease_sha256[:24]}",
            "request_id": entry.request.request_id,
            "request_sha256": entry.request_sha256,
            "trace_id": entry.request.trace_id,
            "account_id": entry.lease.account_id,
            "node_id": entry.lease.node_id,
            "device_uri": entry.request.device_uri,
            "lease_id": entry.lease.lease_id,
            "lease_sha256": entry.lease_sha256,
            "fencing_token": entry.lease.fencing_token,
            "status": status.value,
            "completed_at": _wire_time(completed_at),
            "outputs": [dict(output) for output in outputs],
            "telemetry_ids": [],
            "error": (
                error.model_dump(mode="json", by_alias=True)
                if error is not None
                else None
            ),
        }
        response = sign_contract_document(ChalResponse, payload, self.signer)
        validate_lease_bound_response(response, entry.lease)
        verified = self._verify_document(
            response,
            expected_account_id=self.account_id,
            expected_node_id=self.node_id,
        )
        if not verified.verified:
            raise RuntimeError("node response signature did not self-verify")
        return response

    def _signed_error_frame(
        self,
        status: NodeAgentStatus,
        *,
        request_id: str,
        request_sha256: str,
        trace_id: str,
        device_uri: str | None,
    ) -> ErrorFrame | None:
        if self.signer is None or self._error_frames_emitted >= self.max_error_frames:
            return None
        code = _FRAME_ERROR_CODES.get(status, ErrorCode.WORKLOAD_REJECTED)
        payload = {
            "schema": "planetary.chal.error.v1",
            "error_id": (
                f"error:{request_sha256[:16]}:{self._error_frames_emitted:04d}"
            ),
            "request_id": request_id,
            "request_sha256": request_sha256,
            "trace_id": trace_id,
            "code": code.value,
            "retryable": False,
            "diagnostic_id": None,
            "retry_after_ms": None,
            "device_uri": device_uri,
        }
        try:
            frame = sign_contract_document(ErrorFrame, payload, self.signer)
        except Exception:
            return None
        verified = self._verify_document(
            frame,
            expected_account_id=self.account_id,
            expected_node_id=self.node_id,
        )
        if not verified.verified:
            return None
        self._error_frames_emitted += 1
        return frame


__all__ = [
    "Clock",
    "DocumentSigner",
    "DocumentVerifier",
    "Ed25519DocumentVerifier",
    "HASH_REPORT_MEDIA_TYPE",
    "HASH_REPORT_SCHEMA",
    "KeyResolver",
    "NodeAdmissionResult",
    "NodeAgent",
    "NodeAgentStatus",
    "NodeExecutionResult",
    "VerificationResult",
]
