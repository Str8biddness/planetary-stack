"""Durable local-only vSource control plane.

This module implements the first canonical Python service API for vSource
inventory admission, deterministic placement, fenced leases, and lifecycle
binding. It deliberately exposes no network listener.
"""

from __future__ import annotations

import base64
import json
import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, TypeVar

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pydantic import BaseModel, ValidationError

from contracts.chal_vsource.v1.canonical import document_sha256, signing_bytes
from contracts.chal_vsource.v1.models import (
    AttestationLevel,
    CapabilityDocument,
    ChalRequest,
    ChalResponse,
    ErrorCode,
    ErrorFrame,
    LeaseDocument,
    LeaseRevocationReason,
    LeaseState,
    LifecycleEvent,
    LifecycleState,
    MAX_SAFE_INTEGER,
    NodeHealth,
    PlacementCandidate,
    PlacementDecision,
    PlacementResult,
    ResourceInventory,
    ResourceVector,
    Signature,
    TransportKind,
    WorkloadKind,
    device_uri_matches_prefix,
    resource_vector_within,
    validate_lease_bound_lifecycle,
    validate_lease_bound_response,
    validate_private_cell_allocation,
)


ModelT = TypeVar("ModelT", bound=BaseModel)
_ZERO_SIGNATURE = base64.urlsafe_b64encode(b"\x00" * 64).rstrip(b"=").decode(
    "ascii"
)
_SQLITE_BUSY_TIMEOUT_MS = 5_000
_TERMINAL_LIFECYCLE_STATES = {
    LifecycleState.COMPLETED,
    LifecycleState.FAILED,
    LifecycleState.CANCELLED,
    LifecycleState.LOST,
}
_ATTESTATION_RANK = {
    AttestationLevel.UNVERIFIED: 0,
    AttestationLevel.SOFTWARE_VERIFIED: 1,
    AttestationLevel.HARDWARE_VERIFIED: 2,
}


class VSourceStatus(StrEnum):
    ACCEPTED = "accepted"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    MALFORMED_DOCUMENT = "malformed_document"
    UNKNOWN_KEY = "unknown_key"
    KEY_REVOKED = "key_revoked"
    INVALID_SIGNATURE = "invalid_signature"
    ACCOUNT_MISMATCH = "account_mismatch"
    AUDIENCE_MISMATCH = "audience_mismatch"
    DOCUMENT_EXPIRED = "document_expired"
    CLOCK_SKEW = "clock_skew"
    DIGEST_MISMATCH = "digest_mismatch"
    IDEMPOTENCY_COLLISION = "idempotency_collision"
    NO_PLACEMENT = "no_placement"
    LEASE_EXPIRED = "lease_expired"
    STALE_LEASE = "stale_lease"
    TERMINAL_LEASE = "terminal_lease"
    LEASE_CONFLICT = "lease_conflict"
    REPLAY = "replay"


@dataclass(frozen=True)
class AdmissionResult:
    status: VSourceStatus
    accepted: bool
    digest: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AllocationResult:
    status: VSourceStatus
    accepted: bool
    request_sha256: str | None = None
    placement: PlacementDecision | None = None
    lease: LeaseDocument | None = None
    reason: str | None = None


@dataclass(frozen=True)
class LeaseResult:
    status: VSourceStatus
    accepted: bool
    lease: LeaseDocument | None = None
    reason: str | None = None


@dataclass(frozen=True)
class KeyRecord:
    key_id: str
    public_key: Ed25519PublicKey | bytes
    account_id: str
    audiences: tuple[str, ...]
    subject_id: str | None = None
    node_id: str | None = None
    revoked: bool = False
    not_before: datetime | None = None
    not_after: datetime | None = None
    minimum_capability_revocation_epoch: int = 0

    def ed25519_public_key(self) -> Ed25519PublicKey:
        if isinstance(self.public_key, Ed25519PublicKey):
            return self.public_key
        return Ed25519PublicKey.from_public_bytes(self.public_key)

    def public_key_bytes(self) -> bytes:
        return self.ed25519_public_key().public_bytes(
            encoding=Encoding.Raw,
            format=PublicFormat.Raw,
        )


