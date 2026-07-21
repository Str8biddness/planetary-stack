"""Authorization for the return leg of a request/response exchange.

A lease is authority to deliver TO one leased node, so it cannot carry a
computed result back to the requester. And a result's digest cannot appear as a
content reference in a request signed before the work ran. Those two rules are
correct and this module does not weaken either of them: instead the controller
signs a separate `ResponseGrant` that authorizes exactly one bounded response.

What the grant binds:

  * the exact signed request being answered (`request_sha256`)
  * the lease the forward leg ran under (id, digest, fencing token)
  * the one node allowed to answer, and the one node allowed to receive
  * a hard byte ceiling and an exact media type
  * its own validity window

What it deliberately does NOT bind is the response digest. That is irreducible —
nobody can hash a computation that has not happened yet. The concession is kept
to that single value; everything around it is owner-signed.

HONEST SCOPE — what a grant does and does not buy, given the product claim that
*your data stays on your own machines*:

  * It keeps a computed answer inside the mesh: only an enrolled, named node may
    produce it, only the named destination may receive it, over the authenticated
    encrypted transport, once.
  * The byte ceiling bounds how much can ever travel on the return path, so the
    channel cannot be turned into a bulk egress route.
  * It does NOT make a compromised node honest. A node that is already yours and
    already owns its key can return whatever it likes within the ceiling. That
    is a different property from data locality and this module does not claim it.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from contracts.chal_vsource.v1.canonical import signing_bytes
from contracts.chal_vsource.v1.models import ResponseGrant, TransportKind

from .contracts import AuthenticatedPeerIdentity, TransferContext
from .errors import AuthorizationError


def parse_signed_grant(
    grant_wire: Mapping[str, Any],
    *,
    controller_key_id: str,
    controller_public_key: bytes,
) -> ResponseGrant:
    """Strictly parse one response grant and verify its controller signature."""

    if not isinstance(controller_key_id, str) or not controller_key_id:
        raise AuthorizationError("controller key id is required")
    if not isinstance(controller_public_key, bytes) or len(controller_public_key) != 32:
        raise AuthorizationError("controller public key must be 32 raw Ed25519 bytes")
    try:
        grant = ResponseGrant.model_validate_json(
            json.dumps(dict(grant_wire), allow_nan=False, separators=(",", ":"))
        )
    except Exception as exc:
        raise AuthorizationError(f"document is not a valid response grant: {exc}") from exc
    if grant.signature.key_id != controller_key_id:
        raise AuthorizationError("grant is not signed by the pinned controller key")
    try:
        signature = base64.urlsafe_b64decode(grant.signature.value + "==")
        Ed25519PublicKey.from_public_bytes(controller_public_key).verify(
            signature, signing_bytes(grant)
        )
    except (InvalidSignature, ValueError) as exc:
        raise AuthorizationError("grant signature is invalid") from exc
    return grant


class SignedResponseGrantValidator:
    """Authorize exactly one response transfer against one signed grant.

    Shaped like `SignedLeaseValidator` on purpose: the transport calls
    `validate_transfer` and cannot tell which authority it is talking to, so the
    return leg gets the same treatment as every other transfer.

    Single-use is enforced in memory here AND is expected to be fenced durably
    by the caller's `LeaseUseStore`; this object refusing a second call is a
    guard, not the system of record.
    """

    def __init__(
        self,
        *,
        grant_wire: Mapping[str, Any],
        request_sha256: str,
        controller_key_id: str,
        controller_public_key: bytes,
        expected_source_node_id: str,
        expected_destination_node_id: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._now = now or (lambda: datetime.now(UTC))
        grant = parse_signed_grant(
            grant_wire,
            controller_key_id=controller_key_id,
            controller_public_key=controller_public_key,
        )
        if grant.request_sha256 != request_sha256:
            raise AuthorizationError("grant does not answer the authorized request")
        if grant.transport != TransportKind.LAN_MTLS:
            raise AuthorizationError("grant transport is not lan_mtls")
        if grant.responder_node_id != expected_source_node_id:
            raise AuthorizationError("grant does not name this responder")
        if grant.destination_node_id != expected_destination_node_id:
            raise AuthorizationError("grant does not name this destination")
        self._grant = grant
        self._used = False

    @property
    def grant(self) -> ResponseGrant:
        return self._grant

    def validate_transfer(
        self,
        context: TransferContext,
        peer_identity: AuthenticatedPeerIdentity | None = None,
    ) -> None:
        grant = self._grant
        if context.account_id != grant.account_id:
            raise AuthorizationError("transfer account does not match the grant")
        if context.request_sha256 != grant.request_sha256:
            raise AuthorizationError("transfer does not bind the granted request digest")
        if context.lease_id != grant.lease_id:
            raise AuthorizationError("transfer does not bind the granted lease id")
        if context.lease_sha256 != grant.lease_sha256:
            raise AuthorizationError("transfer does not bind the granted lease digest")
        if context.fencing_token != grant.fencing_token:
            raise AuthorizationError("transfer fencing token is stale for this grant")
        if context.selected_transport != TransportKind.LAN_MTLS.value:
            raise AuthorizationError("transfer transport is not lan_mtls")
        if context.source_node_id != grant.responder_node_id:
            raise AuthorizationError("transfer source is not the granted responder")
        if context.destination_node_id != grant.destination_node_id:
            raise AuthorizationError("transfer destination is not the granted receiver")
        if context.byte_length > grant.max_byte_length:
            raise AuthorizationError("response exceeds the granted byte ceiling")

        current = self._now()
        if current.tzinfo is None or current.utcoffset() is None:
            raise AuthorizationError("validator clock must be timezone-aware")
        current = current.astimezone(UTC)
        not_before = grant.issued_at.astimezone(UTC)
        if current < not_before:
            raise AuthorizationError("grant is not yet valid")
        if current >= not_before + timedelta(seconds=grant.ttl_seconds):
            raise AuthorizationError("grant has expired")
        if context.expires_at.astimezone(UTC) > not_before + timedelta(
            seconds=grant.ttl_seconds
        ):
            raise AuthorizationError("transfer context outlives the grant window")

        if peer_identity is not None:
            if peer_identity.account_id != grant.account_id:
                raise AuthorizationError("authenticated peer account does not match the grant")
            # Both ends of the exchange call this validator, so the peer is the
            # responder when we are receiving and the destination when we are
            # sending. Requiring one specific node here would reject the
            # responder's own upload. The direction itself is already bound:
            # `require_authorized` checks the peer against the context's
            # source/destination role, and the context is checked against the
            # grant above. What is left to enforce is that the peer is a party
            # to THIS grant at all.
            if peer_identity.node_id not in (
                grant.responder_node_id,
                grant.destination_node_id,
            ):
                raise AuthorizationError("authenticated peer is not a party to the grant")

        # A grant authorizes ONE response. The transport re-validates on every
        # frame, so the fence has to tolerate repeated calls for the same
        # object while refusing a different one.
        if self._used and self._used != context.object_sha256:
            raise AuthorizationError("grant has already been used for another response")
        self._used = context.object_sha256


def build_response_grant_payload(
    *,
    grant_id: str,
    account_id: str,
    request_sha256: str,
    lease_id: str,
    lease_sha256: str,
    fencing_token: int,
    responder_node_id: str,
    destination_node_id: str,
    max_byte_length: int,
    media_type: str,
    issued_at: datetime,
    ttl_seconds: int = 300,
) -> dict[str, Any]:
    """Unsigned grant payload, ready for `sign_contract_document`."""

    return {
        "schema": "planetary.chal.response_grant.v1",
        "grant_id": grant_id,
        "account_id": account_id,
        "request_sha256": request_sha256,
        "lease_id": lease_id,
        "lease_sha256": lease_sha256,
        "fencing_token": fencing_token,
        "responder_node_id": responder_node_id,
        "destination_node_id": destination_node_id,
        "max_byte_length": max_byte_length,
        "media_type": media_type,
        "transport": TransportKind.LAN_MTLS.value,
        "issued_at": issued_at.astimezone(UTC)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ttl_seconds": ttl_seconds,
    }
