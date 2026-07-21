"""Paired request/response exchange over one lease-bound mesh mTLS socket.

The Unisync transport moves ONE content-addressed object per connection: a
sender uploads, a receiver verifies and stores. That is the right shape for
artifacts, and the wrong shape for an inference call, where a requester must
send a prompt and read an answer back on the same authorization.

This module adds that second shape WITHOUT adding a second trust model. An
exchange is two ordinary object transfers on one TLS socket:

    leg 1  requester -> responder   (the request object)
    leg 2  responder -> requester   (the response object)

Both legs carry a `TransferContext`. The leg-2 context is *derived* from leg 1
by `derive_response_context`: same account, same request digest, same lease id,
same lease digest, same fencing token, same transport, same expiry — only the
object digest/length change and the source/destination node ids swap. The
requester enforces that derivation on the wire via the receiver's `on_context`
hook, so a responder cannot answer under a different lease, a different fencing
token, or on behalf of a different node. Every existing check (TLS 1.3, mutual
auth, SAN pinning, enrollment binding, `require_authorized` with the correct
peer role, digest verification, receipt) runs unchanged on BOTH legs.

Roles here are transfer roles, not TCP roles. Which side dialed is independent;
`request_over_dialed_socket` is written for the desktop-initiated case proven in
`docs/design/DESKTOP_INITIATED_RESULT_PULL.md`, where the requester opens the
connection outbound and therefore needs no inbound firewall.

The return leg's authority is a controller-signed `ResponseGrant`, not the
forward lease — a lease authorizes delivery to ONE leased node, and a computed
result's digest cannot be named in a request signed before the work ran. See
`services/unisync/mesh_grant.py` and
`docs/design/EXCHANGE_RESPONSE_AUTHORITY.md`. The requester therefore drives leg
2 with a `SignedResponseGrantValidator`, while leg 1 keeps the ordinary
`SignedLeaseValidator`.

HONEST SCOPE: this is the transport primitive. It does not schedule, does not
acquire leases or grants, and does not know what a "prompt" is — the caller
supplies already-authorized contexts and the responder supplies a handler.
Wiring this under an application client is a separate step.
"""

from __future__ import annotations

import hashlib
import socket
import ssl
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .contracts import TransferContext
from .errors import AuthorizationError, TLSConfigurationError
from .storage import ContentAddressedStore
from .tls import (
    TrustedLanClient,
    TrustedLanServer,
    _client_context,
    _derive_authenticated_peer_identity,
    _require_peer_san,
)

# An exchange handler sees the verified request bytes plus the leg-1 context and
# returns the response bytes. Raising fails the exchange closed.
ExchangeHandler = Callable[[bytes, TransferContext], bytes]


class ExchangeError(TLSConfigurationError):
    """A paired request/response exchange could not be completed safely."""


def derive_response_context(
    request_context: TransferContext,
    *,
    response_sha256: str,
    byte_length: int,
) -> TransferContext:
    """Build the leg-2 context bound to the same lease as leg 1.

    Everything that conveys authority is copied verbatim; only the object being
    moved and the direction change. Constructing it this way (rather than
    letting the responder mint a fresh context) is what makes the binding
    checkable by both sides.
    """

    return TransferContext(
        account_id=request_context.account_id,
        request_sha256=request_context.request_sha256,
        lease_id=request_context.lease_id,
        lease_sha256=request_context.lease_sha256,
        fencing_token=request_context.fencing_token,
        selected_transport=request_context.selected_transport,
        source_node_id=request_context.destination_node_id,
        destination_node_id=request_context.source_node_id,
        object_sha256=response_sha256,
        byte_length=byte_length,
        expires_at=request_context.expires_at,
    )


def _require_derived_from(response: TransferContext, request: TransferContext) -> None:
    """Fail closed unless `response` is the legitimate leg-2 of `request`."""

    # Compare WIRE forms: a context that has crossed the socket has its
    # timestamp truncated to second precision, so comparing in-memory datetimes
    # would reject every legitimate response.
    got = response.to_wire()
    want = request.to_wire()
    bound = (
        ("account_id", got["account_id"], want["account_id"]),
        ("request_sha256", got["request_sha256"], want["request_sha256"]),
        ("lease_id", got["lease_id"], want["lease_id"]),
        ("lease_sha256", got["lease_sha256"], want["lease_sha256"]),
        ("fencing_token", got["fencing_token"], want["fencing_token"]),
        ("selected_transport", got["selected_transport"], want["selected_transport"]),
        ("source_node_id", got["source_node_id"], want["destination_node_id"]),
        ("destination_node_id", got["destination_node_id"], want["source_node_id"]),
        ("expires_at", got["expires_at"], want["expires_at"]),
    )
    for field, actual, expected in bound:
        if actual != expected:
            raise AuthorizationError(
                f"exchange response context is not bound to the request lease: {field}"
            )
    if response.object_sha256 == request.object_sha256:
        # A responder echoing the request object back is not an answer; it also
        # lets a peer claim a receipt it never produced work for.
        raise AuthorizationError("exchange response object repeats the request object")


