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
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from contracts.chal_vsource.v1.canonical import document_sha256, signing_bytes
from contracts.chal_vsource.v1.models import LeaseDocument, LeaseState, TransportKind

from .contracts import AuthenticatedPeerIdentity, TransferContext
from .errors import AuthorizationError


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


class SignedLeaseValidator:
    """Authorize exactly one TransferContext against one active signed lease."""

    def __init__(
        self,
        *,
        lease_wire: Mapping[str, Any],
        scheduler_key_id: str,
        scheduler_public_key: bytes,
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
        if lease.state != LeaseState.ACTIVE:
            raise AuthorizationError(f"lease is not active (state={lease.state.value})")
        if lease.transport != TransportKind.LAN_MTLS:
            raise AuthorizationError("lease transport is not lan_mtls")
        self._lease = lease
        self._lease_sha256 = document_sha256(lease)
        self._expected_wire = expected_context.to_wire()
        if expected_context.selected_transport != TransportKind.LAN_MTLS.value:
            raise AuthorizationError("transfer context transport is not lan_mtls")
        if expected_context.lease_sha256 != self._lease_sha256:
            raise AuthorizationError("transfer context does not bind the signed lease digest")
        if expected_context.fencing_token != lease.fencing_token:
            raise AuthorizationError("transfer context fencing token is stale")
        if expected_context.account_id != lease.account_id:
            raise AuthorizationError("transfer context account does not match the lease")
        if expected_context.request_sha256 != lease.request_sha256:
            raise AuthorizationError("transfer context does not bind the lease request digest")
        if expected_context.destination_node_id != lease.node_id:
            raise AuthorizationError("transfer destination is not the leased node")
        if expected_context.source_node_id == expected_context.destination_node_id:
            raise AuthorizationError("transfer source and destination must differ")
        lease_expiry = lease.not_before + timedelta(seconds=lease.ttl_seconds)
        if expected_context.expires_at.astimezone(UTC) > lease_expiry.astimezone(UTC):
            raise AuthorizationError("transfer context outlives the signed lease window")

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
        if context.fencing_token != self._lease.fencing_token:
            raise AuthorizationError("transfer context fencing token is stale")
        if context.lease_sha256 != self._lease_sha256:
            raise AuthorizationError("transfer context lease digest is stale")
        if peer_identity is not None and peer_identity.account_id != self._lease.account_id:
            raise AuthorizationError("authenticated peer account does not match the lease")