class KeyResolver(Protocol):
    def resolve_key(self, key_id: str) -> KeyRecord | None:
        """Return key metadata, or None when the key is unknown."""


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current UTC-aware time."""


class DocumentSigner(Protocol):
    @property
    def key_id(self) -> str:
        """Key identifier to place in the contract signature field."""

    def sign(self, payload: bytes) -> bytes:
        """Return an Ed25519 signature for already canonicalized bytes."""


@dataclass(frozen=True)
class Ed25519DocumentSigner:
    key_id: str
    private_key: Ed25519PrivateKey

    def sign(self, payload: bytes) -> bytes:
        return self.private_key.sign(payload)


@dataclass(frozen=True)
class _VerifiedDocument:
    document: BaseModel
    digest: str
    key: KeyRecord


@dataclass(frozen=True)
class _CandidateEvaluation:
    candidate: PlacementCandidate
    transport: TransportKind | None
    gpu_ids: list[str]


@dataclass(frozen=True)
class _Reservation:
    cpu_millicores: int = 0
    memory_bytes: int = 0
    storage_bytes: int = 0
    ingress_bps: int = 0
    egress_bps: int = 0
    gpu_ids: frozenset[str] = frozenset()


def _json_dumps(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, allow_nan=False, separators=(",", ":"))


def _wire_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_wire_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _public_key_fingerprint(key: KeyRecord) -> str:
    import hashlib

    return hashlib.sha256(key.public_key_bytes()).hexdigest()


def _b64url_signature(signature: bytes) -> str:
    return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


def _signature_payload(key_id: str, value: str) -> dict[str, str]:
    return {"algorithm": "ed25519", "key_id": key_id, "value": value}


def _model_from_wire(model_type: type[ModelT], payload: Mapping[str, Any]) -> ModelT:
    return model_type.model_validate_json(_json_dumps(payload))


def sign_contract_document(
    model_type: type[ModelT],
    payload: Mapping[str, Any],
    signer: DocumentSigner,
) -> ModelT:
    """Materialize a frozen contract model and sign its canonical bytes."""

    unsigned = dict(payload)
    unsigned["signature"] = _signature_payload(signer.key_id, _ZERO_SIGNATURE)
    placeholder = _model_from_wire(model_type, unsigned)
    signed = dict(unsigned)
    signed["signature"] = _signature_payload(
        signer.key_id,
        _b64url_signature(signer.sign(signing_bytes(placeholder))),
    )
    return _model_from_wire(model_type, signed)


class LocalVSourceControlPlane:
    """SQLite-backed local vSource scheduler and lease registry."""

    def __init__(
        self,
        db_path: Path | str | None,
        *,
        key_resolver: KeyResolver | None,
        signer: DocumentSigner | None,
        clock: Clock | None,
        scheduler_id: str = "scheduler:local:001",
        scheduler_audience: str | None = None,
        policy_version: str = "private-cell-v1",
        max_clock_skew_seconds: int = 60,
        default_lease_ttl_seconds: int = 120,
        default_renewals_remaining: int = 16,
    ) -> None:
        self.db_path = Path(db_path) if db_path is not None else None
        self.key_resolver = key_resolver
        self.signer = signer
        self.clock = clock
        self.scheduler_id = scheduler_id
        self.scheduler_audience = scheduler_audience or scheduler_id
        self.policy_version = policy_version
        self.max_clock_skew = timedelta(seconds=max_clock_skew_seconds)
        self.default_lease_ttl_seconds = default_lease_ttl_seconds
        self.default_renewals_remaining = default_renewals_remaining
        self._state_error: str | None = None
        if self.db_path is None:
            self._state_error = "state service is not configured"
        else:
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self._initialize()
            except sqlite3.Error as exc:
                self._state_error = f"state service unavailable: {exc}"

    def register_inventory(
        self,
        inventory: ResourceInventory | Mapping[str, Any],
    ) -> AdmissionResult:
        ready = self._ready(require_signer=False)
        if ready is not None:
            return AdmissionResult(ready, False)
        parsed, error = self._coerce(ResourceInventory, inventory)
        if error is not None:
            return AdmissionResult(error, False)
        assert parsed is not None
        verified, error = self._verify_document(
            parsed,
            expected_account_id=parsed.account_id,
            expected_node_id=parsed.node_id,
        )
        if error is not None:
            return AdmissionResult(error, False)
        assert verified is not None
        if _public_key_fingerprint(verified.key) != parsed.public_key_fingerprint:
            return AdmissionResult(VSourceStatus.DIGEST_MISMATCH, False)
        now, error = self._now()
        if error is not None:
            return AdmissionResult(error, False)
        assert now is not None
        expires_at = parsed.observed_at + timedelta(seconds=parsed.ttl_seconds)
        digest = verified.digest
        try:
            with self._transaction() as conn:
                existing = conn.execute(
                    """
                    SELECT digest, observed_at, account_id, node_id
                    FROM inventories
                    WHERE inventory_id = ?
                    """,
                    (parsed.inventory_id,),
                ).fetchone()
                if existing is not None:
                    if existing["digest"] == digest:
                        return AdmissionResult(
                            VSourceStatus.IDEMPOTENT_REPLAY,
                            True,
                            digest,
                        )
                    if (
                        existing["account_id"] != parsed.account_id
                        or existing["node_id"] != parsed.node_id
                    ):
                        return AdmissionResult(VSourceStatus.REPLAY, False, digest)
                    existing_observed = _parse_wire_time(existing["observed_at"])
                    if parsed.observed_at <= existing_observed:
                        return AdmissionResult(VSourceStatus.REPLAY, False, digest)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO inventory_digests
                    (inventory_id, digest, document_json, admitted_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        parsed.inventory_id,
                        digest,
                        parsed.model_dump_json(by_alias=True),
                        _wire_time(now),
                    ),
                )
                inventory_values = (
                    digest,
                    parsed.model_dump_json(by_alias=True),
                    parsed.account_id,
                    parsed.node_id,
                    _wire_time(parsed.observed_at),
                    _wire_time(expires_at),
                    parsed.health.value,
                    _wire_time(now),
                )
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO inventories
                        (
                            inventory_id, digest, document_json, account_id, node_id,
                            observed_at, expires_at, health, admitted_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (parsed.inventory_id, *inventory_values),
                    )
                else:
                    cursor = conn.execute(
                        """
                        UPDATE inventories
                        SET
                            digest = ?,
                            document_json = ?,
                            account_id = ?,
                            node_id = ?,
                            observed_at = ?,
                            expires_at = ?,
                            health = ?,
                            admitted_at = ?
                        WHERE inventory_id = ?
                          AND account_id = ?
                          AND node_id = ?
                          AND observed_at = ?
                        """,
                        (
                            *inventory_values,
                            parsed.inventory_id,
                            parsed.account_id,
                            parsed.node_id,
                            existing["observed_at"],
                        ),
                    )
                    if cursor.rowcount != 1:
                        return AdmissionResult(VSourceStatus.REPLAY, False, digest)
            return AdmissionResult(VSourceStatus.ACCEPTED, True, digest)
        except sqlite3.Error as exc:
            return AdmissionResult(VSourceStatus.UNAVAILABLE, False, reason=str(exc))

    def allocate(
        self,
        request: ChalRequest | Mapping[str, Any],
        capability: CapabilityDocument | Mapping[str, Any],
        *,
        authenticated_subject_id: str,
        lease_ttl_seconds: int | None = None,
    ) -> AllocationResult:
        ready = self._ready(require_signer=True)
        if ready is not None:
            return AllocationResult(ready, False)
        parsed_request, error = self._coerce(ChalRequest, request)
        if error is not None:
            return AllocationResult(error, False)
        parsed_capability, error = self._coerce(CapabilityDocument, capability)
        if error is not None:
            return AllocationResult(error, False)
        assert parsed_request is not None
        assert parsed_capability is not None
        request_verified, error = self._verify_document(
            parsed_request,
            expected_account_id=parsed_request.account_id,
        )
        if error is not None:
            return AllocationResult(error, False)
        capability_verified, error = self._verify_document(
            parsed_capability,
            expected_account_id=parsed_capability.account_id,
        )
        if error is not None:
            return AllocationResult(error, False)
        assert request_verified is not None
        assert capability_verified is not None
        request_sha256 = request_verified.digest
        capability_sha256 = capability_verified.digest
        if (
            parsed_request.account_id != parsed_capability.account_id
            or parsed_request.capability_id != parsed_capability.capability_id
            or authenticated_subject_id != parsed_capability.subject_id
        ):
            return AllocationResult(VSourceStatus.REJECTED, False, request_sha256)
        now, error = self._now()
        if error is not None:
            return AllocationResult(error, False, request_sha256)
        assert now is not None
        ttl_seconds = lease_ttl_seconds or self.default_lease_ttl_seconds
        if ttl_seconds < 1 or ttl_seconds > 900:
            return AllocationResult(VSourceStatus.REJECTED, False, request_sha256)
        try:
            with self._transaction() as conn:
                self._expire_active_leases(conn, now)
                replay = self._handle_idempotency(
                    conn,
                    parsed_request,
                    request_sha256,
                    parsed_capability,
                    capability_sha256,
                    authenticated_subject_id,
                    now,
                )
                if replay is not None:
                    return replay
                capability_error = self._admit_capability(
                    conn,
                    parsed_capability,
                    capability_sha256,
                    now,
                )
                if capability_error is not None:
                    return AllocationResult(
                        capability_error,
                        False,
                        request_sha256,
                    )
                inventories = self._load_current_inventories(
                    conn,
                    parsed_request.account_id,
                    now,
                )
                if not inventories:
                    result = AllocationResult(
                        VSourceStatus.NO_PLACEMENT,
                        False,
                        request_sha256,
                        reason="no current inventory",
                    )
                    self._store_idempotency_result(
                        conn,
                        parsed_request,
                        request_sha256,
                        parsed_capability,
                        capability_sha256,
                        authenticated_subject_id,
                        result,
                        now,
                    )
                    return result
                evaluations = [
                    self._evaluate_candidate(
                        conn,
                        parsed_request,
                        parsed_capability,
                        inventory,
                        authenticated_subject_id,
                        now,
                    )
                    for inventory in inventories
                ]
                selected = next(
                    (evaluation for evaluation in evaluations if evaluation.candidate.eligible),
                    None,
                )
                placement_id = self._stable_id("placement", request_sha256)
                if selected is None:
                    placement = self._build_unplaced_decision(
                        parsed_request,
                        request_sha256,
                        evaluations,
                        now,
                        placement_id,
                    )
                    self._store_placement(conn, placement)
                    result = AllocationResult(
                        VSourceStatus.NO_PLACEMENT,
                        False,
                        request_sha256,
                        placement=placement,
                    )
                    self._store_idempotency_result(
                        conn,
                        parsed_request,
                        request_sha256,
                        parsed_capability,
                        capability_sha256,
                        authenticated_subject_id,
                        result,
                        now,
                    )
                    return result
                refreshed = self._refresh_selected_inventory(
                    conn,
                    parsed_request,
                    parsed_capability,
                    selected,
                    authenticated_subject_id,
                    now,
                )
                if refreshed is None:
                    return AllocationResult(
                        VSourceStatus.LEASE_CONFLICT,
                        False,
                        request_sha256,
                        reason="inventory changed before commit",
                    )
                inventory, selected = refreshed
                lease = self._build_lease(
                    parsed_request,
                    request_sha256,
                    inventory,
                    placement_id,
                    selected.transport,
                    selected.gpu_ids,
                    now,
                    ttl_seconds,
                )
                placement = self._build_placed_decision(
                    parsed_request,
                    request_sha256,
                    evaluations,
                    selected,
                    now,
                    placement_id,
                )
                validate_private_cell_allocation(
                    parsed_request,
                    parsed_capability,
                    inventory,
                    placement,
                    lease,
                    authenticated_subject_id=authenticated_subject_id,
                )
                self._store_placement(conn, placement)
                self._insert_lease(conn, lease, now)
                result = AllocationResult(
                    VSourceStatus.ACCEPTED,
                    True,
                    request_sha256,
                    placement=placement,
                    lease=lease,
                )
                self._store_idempotency_result(
                    conn,
                    parsed_request,
                    request_sha256,
                    parsed_capability,
                    capability_sha256,
                    authenticated_subject_id,
                    result,
                    now,
                )
                return result
        except (sqlite3.Error, ValidationError, ValueError) as exc:
            if isinstance(exc, sqlite3.Error):
                status = VSourceStatus.UNAVAILABLE
            else:
                status = VSourceStatus.REJECTED
            return AllocationResult(status, False, request_sha256, reason=str(exc))

    def renew_lease(
        self,
        lease_id: str,
        *,
        lease_sha256: str,
        fencing_token: int,
        renewal_sequence: int,
        ttl_seconds: int | None = None,
    ) -> LeaseResult:
        ready = self._ready(require_signer=True)
        if ready is not None:
            return LeaseResult(ready, False)
        now, error = self._now()
        if error is not None:
            return LeaseResult(error, False)
        assert now is not None
        requested_ttl = ttl_seconds or self.default_lease_ttl_seconds
        if requested_ttl < 1 or requested_ttl > 900:
            return LeaseResult(VSourceStatus.REJECTED, False)
        try:
            with self._transaction() as conn:
                self._expire_active_leases(conn, now)
                row = conn.execute(
                    "SELECT * FROM leases WHERE lease_id = ?",
                    (lease_id,),
                ).fetchone()
                if row is None:
                    return LeaseResult(VSourceStatus.REJECTED, False)
                if row["state"] == LeaseState.EXPIRED.value:
                    return LeaseResult(VSourceStatus.LEASE_EXPIRED, False)
                if row["terminal_state"] is not None:
                    return LeaseResult(VSourceStatus.TERMINAL_LEASE, False)
                if row["state"] != LeaseState.ACTIVE.value:
                    return LeaseResult(VSourceStatus.TERMINAL_LEASE, False)
                if (
                    row["document_sha256"] != lease_sha256
                    or row["fencing_token"] != fencing_token
                    or row["renewal_sequence"] != renewal_sequence
                ):
                    return LeaseResult(VSourceStatus.STALE_LEASE, False)
                current = LeaseDocument.model_validate_json(row["document_json"])
                if (
                    current.state != LeaseState.ACTIVE
                    or document_sha256(current) != row["document_sha256"]
                    or current.fencing_token != fencing_token
                    or current.renewal_sequence != renewal_sequence
                ):
                    return LeaseResult(VSourceStatus.STALE_LEASE, False)
                if (
                    current.renewals_remaining <= 0
                    or current.renewal_sequence >= 1024
                    or current.fencing_token >= MAX_SAFE_INTEGER
                ):
                    return LeaseResult(VSourceStatus.LEASE_CONFLICT, False)
                payload = current.model_dump(mode="json", by_alias=True)
                payload.update(
                    not_before=_wire_time(now),
                    ttl_seconds=requested_ttl,
                    fencing_token=current.fencing_token + 1,
                    renewal_sequence=current.renewal_sequence + 1,
                    renewals_remaining=current.renewals_remaining - 1,
                )
                payload.pop("signature", None)
                lease = sign_contract_document(LeaseDocument, payload, self.signer)  # type: ignore[arg-type]
                if (
                    lease.fencing_token <= current.fencing_token
                    or lease.renewal_sequence <= current.renewal_sequence
                ):
                    return LeaseResult(VSourceStatus.LEASE_CONFLICT, False)
                if (
                    self._update_lease_document(
                        conn,
                        lease,
                        now,
                        previous_sha256=lease_sha256,
                        previous_fencing_token=fencing_token,
                        previous_renewal_sequence=renewal_sequence,
                        terminal_state=None,
                    )
                    != 1
                ):
                    return LeaseResult(VSourceStatus.STALE_LEASE, False)
                return LeaseResult(VSourceStatus.ACCEPTED, True, lease)
        except (sqlite3.Error, ValidationError, ValueError) as exc:
            status = VSourceStatus.UNAVAILABLE if isinstance(exc, sqlite3.Error) else VSourceStatus.REJECTED
            return LeaseResult(status, False, reason=str(exc))

    def release_lease(
        self,
        lease_id: str,
        *,
        lease_sha256: str,
        fencing_token: int,
        renewal_sequence: int,
    ) -> LeaseResult:
        return self._terminal_lease_transition(
            lease_id,
            lease_sha256=lease_sha256,
            fencing_token=fencing_token,
            renewal_sequence=renewal_sequence,
            state=LeaseState.RELEASED,
            terminal_state=LeaseState.RELEASED.value,
        )

    def revoke_lease(
        self,
        lease_id: str,
        *,
        lease_sha256: str,
        fencing_token: int,
        renewal_sequence: int,
        revocation_reason: LeaseRevocationReason | str,
    ) -> LeaseResult:
        try:
            reason = (
                revocation_reason
                if isinstance(revocation_reason, LeaseRevocationReason)
                else LeaseRevocationReason(revocation_reason)
            )
        except ValueError:
            return LeaseResult(VSourceStatus.REJECTED, False)
        return self._terminal_lease_transition(
            lease_id,
            lease_sha256=lease_sha256,
            fencing_token=fencing_token,
            renewal_sequence=renewal_sequence,
            state=LeaseState.REVOKED,
            terminal_state=LeaseState.REVOKED.value,
            revocation_reason=reason,
        )

    def _terminal_lease_transition(
        self,
        lease_id: str,
        *,
        lease_sha256: str,
        fencing_token: int,
        renewal_sequence: int,
        state: LeaseState,
        terminal_state: str,
        revocation_reason: LeaseRevocationReason | None = None,
    ) -> LeaseResult:
        ready = self._ready(require_signer=True)
        if ready is not None:
            return LeaseResult(ready, False)
        now, error = self._now()
        if error is not None:
            return LeaseResult(error, False)
        assert now is not None
        try:
            with self._transaction() as conn:
                self._expire_active_leases(conn, now)
                row = conn.execute(
                    "SELECT * FROM leases WHERE lease_id = ?",
                    (lease_id,),
                ).fetchone()
                if row is None:
                    return LeaseResult(VSourceStatus.REJECTED, False)
                if row["state"] == LeaseState.EXPIRED.value:
                    return LeaseResult(VSourceStatus.LEASE_EXPIRED, False)
                if row["terminal_state"] is not None or row["state"] != LeaseState.ACTIVE.value:
                    return LeaseResult(VSourceStatus.TERMINAL_LEASE, False)
                if (
                    row["document_sha256"] != lease_sha256
                    or row["fencing_token"] != fencing_token
                    or row["renewal_sequence"] != renewal_sequence
                ):
                    return LeaseResult(VSourceStatus.STALE_LEASE, False)
                current = LeaseDocument.model_validate_json(row["document_json"])
                if (
                    current.state != LeaseState.ACTIVE
                    or document_sha256(current) != lease_sha256
                    or current.fencing_token != fencing_token
                    or current.renewal_sequence != renewal_sequence
                ):
                    return LeaseResult(VSourceStatus.STALE_LEASE, False)
                terminal = self._sign_lease_state(
                    current,
                    state,
                    revocation_reason=revocation_reason,
                )
                if (
                    self._update_lease_document(
                        conn,
                        terminal,
                        now,
                        previous_sha256=lease_sha256,
                        previous_fencing_token=fencing_token,
                        previous_renewal_sequence=renewal_sequence,
                        terminal_state=terminal_state,
                    )
                    != 1
                ):
                    return LeaseResult(VSourceStatus.STALE_LEASE, False)
                return LeaseResult(VSourceStatus.ACCEPTED, True, terminal)
        except (sqlite3.Error, ValidationError, ValueError) as exc:
            status = VSourceStatus.UNAVAILABLE if isinstance(exc, sqlite3.Error) else VSourceStatus.REJECTED
            return LeaseResult(status, False, reason=str(exc))

    def record_lifecycle_event(
        self,
        event: LifecycleEvent | Mapping[str, Any],
    ) -> AdmissionResult:
        ready = self._ready(require_signer=False)
        if ready is not None:
            return AdmissionResult(ready, False)
        parsed, error = self._coerce(LifecycleEvent, event)
        if error is not None:
            return AdmissionResult(error, False)
        assert parsed is not None
        verified, error = self._verify_document(
            parsed,
            expected_account_id=parsed.account_id,
            expected_node_id=parsed.node_id,
        )
        if error is not None:
            return AdmissionResult(error, False)
        assert verified is not None
        now, error = self._now()
        if error is not None:
            return AdmissionResult(error, False)
        assert now is not None
        try:
            with self._transaction() as conn:
                self._expire_active_leases(conn, now)
                lease_row = conn.execute(
                    "SELECT * FROM leases WHERE lease_id = ?",
                    (parsed.lease_id,),
                ).fetchone()
                if lease_row is None:
                    return AdmissionResult(VSourceStatus.REJECTED, False, verified.digest)
                if lease_row["state"] == LeaseState.EXPIRED.value:
                    return AdmissionResult(VSourceStatus.LEASE_EXPIRED, False, verified.digest)
                if lease_row["state"] != LeaseState.ACTIVE.value or lease_row["terminal_state"] is not None:
                    return AdmissionResult(VSourceStatus.TERMINAL_LEASE, False, verified.digest)
                lease = LeaseDocument.model_validate_json(lease_row["document_json"])
                if (
                    lease.state.value != lease_row["state"]
                    or document_sha256(lease) != lease_row["document_sha256"]
                ):
                    return AdmissionResult(VSourceStatus.STALE_LEASE, False, verified.digest)
                try:
                    validate_lease_bound_lifecycle(parsed, lease)
                except ValueError:
                    return AdmissionResult(VSourceStatus.STALE_LEASE, False, verified.digest)
                existing = conn.execute(
                    "SELECT digest FROM lifecycle_events WHERE event_id = ?",
                    (parsed.event_id,),
                ).fetchone()
                if existing is not None:
                    if existing["digest"] == verified.digest:
                        return AdmissionResult(
                            VSourceStatus.IDEMPOTENT_REPLAY,
                            True,
                            verified.digest,
                        )
                    return AdmissionResult(VSourceStatus.REPLAY, False, verified.digest)
                prior = conn.execute(
                    """
                    SELECT sequence, state
                    FROM lifecycle_events
                    WHERE lease_id = ?
                    ORDER BY sequence DESC
                    LIMIT 1
                    """,
                    (parsed.lease_id,),
                ).fetchone()
                if prior is None:
                    if parsed.sequence != 0 or parsed.previous_state is not None:
                        return AdmissionResult(VSourceStatus.REPLAY, False, verified.digest)
                else:
                    if (
                        parsed.sequence != prior["sequence"] + 1
                        or parsed.previous_state is None
                        or parsed.previous_state.value != prior["state"]
                    ):
                        return AdmissionResult(VSourceStatus.REPLAY, False, verified.digest)
                conn.execute(
                    """
                    INSERT INTO lifecycle_events
                    (event_id, digest, lease_id, workload_id, sequence, state, document_json, admitted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        parsed.event_id,
                        verified.digest,
                        parsed.lease_id,
                        parsed.workload_id,
                        parsed.sequence,
                        parsed.state.value,
                        parsed.model_dump_json(by_alias=True),
                        _wire_time(now),
                    ),
                )
                if parsed.state in _TERMINAL_LIFECYCLE_STATES:
                    released = self._sign_lease_state(lease, LeaseState.RELEASED)
                    updated = self._update_lease_document(
                        conn,
                        released,
                        now,
                        previous_sha256=lease_row["document_sha256"],
                        previous_fencing_token=lease_row["fencing_token"],
                        previous_renewal_sequence=lease_row["renewal_sequence"],
                        terminal_state=parsed.state.value,
                    )
                    if updated != 1:
                        raise sqlite3.OperationalError("terminal lease release CAS failed")
                return AdmissionResult(VSourceStatus.ACCEPTED, True, verified.digest)
        except (sqlite3.Error, ValidationError, ValueError) as exc:
            status = VSourceStatus.UNAVAILABLE if isinstance(exc, sqlite3.Error) else VSourceStatus.REJECTED
            return AdmissionResult(status, False, verified.digest, reason=str(exc))

    def record_response(
        self,
        response: ChalResponse | Mapping[str, Any],
    ) -> AdmissionResult:
        ready = self._ready(require_signer=False)
        if ready is not None:
            return AdmissionResult(ready, False)
        parsed, error = self._coerce(ChalResponse, response)
        if error is not None:
            return AdmissionResult(error, False)
        assert parsed is not None
        verified, error = self._verify_document(
            parsed,
            expected_account_id=parsed.account_id,
            expected_node_id=parsed.node_id,
        )
        if error is not None:
            return AdmissionResult(error, False)
        assert verified is not None
        now, error = self._now()
        if error is not None:
            return AdmissionResult(error, False)
        assert now is not None
        try:
            with self._transaction() as conn:
                self._expire_active_leases(conn, now)
                lease_row = conn.execute(
                    "SELECT * FROM leases WHERE lease_id = ?",
                    (parsed.lease_id,),
                ).fetchone()
                if lease_row is None:
                    return AdmissionResult(VSourceStatus.REJECTED, False, verified.digest)
                if lease_row["state"] == LeaseState.EXPIRED.value:
                    return AdmissionResult(VSourceStatus.LEASE_EXPIRED, False, verified.digest)
                if lease_row["state"] != LeaseState.ACTIVE.value or lease_row["terminal_state"] is not None:
                    return AdmissionResult(VSourceStatus.TERMINAL_LEASE, False, verified.digest)
                lease = LeaseDocument.model_validate_json(lease_row["document_json"])
                if (
                    lease.state.value != lease_row["state"]
                    or document_sha256(lease) != lease_row["document_sha256"]
                ):
                    return AdmissionResult(VSourceStatus.STALE_LEASE, False, verified.digest)
                try:
                    validate_lease_bound_response(parsed, lease)
                except ValueError:
                    return AdmissionResult(VSourceStatus.STALE_LEASE, False, verified.digest)
                existing = conn.execute(
                    "SELECT digest FROM responses WHERE response_id = ?",
                    (parsed.response_id,),
                ).fetchone()
                if existing is not None:
                    if existing["digest"] == verified.digest:
                        return AdmissionResult(
                            VSourceStatus.IDEMPOTENT_REPLAY,
                            True,
                            verified.digest,
                        )
                    return AdmissionResult(VSourceStatus.REPLAY, False, verified.digest)
                conn.execute(
                    """
                    INSERT INTO responses
                    (response_id, digest, lease_id, document_json, admitted_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        parsed.response_id,
                        verified.digest,
                        parsed.lease_id,
                        parsed.model_dump_json(by_alias=True),
                        _wire_time(now),
                    ),
                )
                return AdmissionResult(VSourceStatus.ACCEPTED, True, verified.digest)
        except (sqlite3.Error, ValidationError, ValueError) as exc:
            status = VSourceStatus.UNAVAILABLE if isinstance(exc, sqlite3.Error) else VSourceStatus.REJECTED
            return AdmissionResult(status, False, verified.digest, reason=str(exc))

    def get_lease(self, lease_id: str) -> LeaseDocument | None:
        if self._state_error is not None:
            return None
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT state, document_json FROM leases WHERE lease_id = ?",
                    (lease_id,),
                ).fetchone()
                if row is None:
                    return None
                lease = LeaseDocument.model_validate_json(row["document_json"])
                if lease.state.value != row["state"]:
                    return None
                return lease
        except (sqlite3.Error, ValidationError):
            return None

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR IGNORE INTO meta(key, value)
                VALUES ('schema_version', '1');

                CREATE TABLE IF NOT EXISTS inventories (
                    inventory_id TEXT PRIMARY KEY,
                    digest TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    health TEXT NOT NULL,
                    admitted_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_inventories_account
                    ON inventories(account_id, node_id, inventory_id);

                CREATE TABLE IF NOT EXISTS inventory_digests (
                    inventory_id TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    admitted_at TEXT NOT NULL,
                    PRIMARY KEY(inventory_id, digest)
                );

                CREATE TABLE IF NOT EXISTS idempotency (
                    account_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    capability_sha256 TEXT NOT NULL,
                    capability_json TEXT NOT NULL,
                    authenticated_subject_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    accepted INTEGER NOT NULL CHECK(accepted IN (0, 1)),
                    placement_id TEXT,
                    lease_id TEXT,
                    lease_sha256 TEXT,
                    fencing_token INTEGER,
                    renewal_sequence INTEGER,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY(account_id, idempotency_key)
                );

                CREATE TABLE IF NOT EXISTS capabilities (
                    capability_id TEXT PRIMARY KEY,
                    digest TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    admitted_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS placements (
                    placement_id TEXT PRIMARY KEY,
                    request_sha256 TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    result TEXT NOT NULL,
                    decided_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_placements_request
                    ON placements(account_id, request_sha256);

                CREATE TABLE IF NOT EXISTS leases (
                    lease_id TEXT PRIMARY KEY,
                    placement_id TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    inventory_id TEXT NOT NULL,
                    inventory_sha256 TEXT NOT NULL,
                    document_sha256 TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    terminal_state TEXT,
                    fencing_token INTEGER NOT NULL,
                    renewal_sequence INTEGER NOT NULL,
                    renewals_remaining INTEGER NOT NULL,
                    not_before TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    cpu_millicores INTEGER NOT NULL,
                    memory_bytes INTEGER NOT NULL,
                    gpu_count INTEGER NOT NULL,
                    gpu_memory_bytes INTEGER NOT NULL,
                    storage_bytes INTEGER NOT NULL,
                    ingress_bps INTEGER NOT NULL,
                    egress_bps INTEGER NOT NULL,
                    gpu_ids_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_leases_inventory
                    ON leases(account_id, node_id, state, expires_at);
                CREATE INDEX IF NOT EXISTS idx_leases_request
                    ON leases(account_id, request_sha256);

                CREATE TABLE IF NOT EXISTS lifecycle_events (
                    event_id TEXT PRIMARY KEY,
                    digest TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    workload_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    admitted_at TEXT NOT NULL,
                    UNIQUE(lease_id, workload_id, sequence)
                );

                CREATE TABLE IF NOT EXISTS responses (
                    response_id TEXT PRIMARY KEY,
                    digest TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    admitted_at TEXT NOT NULL
                );
                """
            )
            self._migrate_schema(conn)
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                detail = "unknown" if integrity is None else str(integrity[0])
                raise sqlite3.DatabaseError(f"sqlite integrity check failed: {detail}")

    @contextmanager
    def _transaction(self) -> Any:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except Exception:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:
            raise sqlite3.OperationalError("state service is not configured")
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=_SQLITE_BUSY_TIMEOUT_MS / 1000,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        self._ensure_columns(
            conn,
            "idempotency",
            {
                "capability_id": "TEXT NOT NULL DEFAULT ''",
                "capability_sha256": "TEXT NOT NULL DEFAULT ''",
                "capability_json": "TEXT NOT NULL DEFAULT ''",
                "authenticated_subject_id": "TEXT NOT NULL DEFAULT ''",
                "status": "TEXT NOT NULL DEFAULT ''",
                "accepted": "INTEGER NOT NULL DEFAULT 0 CHECK(accepted IN (0, 1))",
                "placement_id": "TEXT",
                "lease_id": "TEXT",
                "lease_sha256": "TEXT",
                "fencing_token": "INTEGER",
                "renewal_sequence": "INTEGER",
                "reason": "TEXT",
                "completed_at": "TEXT NOT NULL DEFAULT ''",
            },
        )

    def _ensure_columns(
        self,
        conn: sqlite3.Connection,
        table: str,
        columns: Mapping[str, str],
    ) -> None:
        existing = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def _ready(self, *, require_signer: bool) -> VSourceStatus | None:
        if self._state_error is not None:
            return VSourceStatus.UNAVAILABLE
        if self.key_resolver is None or self.clock is None:
            return VSourceStatus.UNAVAILABLE
        if require_signer and self.signer is None:
            return VSourceStatus.UNAVAILABLE
        return None

    def _now(self) -> tuple[datetime | None, VSourceStatus | None]:
        if self.clock is None:
            return None, VSourceStatus.UNAVAILABLE
        try:
            now = self.clock.now()
        except Exception:
            return None, VSourceStatus.UNAVAILABLE
        if now.tzinfo is None or now.utcoffset() is None:
            return None, VSourceStatus.UNAVAILABLE
        return now.astimezone(UTC).replace(microsecond=0), None

    def _coerce(
        self,
        model_type: type[ModelT],
        document: ModelT | Mapping[str, Any],
    ) -> tuple[ModelT | None, VSourceStatus | None]:
        try:
            if isinstance(document, model_type):
                return document, None
            if isinstance(document, Mapping):
                return _model_from_wire(model_type, document), None
        except (TypeError, ValueError, ValidationError):
            return None, VSourceStatus.MALFORMED_DOCUMENT
        return None, VSourceStatus.MALFORMED_DOCUMENT

    def _verify_document(
        self,
        document: BaseModel,
        *,
        expected_account_id: str,
        expected_node_id: str | None = None,
    ) -> tuple[_VerifiedDocument | None, VSourceStatus | None]:
        if self.key_resolver is None:
            return None, VSourceStatus.UNAVAILABLE
        now, error = self._now()
        if error is not None:
            return None, error
        assert now is not None
        signature = getattr(document, "signature", None)
        if not isinstance(signature, Signature):
            return None, VSourceStatus.MALFORMED_DOCUMENT
        try:
            key = self.key_resolver.resolve_key(signature.key_id)
        except Exception:
            return None, VSourceStatus.UNAVAILABLE
        if key is None:
            return None, VSourceStatus.UNKNOWN_KEY
        if key.revoked:
            return None, VSourceStatus.KEY_REVOKED
        if key.account_id != expected_account_id:
            return None, VSourceStatus.ACCOUNT_MISMATCH
        if (
            self.scheduler_audience not in set(key.audiences)
            and "*" not in set(key.audiences)
        ):
            return None, VSourceStatus.AUDIENCE_MISMATCH
        if expected_node_id is not None and key.node_id != expected_node_id:
            return None, VSourceStatus.ACCOUNT_MISMATCH
        if key.not_before is not None and now + self.max_clock_skew < key.not_before:
            return None, VSourceStatus.CLOCK_SKEW
        if key.not_after is not None and now > key.not_after:
            return None, VSourceStatus.KEY_REVOKED
        if isinstance(document, CapabilityDocument) and (
            document.revocation_epoch < key.minimum_capability_revocation_epoch
        ):
            return None, VSourceStatus.KEY_REVOKED
        try:
            signature_bytes = base64.urlsafe_b64decode(signature.value + "==")
            key.ed25519_public_key().verify(signature_bytes, signing_bytes(document))
        except (InvalidSignature, ValueError):
            return None, VSourceStatus.INVALID_SIGNATURE
        window_error = self._validate_document_window(document, now)
        if window_error is not None:
            return None, window_error
        return _VerifiedDocument(document, document_sha256(document), key), None

    def _validate_document_window(
        self,
        document: BaseModel,
        now: datetime,
    ) -> VSourceStatus | None:
        if isinstance(document, ChalRequest):
            return self._validate_ttl_window(document.issued_at, document.ttl_seconds, now)
        if isinstance(document, CapabilityDocument):
            return self._validate_ttl_window(document.not_before, document.ttl_seconds, now)
        if isinstance(document, ResourceInventory):
            return self._validate_ttl_window(document.observed_at, document.ttl_seconds, now)
        if isinstance(document, LifecycleEvent):
            if now + self.max_clock_skew < document.occurred_at:
                return VSourceStatus.CLOCK_SKEW
        if isinstance(document, ChalResponse):
            if now + self.max_clock_skew < document.completed_at:
                return VSourceStatus.CLOCK_SKEW
        if isinstance(document, ErrorFrame):
            return None
        return None

    def _validate_ttl_window(
        self,
        starts_at: datetime,
        ttl_seconds: int,
        now: datetime,
    ) -> VSourceStatus | None:
        if now + self.max_clock_skew < starts_at:
            return VSourceStatus.CLOCK_SKEW
        if now > starts_at + timedelta(seconds=ttl_seconds):
            return VSourceStatus.DOCUMENT_EXPIRED
        return None

    def _expire_active_leases(self, conn: sqlite3.Connection, now: datetime) -> None:
        rows = conn.execute(
            """
            SELECT *
            FROM leases
            WHERE state = ? AND expires_at <= ?
            """,
            (
                LeaseState.ACTIVE.value,
                _wire_time(now),
            ),
        ).fetchall()
        for row in rows:
            current = LeaseDocument.model_validate_json(row["document_json"])
            if current.state != LeaseState.ACTIVE or document_sha256(current) != row["document_sha256"]:
                raise sqlite3.DatabaseError("lease document does not match durable active state")
            expired = self._sign_lease_state(current, LeaseState.EXPIRED)
            updated = self._update_lease_document(
                conn,
                expired,
                now,
                previous_sha256=row["document_sha256"],
                previous_fencing_token=row["fencing_token"],
                previous_renewal_sequence=row["renewal_sequence"],
                terminal_state=LeaseState.EXPIRED.value,
            )
            if updated != 1:
                raise sqlite3.OperationalError("lease expiry CAS failed")

    def _handle_idempotency(
        self,
        conn: sqlite3.Connection,
        request: ChalRequest,
        request_sha256: str,
        capability: CapabilityDocument,
        capability_sha256: str,
        authenticated_subject_id: str,
        now: datetime,
    ) -> AllocationResult | None:
        existing = conn.execute(
            """
            SELECT *
            FROM idempotency
            WHERE account_id = ? AND idempotency_key = ?
            """,
            (request.account_id, request.idempotency_key),
        ).fetchone()
        if existing is None:
            return None
        if existing["request_sha256"] != request_sha256:
            return AllocationResult(
                VSourceStatus.IDEMPOTENCY_COLLISION,
                False,
                request_sha256,
            )
        if (
            existing["capability_id"] != capability.capability_id
            or existing["capability_sha256"] != capability_sha256
            or existing["capability_json"] != capability.model_dump_json(by_alias=True)
            or existing["authenticated_subject_id"] != authenticated_subject_id
            or capability.subject_id != authenticated_subject_id
            or capability.account_id != request.account_id
            or request.capability_id != capability.capability_id
        ):
            return AllocationResult(VSourceStatus.REPLAY, False, request_sha256)
        if not existing["status"]:
            return AllocationResult(
                VSourceStatus.UNAVAILABLE,
                False,
                request_sha256,
                reason="incomplete idempotency record",
            )
        return self._allocation_from_idempotency_row(
            conn,
            existing,
            request_sha256,
            now,
        )

    def _allocation_from_idempotency_row(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        request_sha256: str,
        now: datetime,
    ) -> AllocationResult:
        status = VSourceStatus(row["status"])
        placement = self._placement_from_idempotency(conn, row)
        if not row["accepted"]:
            return AllocationResult(
                status,
                False,
                request_sha256,
                placement=placement,
                reason=row["reason"],
            )
        lease_id = row["lease_id"]
        if lease_id is None:
            return AllocationResult(
                VSourceStatus.UNAVAILABLE,
                False,
                request_sha256,
                placement=placement,
                reason="accepted idempotency record has no lease",
            )
        lease_row = conn.execute(
            "SELECT * FROM leases WHERE lease_id = ?",
            (lease_id,),
        ).fetchone()
        if lease_row is None:
            return AllocationResult(
                VSourceStatus.STALE_LEASE,
                False,
                request_sha256,
                placement=placement,
            )
        lease = LeaseDocument.model_validate_json(lease_row["document_json"])
        if lease_row["state"] != lease.state.value:
            return AllocationResult(
                VSourceStatus.STALE_LEASE,
                False,
                request_sha256,
                placement=placement,
                reason="lease document state differs from durable state",
            )
        if lease_row["state"] == LeaseState.EXPIRED.value:
            return AllocationResult(
                VSourceStatus.LEASE_EXPIRED,
                False,
                request_sha256,
                placement=placement,
                lease=lease,
            )
        if lease_row["state"] != LeaseState.ACTIVE.value or lease_row["terminal_state"] is not None:
            return AllocationResult(
                VSourceStatus.TERMINAL_LEASE,
                False,
                request_sha256,
                placement=placement,
                lease=lease,
            )
        if lease.not_before + timedelta(seconds=lease.ttl_seconds) <= now:
            return AllocationResult(
                VSourceStatus.LEASE_EXPIRED,
                False,
                request_sha256,
                placement=placement,
                lease=lease,
            )
        if (
            lease_row["document_sha256"] != row["lease_sha256"]
            or lease_row["fencing_token"] != row["fencing_token"]
            or lease_row["renewal_sequence"] != row["renewal_sequence"]
        ):
            return AllocationResult(
                VSourceStatus.STALE_LEASE,
                False,
                request_sha256,
                placement=placement,
            )
        return AllocationResult(
            VSourceStatus.IDEMPOTENT_REPLAY,
            True,
            request_sha256,
            placement=placement,
            lease=lease,
        )

    def _placement_from_idempotency(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> PlacementDecision | None:
        placement_id = row["placement_id"]
        if placement_id is None:
            return None
        placement_row = conn.execute(
            "SELECT document_json FROM placements WHERE placement_id = ?",
            (placement_id,),
        ).fetchone()
        if placement_row is None:
            return None
        return PlacementDecision.model_validate_json(placement_row["document_json"])

    def _store_idempotency_result(
        self,
        conn: sqlite3.Connection,
        request: ChalRequest,
        request_sha256: str,
        capability: CapabilityDocument,
        capability_sha256: str,
        authenticated_subject_id: str,
        result: AllocationResult,
        now: datetime,
    ) -> None:
        placement_id = result.placement.placement_id if result.placement is not None else None
        lease_id = result.lease.lease_id if result.lease is not None else None
        lease_sha256 = document_sha256(result.lease) if result.lease is not None else None
        fencing_token = result.lease.fencing_token if result.lease is not None else None
        renewal_sequence = result.lease.renewal_sequence if result.lease is not None else None
        if result.accepted and (placement_id is None or lease_id is None):
            raise ValueError("accepted allocation requires persisted placement and lease")
        conn.execute(
            """
            INSERT INTO idempotency
            (
                account_id, idempotency_key, request_sha256, request_json,
                capability_id, capability_sha256, capability_json,
                authenticated_subject_id, status, accepted, placement_id,
                lease_id, lease_sha256, fencing_token, renewal_sequence,
                reason, created_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.account_id,
                request.idempotency_key,
                request_sha256,
                request.model_dump_json(by_alias=True),
                capability.capability_id,
                capability_sha256,
                capability.model_dump_json(by_alias=True),
                authenticated_subject_id,
                result.status.value,
                1 if result.accepted else 0,
                placement_id,
                lease_id,
                lease_sha256,
                fencing_token,
                renewal_sequence,
                result.reason,
                _wire_time(now),
                _wire_time(now),
            ),
        )

    def _admit_capability(
        self,
        conn: sqlite3.Connection,
        capability: CapabilityDocument,
        capability_sha256: str,
        now: datetime,
    ) -> VSourceStatus | None:
        existing = conn.execute(
            """
            SELECT digest, account_id, subject_id, document_json
            FROM capabilities
            WHERE capability_id = ?
            """,
            (capability.capability_id,),
        ).fetchone()
        if existing is not None:
            if (
                existing["digest"] == capability_sha256
                and existing["account_id"] == capability.account_id
                and existing["subject_id"] == capability.subject_id
                and existing["document_json"] == capability.model_dump_json(by_alias=True)
            ):
                return None
            return VSourceStatus.REPLAY
        conn.execute(
            """
            INSERT INTO capabilities
            (capability_id, digest, document_json, account_id, subject_id, admitted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                capability.capability_id,
                capability_sha256,
                capability.model_dump_json(by_alias=True),
                capability.account_id,
                capability.subject_id,
                _wire_time(now),
            ),
        )
        return None

    def _load_current_inventories(
        self,
        conn: sqlite3.Connection,
        account_id: str,
        now: datetime,
    ) -> list[ResourceInventory]:
        rows = conn.execute(
            """
            SELECT document_json
            FROM inventories
            WHERE account_id = ? AND expires_at > ?
            ORDER BY node_id ASC, inventory_id ASC, digest ASC
            """,
            (account_id, _wire_time(now)),
        ).fetchall()
        return [
            ResourceInventory.model_validate_json(row["document_json"])
            for row in rows
        ]

    def _refresh_selected_inventory(
        self,
        conn: sqlite3.Connection,
        request: ChalRequest,
        capability: CapabilityDocument,
        selected: _CandidateEvaluation,
        authenticated_subject_id: str,
        now: datetime,
    ) -> tuple[ResourceInventory, _CandidateEvaluation] | None:
        candidate = selected.candidate
        row = conn.execute(
            """
            SELECT digest, document_json
            FROM inventories
            WHERE account_id = ?
              AND node_id = ?
              AND inventory_id = ?
              AND expires_at > ?
            """,
            (
                request.account_id,
                candidate.node_id,
                candidate.inventory_id,
                _wire_time(now),
            ),
        ).fetchone()
        if row is None or row["digest"] != candidate.inventory_sha256:
            return None
        inventory = ResourceInventory.model_validate_json(row["document_json"])
        if document_sha256(inventory) != candidate.inventory_sha256:
            return None
        refreshed = self._evaluate_candidate(
            conn,
            request,
            capability,
            inventory,
            authenticated_subject_id,
            now,
        )
        if (
            not refreshed.candidate.eligible
            or refreshed.candidate.inventory_sha256 != candidate.inventory_sha256
        ):
            return None
        return inventory, refreshed

    def _evaluate_candidate(
        self,
        conn: sqlite3.Connection,
        request: ChalRequest,
        capability: CapabilityDocument,
        inventory: ResourceInventory,
        authenticated_subject_id: str,
        now: datetime,
    ) -> _CandidateEvaluation:
        inventory_sha256 = document_sha256(inventory)
        reasons: set[str] = set()
        if inventory.health != NodeHealth.READY:
            reasons.add("node_health")
        if request.account_id != capability.account_id or request.account_id != inventory.account_id:
            reasons.add("account")
        if request.capability_id != capability.capability_id:
            reasons.add("capability")
        if authenticated_subject_id != capability.subject_id:
            reasons.add("subject")
        if inventory.node_id not in capability.audience_node_ids:
            reasons.add("audience")
        if _ATTESTATION_RANK[inventory.attestation] < _ATTESTATION_RANK[
            capability.constraints.minimum_attestation
        ]:
            reasons.add("attestation")
        if request.workload_kind not in capability.constraints.workload_kinds:
            reasons.add("workload")
        if request.workload_kind not in inventory.workload_kinds:
            reasons.add("workload")
        if not any(
            device_uri_matches_prefix(request.device_uri, prefix)
            for prefix in capability.constraints.resource_prefixes
        ):
            reasons.add("device_prefix")
        if not resource_vector_within(
            request.constraints.resources,
            capability.constraints.resources,
        ):
            reasons.add("capability")
        transports = sorted(
            {
                transport
                for transport in inventory.transports
                if transport in capability.constraints.transports
            },
            key=lambda item: item.value,
        )
        if not transports:
            reasons.add("transport")
        reservation = self._reservation_for_node(conn, request.account_id, inventory.node_id, now)
        available = inventory.resources.allocatable
        requested = request.constraints.resources
        if requested.cpu_millicores > available.cpu_millicores - reservation.cpu_millicores:
            reasons.add("cpu")
        if requested.memory_bytes > available.memory_bytes - reservation.memory_bytes:
            reasons.add("memory")
        if requested.storage_bytes > available.storage_bytes - reservation.storage_bytes:
            reasons.add("storage")
        if requested.ingress_bps > available.ingress_bps - reservation.ingress_bps:
            reasons.add("ingress")
        if requested.egress_bps > available.egress_bps - reservation.egress_bps:
            reasons.add("egress")
        gpu_ids = self._select_gpu_ids(inventory, reservation, requested)
        if requested.gpu_count and not gpu_ids:
            reasons.add("gpu")
        candidate = PlacementCandidate(
            node_id=inventory.node_id,
            account_id=inventory.account_id,
            inventory_id=inventory.inventory_id,
            inventory_sha256=inventory_sha256,
            eligible=not reasons,
            score=1.0 if not reasons else 0.0,
            reasons=sorted(reasons) if reasons else ["capacity", "same_account"],
        )
        return _CandidateEvaluation(
            candidate=candidate,
            transport=transports[0] if transports else None,
            gpu_ids=gpu_ids,
        )

    def _reservation_for_node(
        self,
        conn: sqlite3.Connection,
        account_id: str,
        node_id: str,
        now: datetime,
    ) -> _Reservation:
        rows = conn.execute(
            """
            SELECT *
            FROM leases
            WHERE account_id = ?
              AND node_id = ?
              AND state = ?
              AND expires_at > ?
            """,
            (account_id, node_id, LeaseState.ACTIVE.value, _wire_time(now)),
        ).fetchall()
        gpu_ids: set[str] = set()
        reservation = _Reservation()
        for row in rows:
            gpu_ids.update(json.loads(row["gpu_ids_json"]))
            reservation = _Reservation(
                cpu_millicores=reservation.cpu_millicores + row["cpu_millicores"],
                memory_bytes=reservation.memory_bytes + row["memory_bytes"],
                storage_bytes=reservation.storage_bytes + row["storage_bytes"],
                ingress_bps=reservation.ingress_bps + row["ingress_bps"],
                egress_bps=reservation.egress_bps + row["egress_bps"],
                gpu_ids=frozenset(gpu_ids),
            )
        return reservation

    def _select_gpu_ids(
        self,
        inventory: ResourceInventory,
        reservation: _Reservation,
        requested: ResourceVector,
    ) -> list[str]:
        if requested.gpu_count == 0:
            return []
        available = [
            (gpu_id, gpu.allocatable_memory_bytes)
            for gpu_id, gpu in sorted(inventory.resources.gpus.items())
            if gpu_id not in reservation.gpu_ids
        ]
        if len(available) < requested.gpu_count:
            return []
        selected = available[: requested.gpu_count]
        if sum(memory for _, memory in selected) < requested.gpu_memory_bytes:
            return []
        return [gpu_id for gpu_id, _ in selected]

    def _build_lease(
        self,
        request: ChalRequest,
        request_sha256: str,
        inventory: ResourceInventory,
        placement_id: str,
        transport: TransportKind | None,
        gpu_ids: list[str],
        now: datetime,
        ttl_seconds: int,
    ) -> LeaseDocument:
        if transport is None:
            raise ValueError("cannot lease without a selected transport")
        payload = {
            "schema": "planetary.vsource.lease.v1",
            "lease_id": self._stable_id("lease", request_sha256),
            "placement_id": placement_id,
            "request_id": request.request_id,
            "request_sha256": request_sha256,
            "capability_id": request.capability_id,
            "node_id": inventory.node_id,
            "inventory_id": inventory.inventory_id,
            "inventory_sha256": document_sha256(inventory),
            "account_id": request.account_id,
            "transport": transport.value,
            "resources": request.constraints.resources.model_dump(mode="json"),
            "gpu_ids": gpu_ids,
            "state": LeaseState.ACTIVE.value,
            "not_before": _wire_time(now),
            "ttl_seconds": ttl_seconds,
            "fencing_token": 1,
            "renewal_sequence": 0,
            "renewals_remaining": self.default_renewals_remaining,
            "revocation_reason": None,
        }
        return sign_contract_document(LeaseDocument, payload, self.signer)  # type: ignore[arg-type]

    def _build_placed_decision(
        self,
        request: ChalRequest,
        request_sha256: str,
        evaluations: list[_CandidateEvaluation],
        selected: _CandidateEvaluation,
        now: datetime,
        placement_id: str,
    ) -> PlacementDecision:
        payload = {
            "schema": "planetary.vsource.placement.v1",
            "placement_id": placement_id,
            "request_id": request.request_id,
            "request_sha256": request_sha256,
            "trace_id": request.trace_id,
            "account_id": request.account_id,
            "scheduler_id": self.scheduler_id,
            "scheduler_scope": "same_account_private_cell",
            "transport": selected.transport.value if selected.transport else "lan_mtls",
            "decided_at": _wire_time(now),
            "result": PlacementResult.PLACED.value,
            "selected_candidate": selected.candidate.model_dump(mode="json"),
            "candidates": [
                item.candidate.model_dump(mode="json")
                for item in sorted(
                    evaluations,
                    key=lambda item: (
                        not item.candidate.eligible,
                        item.candidate.node_id,
                        item.candidate.inventory_id,
                        item.candidate.inventory_sha256,
                    ),
                )
            ],
            "policy_version": self.policy_version,
            "rejection_error": None,
        }
        return sign_contract_document(PlacementDecision, payload, self.signer)  # type: ignore[arg-type]

    def _build_unplaced_decision(
        self,
        request: ChalRequest,
        request_sha256: str,
        evaluations: list[_CandidateEvaluation],
        now: datetime,
        placement_id: str,
    ) -> PlacementDecision:
        fallback_transport = self._fallback_transport(evaluations)
        error = self._build_error_frame(
            request,
            request_sha256,
            ErrorCode.NO_PLACEMENT,
            now,
        )
        payload = {
            "schema": "planetary.vsource.placement.v1",
            "placement_id": placement_id,
            "request_id": request.request_id,
            "request_sha256": request_sha256,
            "trace_id": request.trace_id,
            "account_id": request.account_id,
            "scheduler_id": self.scheduler_id,
            "scheduler_scope": "same_account_private_cell",
            "transport": fallback_transport.value,
            "decided_at": _wire_time(now),
            "result": PlacementResult.UNPLACED.value,
            "selected_candidate": None,
            "candidates": [
                item.candidate.model_dump(mode="json")
                for item in sorted(
                    evaluations,
                    key=lambda item: (
                        item.candidate.node_id,
                        item.candidate.inventory_id,
                        item.candidate.inventory_sha256,
                    ),
                )
            ],
            "policy_version": self.policy_version,
            "rejection_error": error.model_dump(mode="json", by_alias=True),
        }
        return sign_contract_document(PlacementDecision, payload, self.signer)  # type: ignore[arg-type]

    def _fallback_transport(
        self,
        evaluations: list[_CandidateEvaluation],
    ) -> TransportKind:
        transports = sorted(
            {
                item.transport
                for item in evaluations
                if item.transport is not None
            },
            key=lambda item: item.value,
        )
        return transports[0] if transports else TransportKind.LAN_MTLS

    def _build_error_frame(
        self,
        request: ChalRequest,
        request_sha256: str,
        code: ErrorCode,
        now: datetime,
    ) -> ErrorFrame:
        payload = {
            "schema": "planetary.chal.error.v1",
            "error_id": self._stable_id("error", f"{request_sha256}:{code.value}"),
            "request_id": request.request_id,
            "request_sha256": request_sha256,
            "trace_id": request.trace_id,
            "code": code.value,
            "retryable": False,
            "diagnostic_id": None,
            "retry_after_ms": None,
            "device_uri": request.device_uri,
        }
        return sign_contract_document(ErrorFrame, payload, self.signer)  # type: ignore[arg-type]

    def _store_placement(
        self,
        conn: sqlite3.Connection,
        placement: PlacementDecision,
    ) -> None:
        document_json = placement.model_dump_json(by_alias=True)
        existing = conn.execute(
            "SELECT document_json FROM placements WHERE placement_id = ?",
            (placement.placement_id,),
        ).fetchone()
        if existing is not None:
            if existing["document_json"] == document_json:
                return
            raise sqlite3.IntegrityError("placement identity collision")
        conn.execute(
            """
            INSERT INTO placements
            (placement_id, request_sha256, account_id, document_json, result, decided_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                placement.placement_id,
                placement.request_sha256,
                placement.account_id,
                document_json,
                placement.result.value,
                _wire_time(placement.decided_at),
            ),
        )

    def _insert_lease(
        self,
        conn: sqlite3.Connection,
        lease: LeaseDocument,
        now: datetime,
    ) -> None:
        expires_at = lease.not_before + timedelta(seconds=lease.ttl_seconds)
        conn.execute(
            """
            INSERT INTO leases
            (
                lease_id, placement_id, request_sha256, account_id, node_id,
                inventory_id, inventory_sha256, document_sha256, document_json,
                state, terminal_state, fencing_token, renewal_sequence,
                renewals_remaining, not_before, expires_at, cpu_millicores,
                memory_bytes, gpu_count, gpu_memory_bytes, storage_bytes,
                ingress_bps, egress_bps, gpu_ids_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lease.lease_id,
                lease.placement_id,
                lease.request_sha256,
                lease.account_id,
                lease.node_id,
                lease.inventory_id,
                lease.inventory_sha256,
                document_sha256(lease),
                lease.model_dump_json(by_alias=True),
                lease.state.value,
                None,
                lease.fencing_token,
                lease.renewal_sequence,
                lease.renewals_remaining,
                _wire_time(lease.not_before),
                _wire_time(expires_at),
                lease.resources.cpu_millicores,
                lease.resources.memory_bytes,
                lease.resources.gpu_count,
                lease.resources.gpu_memory_bytes,
                lease.resources.storage_bytes,
                lease.resources.ingress_bps,
                lease.resources.egress_bps,
                json.dumps(lease.gpu_ids, separators=(",", ":")),
                _wire_time(now),
            ),
        )

    def _update_lease_document(
        self,
        conn: sqlite3.Connection,
        lease: LeaseDocument,
        now: datetime,
        *,
        previous_sha256: str,
        previous_fencing_token: int,
        previous_renewal_sequence: int,
        terminal_state: str | None,
    ) -> int:
        expires_at = lease.not_before + timedelta(seconds=lease.ttl_seconds)
        cursor = conn.execute(
            """
            UPDATE leases
            SET
                placement_id = ?,
                request_sha256 = ?,
                account_id = ?,
                node_id = ?,
                inventory_id = ?,
                inventory_sha256 = ?,
                document_sha256 = ?,
                document_json = ?,
                state = ?,
                terminal_state = ?,
                fencing_token = ?,
                renewal_sequence = ?,
                renewals_remaining = ?,
                not_before = ?,
                expires_at = ?,
                cpu_millicores = ?,
                memory_bytes = ?,
                gpu_count = ?,
                gpu_memory_bytes = ?,
                storage_bytes = ?,
                ingress_bps = ?,
                egress_bps = ?,
                gpu_ids_json = ?,
                updated_at = ?
            WHERE lease_id = ?
              AND document_sha256 = ?
              AND fencing_token = ?
              AND renewal_sequence = ?
              AND state = ?
              AND terminal_state IS NULL
            """,
            (
                lease.placement_id,
                lease.request_sha256,
                lease.account_id,
                lease.node_id,
                lease.inventory_id,
                lease.inventory_sha256,
                document_sha256(lease),
                lease.model_dump_json(by_alias=True),
                lease.state.value,
                terminal_state,
                lease.fencing_token,
                lease.renewal_sequence,
                lease.renewals_remaining,
                _wire_time(lease.not_before),
                _wire_time(expires_at),
                lease.resources.cpu_millicores,
                lease.resources.memory_bytes,
                lease.resources.gpu_count,
                lease.resources.gpu_memory_bytes,
                lease.resources.storage_bytes,
                lease.resources.ingress_bps,
                lease.resources.egress_bps,
                json.dumps(lease.gpu_ids, separators=(",", ":")),
                _wire_time(now),
                lease.lease_id,
                previous_sha256,
                previous_fencing_token,
                previous_renewal_sequence,
                LeaseState.ACTIVE.value,
            ),
        )
        return cursor.rowcount

    def _sign_lease_state(
        self,
        lease: LeaseDocument,
        state: LeaseState,
        *,
        revocation_reason: LeaseRevocationReason | None = None,
    ) -> LeaseDocument:
        if self.signer is None:
            raise sqlite3.OperationalError("signer unavailable for lease state transition")
        payload = lease.model_dump(mode="json", by_alias=True)
        payload.update(
            state=state.value,
            revocation_reason=revocation_reason.value if revocation_reason else None,
        )
        payload.pop("signature", None)
        return sign_contract_document(LeaseDocument, payload, self.signer)

    def _stable_id(self, prefix: str, digest_material: str) -> str:
        import hashlib

        digest = hashlib.sha256(digest_material.encode("utf-8")).hexdigest()
        return f"{prefix}:{digest[:32]}"
