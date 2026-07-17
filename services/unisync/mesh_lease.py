"""Scheduler-signed vSource lease binding for Unisync mesh transfers.

`SignedLeaseValidator` is the injected `AuthorizationLeaseValidator` used by
both mesh transfer roles.  It authorizes exactly one transfer: the exact
`TransferContext` handed to it at construction, bound to one scheduler-signed
active `lan_mtls` vSource lease.  Any other context, a stale fencing token or
lease digest, an expired or revoked lease, or a foreign account fails closed
before bytes are committed.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from contracts.chal_vsource.v1.canonical import document_sha256, signing_bytes
from contracts.chal_vsource.v1.models import (
    ChalRequest,
    LeaseDocument,
    LeaseState,
    TransportKind,
)

from .contracts import AuthenticatedPeerIdentity, TransferContext
from .errors import AuthorizationError
from .mesh_common import (
    MeshSecurityError,
    compact_json,
    fsync_directory,
    read_private_file,
    require_identifier,
    require_sha256,
    safe_owned_directory,
    strict_json,
    wire_time,
    write_exclusive_private,
)

LEASE_USE_FILE = "lease-use.json"
LEASE_USE_SCHEMA = "planetary.unisync.mesh_lease_use.v1"
LEASE_USE_RECORD_SCHEMA = "planetary.unisync.mesh_lease_use_record.v1"
MAX_LEASE_USE_BYTES = 1024 * 1024
_USE_STATES = frozenset({"admitted", "completed", "failed"})
_USE_RECORD_FIELDS = frozenset(
    {
        "schema",
        "lease_id",
        "lease_sha256",
        "fencing_token",
        "state",
        "updated_at",
    }
)


def parse_signed_lease(
    lease_wire: Mapping[str, Any],
    *,
    scheduler_key_id: str,
    scheduler_public_key: bytes,
) -> LeaseDocument:
    """Strictly parse one lease document and verify its scheduler signature."""

    if not isinstance(scheduler_key_id, str) or not scheduler_key_id:
        raise AuthorizationError("scheduler key id is required")
    if not isinstance(scheduler_public_key, bytes) or len(scheduler_public_key) != 32:
        raise AuthorizationError("scheduler public key must be 32 raw Ed25519 bytes")
    try:
        lease = LeaseDocument.model_validate_json(
            json.dumps(dict(lease_wire), allow_nan=False, separators=(",", ":"))
        )
    except Exception as exc:
        raise AuthorizationError(f"lease document is not a valid v1 lease: {exc}") from exc
    if lease.signature.key_id != scheduler_key_id:
        raise AuthorizationError("lease is not signed by the pinned scheduler key")
    try:
        signature = base64.urlsafe_b64decode(lease.signature.value + "==")
        Ed25519PublicKey.from_public_bytes(scheduler_public_key).verify(
            signature, signing_bytes(lease)
        )
    except (InvalidSignature, ValueError) as exc:
        raise AuthorizationError("lease scheduler signature is invalid") from exc
    return lease


def parse_signed_request(
    request_wire: Mapping[str, Any],
    *,
    controller_key_id: str,
    controller_public_key: bytes,
) -> ChalRequest:
    """Strictly parse one CHAL request and verify its controller signature."""

    if not isinstance(controller_key_id, str) or not controller_key_id:
        raise AuthorizationError("controller key id is required")
    if not isinstance(controller_public_key, bytes) or len(controller_public_key) != 32:
        raise AuthorizationError("controller public key must be 32 raw Ed25519 bytes")
    try:
        request = ChalRequest.model_validate_json(
            json.dumps(dict(request_wire), allow_nan=False, separators=(",", ":"))
        )
    except Exception as exc:
        raise AuthorizationError(f"request document is not a valid v1 request: {exc}") from exc
    if request.signature.key_id != controller_key_id:
        raise AuthorizationError("request is not signed by the pinned controller key")
    try:
        signature = base64.urlsafe_b64decode(request.signature.value + "==")
        Ed25519PublicKey.from_public_bytes(controller_public_key).verify(
            signature, signing_bytes(request)
        )
    except (InvalidSignature, ValueError) as exc:
        raise AuthorizationError("request controller signature is invalid") from exc
    return request


class SignedLeaseValidator:
    """Authorize exactly one TransferContext against one active signed lease."""

    def __init__(
        self,
        *,
        lease_wire: Mapping[str, Any],
        request_wire: Mapping[str, Any],
        scheduler_key_id: str,
        scheduler_public_key: bytes,
        controller_key_id: str,
        controller_public_key: bytes,
        expected_context: TransferContext,
        now: Callable[[], datetime] | None = None,
        revocation_probe: Callable[[str], bool] | None = None,
    ) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        self._revocation_probe = revocation_probe
        lease = parse_signed_lease(
            lease_wire,
            scheduler_key_id=scheduler_key_id,
            scheduler_public_key=scheduler_public_key,
        )
        request = parse_signed_request(
            request_wire,
            controller_key_id=controller_key_id,
            controller_public_key=controller_public_key,
        )
        if lease.state != LeaseState.ACTIVE:
            raise AuthorizationError(f"lease is not active (state={lease.state.value})")
        if lease.transport != TransportKind.LAN_MTLS:
            raise AuthorizationError("lease transport is not lan_mtls")
        self._lease = lease
        self._request = request
        self._lease_sha256 = document_sha256(lease)
        self._expected_wire = expected_context.to_wire()
        if expected_context.selected_transport != TransportKind.LAN_MTLS.value:
            raise AuthorizationError("transfer context transport is not lan_mtls")
        if expected_context.lease_id != lease.lease_id:
            raise AuthorizationError("transfer context does not bind the signed lease id")
        if expected_context.lease_sha256 != self._lease_sha256:
            raise AuthorizationError("transfer context does not bind the signed lease digest")
        if expected_context.fencing_token != lease.fencing_token:
            raise AuthorizationError("transfer context fencing token is stale")
        if expected_context.account_id != lease.account_id:
            raise AuthorizationError("transfer context account does not match the lease")
        if expected_context.request_sha256 != lease.request_sha256:
            raise AuthorizationError("transfer context does not bind the lease request digest")
        if document_sha256(request) != lease.request_sha256:
            raise AuthorizationError("signed request digest does not match the signed lease")
        if request.account_id != lease.account_id:
            raise AuthorizationError("signed request account does not match the lease")
        if expected_context.destination_node_id != lease.node_id:
            raise AuthorizationError("transfer destination is not the leased node")
        if expected_context.source_node_id == expected_context.destination_node_id:
            raise AuthorizationError("transfer source and destination must differ")
        lease_expiry = lease.not_before + timedelta(seconds=lease.ttl_seconds)
        if expected_context.expires_at.astimezone(UTC) > lease_expiry.astimezone(UTC):
            raise AuthorizationError("transfer context outlives the signed lease window")
        request_expiry = request.issued_at + timedelta(seconds=request.ttl_seconds)
        if expected_context.expires_at.astimezone(UTC) > request_expiry.astimezone(UTC):
            raise AuthorizationError("transfer context outlives the signed request window")
        authorized_objects = (request.workload_manifest, *request.inputs)
        if not any(
            reference.sha256 == expected_context.object_sha256
            and reference.size_bytes == expected_context.byte_length
            for reference in authorized_objects
        ):
            raise AuthorizationError(
                "transfer object is not an exact content reference in the signed request"
            )

    @property
    def lease(self) -> LeaseDocument:
        return self._lease

    @property
    def lease_sha256(self) -> str:
        return self._lease_sha256

    def validate_transfer(
        self,
        context: TransferContext,
        peer_identity: AuthenticatedPeerIdentity | None = None,
    ) -> None:
        if context.to_wire() != self._expected_wire:
            raise AuthorizationError("transfer context does not match the authorized job")
        if self._revocation_probe is not None and self._revocation_probe(self._lease_sha256):
            raise AuthorizationError("lease has been revoked")
        current = self._now()
        if current.tzinfo is None or current.utcoffset() is None:
            raise AuthorizationError("validator clock must be timezone-aware")
        current = current.astimezone(UTC)
        not_before = self._lease.not_before.astimezone(UTC)
        if current < not_before:
            raise AuthorizationError("lease is not yet valid")
        if current >= not_before + timedelta(seconds=self._lease.ttl_seconds):
            raise AuthorizationError("lease has expired")
        request_not_before = self._request.issued_at.astimezone(UTC)
        if current < request_not_before:
            raise AuthorizationError("request is not yet valid")
        if current >= request_not_before + timedelta(seconds=self._request.ttl_seconds):
            raise AuthorizationError("request has expired")
        if context.lease_id != self._lease.lease_id:
            raise AuthorizationError("transfer context lease id is stale")
        if context.fencing_token != self._lease.fencing_token:
            raise AuthorizationError("transfer context fencing token is stale")
        if context.lease_sha256 != self._lease_sha256:
            raise AuthorizationError("transfer context lease digest is stale")
        if peer_identity is not None and peer_identity.account_id != self._lease.account_id:
            raise AuthorizationError("authenticated peer account does not match the lease")


class LeaseUseStore:
    """Durable node-local replay fence for signed lease revisions.

    Admission is intentionally fail-stop: a process crash after ``begin``
    leaves the lease revision unusable. Automated recovery is a later gate.
    """

    def __init__(self, directory: Path, *, account_id: str, node_id: str) -> None:
        self._directory = safe_owned_directory(Path(directory), create=False)
        self._path = self._directory / LEASE_USE_FILE
        self._account_id = require_identifier("account_id", account_id)
        self._node_id = require_identifier("node_id", node_id)
        self._records: dict[str, dict[str, Any]] = {}
        try:
            self._path.lstat()
        except FileNotFoundError:
            self._save()
        else:
            self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        payload = strict_json(
            read_private_file(self._path, max_bytes=MAX_LEASE_USE_BYTES)
        )
        if set(payload) != {"schema", "account_id", "node_id", "records"}:
            raise MeshSecurityError("lease-use state has unexpected fields")
        if (
            payload["schema"] != LEASE_USE_SCHEMA
            or payload["account_id"] != self._account_id
            or payload["node_id"] != self._node_id
            or not isinstance(payload["records"], list)
        ):
            raise MeshSecurityError("lease-use state does not bind this node")
        records: dict[str, dict[str, Any]] = {}
        for record in payload["records"]:
            if not isinstance(record, dict) or set(record) != _USE_RECORD_FIELDS:
                raise MeshSecurityError("lease-use record has unexpected fields")
            if record["schema"] != LEASE_USE_RECORD_SCHEMA:
                raise MeshSecurityError("lease-use record schema is unsupported")
            lease_id = require_identifier("lease_id", record["lease_id"])
            require_sha256("lease_sha256", record["lease_sha256"])
            fencing_token = record["fencing_token"]
            if (
                not isinstance(fencing_token, int)
                or isinstance(fencing_token, bool)
                or fencing_token <= 0
            ):
                raise MeshSecurityError("lease-use fencing token must be positive")
            if record["state"] not in _USE_STATES:
                raise MeshSecurityError("lease-use state is unsupported")
            datetime.strptime(record["updated_at"], "%Y-%m-%dT%H:%M:%SZ")
            if lease_id in records:
                raise MeshSecurityError("lease-use state contains duplicate lease ids")
            records[lease_id] = dict(record)
        self._records = records

    def _save(self) -> None:
        payload = {
            "schema": LEASE_USE_SCHEMA,
            "account_id": self._account_id,
            "node_id": self._node_id,
            "records": [self._records[key] for key in sorted(self._records)],
        }
        encoded = (compact_json(payload) + "\n").encode("utf-8")
        if len(encoded) > MAX_LEASE_USE_BYTES:
            raise MeshSecurityError("lease-use state exceeds its size bound")
        temp = self._directory / f".{LEASE_USE_FILE}.{secrets.token_hex(8)}.tmp"
        write_exclusive_private(temp, encoded)
        try:
            os.replace(temp, self._path)
        except OSError:
            try:
                os.unlink(temp)
            except FileNotFoundError:
                pass
            raise
        fsync_directory(self._directory)
        if stat.S_IMODE(self._path.lstat().st_mode) != 0o600:
            raise MeshSecurityError("lease-use state must have mode 0600")

    def begin(self, context: TransferContext) -> None:
        if context.account_id != self._account_id:
            raise AuthorizationError("lease-use account does not match this node")
        if self._node_id not in {
            context.source_node_id,
            context.destination_node_id,
        }:
            raise AuthorizationError("lease-use context does not name this node")
        self._load()
        existing = self._records.get(context.lease_id)
        if existing is not None and existing["fencing_token"] >= context.fencing_token:
            raise AuthorizationError("lease revision was already admitted or superseded")
        record = {
            "schema": LEASE_USE_RECORD_SCHEMA,
            "lease_id": context.lease_id,
            "lease_sha256": context.lease_sha256,
            "fencing_token": context.fencing_token,
            "state": "admitted",
            "updated_at": wire_time(datetime.now(UTC)),
        }
        previous = self._records
        self._records = {**previous, context.lease_id: record}
        try:
            self._save()
        except BaseException:
            self._records = previous
            raise

    def finish(self, context: TransferContext, *, succeeded: bool) -> None:
        self._load()
        record = self._records.get(context.lease_id)
        if (
            record is None
            or record["lease_sha256"] != context.lease_sha256
            or record["fencing_token"] != context.fencing_token
            or record["state"] != "admitted"
        ):
            raise AuthorizationError("lease-use completion does not match admitted revision")
        replacement = {
            **record,
            "state": "completed" if succeeded else "failed",
            "updated_at": wire_time(datetime.now(UTC)),
        }
        previous = self._records
        self._records = {**previous, context.lease_id: replacement}
        try:
            self._save()
        except BaseException:
            self._records = previous
            raise