def request_over_dialed_socket(
    *,
    raw_sock: socket.socket,
    client: TrustedLanClient,
    receiver: TrustedLanServer,
    request_context: TransferContext,
    source_root: Path,
    handshake_timeout: float | None = None,
) -> dict[str, Any]:
    """Requester side: send the request object, read the response object back.

    THIS side opened the TCP connection and is the TLS client. `client` sends
    leg 1 (it must have the responder enrolled as the destination); `receiver`
    stores leg 2 (it must have the responder enrolled as a client identity, and
    permit the responder's SAN). Returns the verified leg-2 receipt.
    """

    context = _client_context(client.credentials)
    raw_sock.settimeout(handshake_timeout or receiver.handshake_timeout)
    with context.wrap_socket(
        raw_sock, server_side=False, server_hostname=client.server_hostname
    ) as tls_sock:
        tls_sock.settimeout(receiver.idle_timeout)
        # Leg 1 — upload_object_over_tls_socket enforces TLS 1.3, binds the
        # enrolled destination, and authorizes us as the transfer source.
        client.upload_object_over_tls_socket(
            tls_sock=tls_sock,
            context=request_context,
            source_root=source_root,
        )
        # Leg 2 — the peer now sends. It must present the same certificate it
        # was just authenticated with, and must answer under the same lease.
        peer_cert = tls_sock.getpeercert()
        if not peer_cert:
            raise AuthorizationError("peer certificate is required")
        _require_peer_san(peer_cert, receiver.allowed_client_sans)
        peer_identity = _derive_authenticated_peer_identity(
            peer_cert=peer_cert,
            der_bytes=tls_sock.getpeercert(binary_form=True),
            enrollments=receiver.enrolled_client_identities,
        )
        receipt = receiver._receive_upload(
            tls_sock,
            peer_identity=peer_identity,
            on_context=lambda response: _require_derived_from(response, request_context),
        )
        if not receipt or "object_sha256" not in receipt:
            raise ExchangeError("exchange did not complete a verified response receipt")
        return receipt


def serve_exchange_over_tls_socket(
    *,
    tls_sock: ssl.SSLSocket,
    receiver: TrustedLanServer,
    responder: TrustedLanClient,
    handler: ExchangeHandler,
    response_root: Path,
) -> dict[str, Any]:
    """Responder side: receive the request object, answer on the same socket.

    `tls_sock` is an already-handshaked socket (this side is the TLS server).
    `receiver` stores leg 1 into its destination root; `handler` turns the
    verified request bytes into response bytes; `responder` sends leg 2 under
    the derived context. Returns the leg-2 transfer result as a dict.
    """

    if tls_sock.version() != "TLSv1.3":
        raise TLSConfigurationError("negotiated TLS version is not TLSv1.3")
    peer_cert = tls_sock.getpeercert()
    if not peer_cert:
        raise AuthorizationError("peer certificate is required")
    _require_peer_san(peer_cert, receiver.allowed_client_sans)
    peer_identity = _derive_authenticated_peer_identity(
        peer_cert=peer_cert,
        der_bytes=tls_sock.getpeercert(binary_form=True),
        enrollments=receiver.enrolled_client_identities,
    )
    receiver._record_audit("client_identity_bound")

    seen: list[TransferContext] = []
    receipt = receiver._receive_upload(
        tls_sock,
        peer_identity=peer_identity,
        on_context=seen.append,
    )
    if not receipt or "object_sha256" not in receipt or not seen:
        raise ExchangeError("exchange did not complete a verified request receipt")
    request_context = seen[0]

    inbox = ContentAddressedStore(receiver.destination_root)
    request_bytes = inbox.read_bytes(receipt["object_sha256"])

    response_bytes = handler(request_bytes, request_context)
    if not isinstance(response_bytes, (bytes, bytearray)):
        raise ExchangeError("exchange handler must return bytes")
    response_bytes = bytes(response_bytes)

    outbox = ContentAddressedStore(response_root)
    response_sha256 = outbox.put_bytes(response_bytes)
    if response_sha256 != hashlib.sha256(response_bytes).hexdigest():
        raise ExchangeError("response object digest does not match the response bytes")

    response_context = derive_response_context(
        request_context,
        response_sha256=response_sha256,
        byte_length=len(response_bytes),
    )
    result = responder.upload_object_over_tls_socket(
        tls_sock=tls_sock,
        context=response_context,
        source_root=outbox.root,
    )
    return {
        "request_sha256": receipt["object_sha256"],
        "response_sha256": response_sha256,
        "byte_length": len(response_bytes),
        "lease_id": response_context.lease_id,
        "fencing_token": response_context.fencing_token,
        "verified_receipt_sha256": result.verified_receipt_sha256,
        "transport_id": result.transport_id,
    }
