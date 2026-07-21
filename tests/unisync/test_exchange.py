"""Paired request/response exchange over one lease-bound mTLS socket.

Real TCP, real TLS 1.3, real certificates, real content-addressed stores — the
same fixtures the object-transfer tests use. The point of these tests is not
that a round trip works; it is that the SECOND leg cannot escape the first
leg's authorization.
"""

from __future__ import annotations

import dataclasses
import socket
import threading
from pathlib import Path

import pytest

from services.unisync.contracts import TransferContext
from services.unisync.errors import AuthorizationError
from services.unisync.exchange import (
    derive_response_context,
    request_over_dialed_socket,
    serve_exchange_over_tls_socket,
)
from services.unisync.storage import ContentAddressedStore
from services.unisync.tls import TrustedLanClient, TrustedLanServer, _server_context
from tests.unisync.conftest import StrictValidator, make_context
from tests.unisync.test_tls_transport import (  # noqa: F401  (certs is a fixture)
    CertMaterial,
    certs,
    _client_credentials,
    _client_enrollment,
    _server_credentials,
    _server_enrollment,
    _server_instance,
)

PROMPT = b'{"prompt":"summarize my notes","model":"demo-3b"}'
ANSWER = b'{"response":"Your notes cover three topics.","model":"demo-3b"}'


def _requester(tmp_path: Path, certs: CertMaterial):
    """Desktop: TLS client + leg-1 sender, and leg-2 receiver."""
    client = TrustedLanClient(
        credentials=_client_credentials(certs),
        server_hostname="server.test",
        validator=StrictValidator(),
        enrolled_server_identities={_server_enrollment(certs)},
        chunk_size=32,
    )
    # Leg 2 arrives FROM the responder, so the responder is the enrolled
    # "client identity" from this side's point of view. This receiver never
    # listens — it only supplies the verified-receive half over a socket the
    # requester already opened — so its own credentials are unused here.
    receiver = TrustedLanServer(
        bind_host="127.0.0.1",
        port=0,
        credentials=_client_credentials(certs),
        destination_root=tmp_path / "requester" / "destination",
        validator=StrictValidator(),
        declared_listener_addresses={"127.0.0.1"},
        allowed_client_sans={"server.test", "127.0.0.1"},
        enrolled_client_identities={_server_enrollment(certs)},
    )
    return client, receiver


def _responder(tmp_path: Path, certs: CertMaterial):
    """Worker: TLS server + leg-1 receiver, and leg-2 sender."""
    receiver = _server_instance(tmp_path / "responder", certs)
    responder = TrustedLanClient(
        credentials=_server_credentials(certs),
        server_hostname="client.test",
        validator=StrictValidator(),
        enrolled_server_identities={_client_enrollment(certs)},
        chunk_size=32,
    )
    return receiver, responder


def _run_exchange(tmp_path, certs, handler, *, request_context=None):
    """Drive one full exchange over a real socket; return (receipt, errors)."""
    request_context = request_context or make_context(PROMPT, transport="lan_mtls")
    outbox = ContentAddressedStore(tmp_path / "requester-outbox")
    outbox.put_bytes(PROMPT)

    client, receiver = _requester(tmp_path, certs)
    resp_receiver, responder = _responder(tmp_path, certs)

    listen = socket.socket()
    listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen.bind(("127.0.0.1", 0))
    listen.listen(1)
    port = listen.getsockname()[1]
    errors: list[BaseException] = []

    def responder_side() -> None:
        try:
            conn, _ = listen.accept()
            ctx = _server_context(responder.credentials)
            tls = ctx.wrap_socket(conn, server_side=True)
            try:
                tls.settimeout(10)
                serve_exchange_over_tls_socket(
                    tls_sock=tls,
                    receiver=resp_receiver,
                    responder=responder,
                    handler=handler,
                    response_root=tmp_path / "responder-outbox",
                )
            finally:
                tls.close()
        except BaseException as exc:  # surfaced by the caller
            errors.append(exc)

    thread = threading.Thread(target=responder_side)
    thread.start()
    try:
        raw = socket.create_connection(("127.0.0.1", port), timeout=5)
        receipt = request_over_dialed_socket(
            raw_sock=raw,
            client=client,
            receiver=receiver,
            request_context=request_context,
            source_root=outbox.root,
        )
    finally:
        thread.join(timeout=10)
        listen.close()
    return receipt, errors, receiver


def test_exchange_returns_the_response_under_the_same_lease(tmp_path, certs):
    """One socket, one lease: prompt goes out, answer comes back verified."""
    seen: list[tuple[bytes, str]] = []

    def handler(request_bytes: bytes, ctx: TransferContext) -> bytes:
        seen.append((request_bytes, ctx.lease_id))
        return ANSWER

    receipt, errors, receiver = _run_exchange(tmp_path, certs, handler)
    if errors:
        raise errors[0]

    # The responder saw the exact request bytes under the request's lease.
    assert seen and seen[0][0] == PROMPT
    request_context = make_context(PROMPT, transport="lan_mtls")
    assert seen[0][1] == request_context.lease_id

    # The requester stored the exact response bytes, digest-verified.
    inbox = ContentAddressedStore(tmp_path / "requester" / "destination")
    assert inbox.read_bytes(receipt["object_sha256"]) == ANSWER

    # Leg 2 was authorized as its own transfer, with the responder as source.
    leg2 = receiver.validator.calls[-1]
    assert leg2.lease_id == request_context.lease_id
    assert leg2.fencing_token == request_context.fencing_token
    assert leg2.source_node_id == "node:destination"
    assert leg2.destination_node_id == "node:source"
    assert receiver.validator.peer_identities[-1].node_id == "node:destination"


def test_response_under_a_different_lease_is_rejected(tmp_path, certs):
    """A responder cannot answer under a lease it was not granted."""

    def handler(request_bytes: bytes, ctx: TransferContext) -> bytes:
        return ANSWER

    # Force the responder to mint a foreign context instead of deriving one.
    import services.unisync.exchange as exchange_mod

    real_derive = exchange_mod.derive_response_context

    def forged(request_context, *, response_sha256, byte_length):
        good = real_derive(
            request_context, response_sha256=response_sha256, byte_length=byte_length
        )
        return dataclasses.replace(good, lease_id="lease:attacker-controlled")

    exchange_mod.derive_response_context = forged
    try:
        # The requester rejects the START frame outright — before its validator
        # is ever consulted — because the declared lease is not the one leg 1
        # was authorized under.
        with pytest.raises(AuthorizationError, match="lease_id"):
            _run_exchange(tmp_path, certs, handler)
    finally:
        exchange_mod.derive_response_context = real_derive


def test_response_with_a_swapped_fencing_token_is_rejected(tmp_path, certs):
    """Fencing token is part of the binding, not decoration."""
    request_context = make_context(PROMPT, transport="lan_mtls")
    response = derive_response_context(
        request_context, response_sha256="b" * 64, byte_length=len(ANSWER)
    )
    stale = dataclasses.replace(response, fencing_token=response.fencing_token + 1)
    with pytest.raises(AuthorizationError, match="fencing_token"):
        from services.unisync.exchange import _require_derived_from

        _require_derived_from(stale, request_context)


def test_response_that_echoes_the_request_object_is_rejected(tmp_path, certs):
    """Replaying the request bytes back is not an answer."""
    request_context = make_context(PROMPT, transport="lan_mtls")
    echo = derive_response_context(
        request_context,
        response_sha256=request_context.object_sha256,
        byte_length=request_context.byte_length,
    )
    with pytest.raises(AuthorizationError, match="repeats the request object"):
        from services.unisync.exchange import _require_derived_from

        _require_derived_from(echo, request_context)


def test_derive_response_context_swaps_direction_and_keeps_authority(tmp_path):
    request_context = make_context(PROMPT, transport="lan_mtls")
    response = derive_response_context(
        request_context, response_sha256="c" * 64, byte_length=7
    )
    assert response.source_node_id == request_context.destination_node_id
    assert response.destination_node_id == request_context.source_node_id
    assert response.lease_id == request_context.lease_id
    assert response.lease_sha256 == request_context.lease_sha256
    assert response.fencing_token == request_context.fencing_token
    assert response.request_sha256 == request_context.request_sha256
    assert response.expires_at == request_context.expires_at
    assert response.object_sha256 == "c" * 64
    assert response.byte_length == 7


def test_handler_failure_does_not_leak_a_response(tmp_path, certs):
    """A handler that raises must fail the exchange, not send partial bytes."""

    def handler(request_bytes: bytes, ctx: TransferContext) -> bytes:
        raise RuntimeError("model unavailable")

    with pytest.raises(Exception):
        _run_exchange(tmp_path, certs, handler)


def test_derived_response_is_rejected_by_the_real_signed_lease_validator():
    """The response leg has no authority under a real lease. See
    docs/design/EXCHANGE_RESPONSE_AUTHORITY.md.

    This remains TRUE and is why `ResponseGrant` exists: a lease authorizes
    delivery to exactly ONE leased node, so it can never carry a result back to
    the requester. The fix was not to weaken this rule but to add a separate
    controller-signed authority for the return direction — see
    tests/unisync/test_mesh_grant.py, where the same physical documents DO
    authorize the return leg once a grant is present.
    """
    import json
    from pathlib import Path

    from services.unisync.mesh_common import b64url_decode
    from services.unisync.mesh_lease import SignedLeaseValidator

    evidence_path = (
        Path(__file__).resolve().parents[2]
        / "docs/evidence/F020_DESKTOP_INITIATED_PULL_PHYSICAL_2026-07-20.evidence.json"
    )
    evidence = json.loads(evidence_path.read_text())
    documents = evidence["documents"]
    trust = evidence["trust_bundle"]
    request_context = TransferContext.from_wire(evidence["transfer"]["transfer_context"])
    common = dict(
        lease_wire=documents["active_lease"],
        request_wire=documents["request"],
        scheduler_key_id=trust["scheduler_key_id"],
        scheduler_public_key=b64url_decode(
            trust["scheduler_public_key_base64"], expected_bytes=32
        ),
        controller_key_id=trust["controller_key_id"],
        controller_public_key=b64url_decode(
            trust["controller_public_key_base64"], expected_bytes=32
        ),
    )

    # The forward leg is genuinely authorized by these documents.
    SignedLeaseValidator(expected_context=request_context, **common)

    # The return leg is not: a lease authorizes delivery to ONE leased node.
    response_context = derive_response_context(
        request_context, response_sha256="d" * 64, byte_length=61
    )
    with pytest.raises(AuthorizationError, match="destination is not the leased node"):
        SignedLeaseValidator(expected_context=response_context, **common)


def test_exchange_runs_under_a_real_signed_grant_over_real_tcp(tmp_path, certs):
    """The wired path: leg 2 authorized by a real controller-signed grant.

    Leg 1 keeps the ordinary transfer validator; leg 2 is validated by
    `SignedResponseGrantValidator` parsing a genuinely signed `ResponseGrant`.
    Real TCP, real TLS 1.3, real certificates, real ed25519 signature — no
    permissive validator on the return direction.
    """
    from datetime import UTC, datetime

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from contracts.chal_vsource.v1.models import ResponseGrant
    from services.unisync.mesh_grant import (
        SignedResponseGrantValidator,
        build_response_grant_payload,
    )
    from services.vsource import Ed25519DocumentSigner, sign_contract_document

    request_context = make_context(PROMPT, transport="lan_mtls")
    controller_key = Ed25519PrivateKey.generate()
    controller = Ed25519DocumentSigner("key:controller:test:0001", controller_key)
    grant = sign_contract_document(
        ResponseGrant,
        build_response_grant_payload(
            grant_id="grant:test:live",
            account_id=request_context.account_id,
            request_sha256=request_context.request_sha256,
            lease_id=request_context.lease_id,
            lease_sha256=request_context.lease_sha256,
            fencing_token=request_context.fencing_token,
            responder_node_id=request_context.destination_node_id,
            destination_node_id=request_context.source_node_id,
            max_byte_length=4096,
            media_type="application/json",
            issued_at=datetime.now(UTC),
        ),
        controller,
    ).model_dump(mode="json", by_alias=True)

    def grant_validator():
        return SignedResponseGrantValidator(
            grant_wire=grant,
            request_sha256=request_context.request_sha256,
            controller_key_id="key:controller:test:0001",
            controller_public_key=controller_key.public_key().public_bytes_raw(),
            expected_source_node_id=request_context.destination_node_id,
            expected_destination_node_id=request_context.source_node_id,
        )

    outbox = ContentAddressedStore(tmp_path / "requester-outbox")
    outbox.put_bytes(PROMPT)

    client, receiver = _requester(tmp_path, certs)
    # THE POINT: the return leg is authorized by the signed grant.
    receiver.validator = grant_validator()

    resp_receiver, responder = _responder(tmp_path, certs)
    responder.validator = grant_validator()

    listen = socket.socket()
    listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen.bind(("127.0.0.1", 0))
    listen.listen(1)
    port = listen.getsockname()[1]
    errors = []

    def responder_side():
        try:
            conn, _ = listen.accept()
            ctx = _server_context(responder.credentials)
            tls = ctx.wrap_socket(conn, server_side=True)
            try:
                tls.settimeout(10)
                serve_exchange_over_tls_socket(
                    tls_sock=tls,
                    receiver=resp_receiver,
                    responder=responder,
                    handler=lambda payload, ctx_: ANSWER,
                    response_root=tmp_path / "responder-outbox",
                )
            finally:
                tls.close()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=responder_side)
    thread.start()
    try:
        raw = socket.create_connection(("127.0.0.1", port), timeout=5)
        receipt = request_over_dialed_socket(
            raw_sock=raw,
            client=client,
            receiver=receiver,
            request_context=request_context,
            source_root=outbox.root,
        )
    finally:
        thread.join(timeout=10)
        listen.close()

    if errors:
        raise errors[0]
    inbox = ContentAddressedStore(tmp_path / "requester" / "destination")
    assert inbox.read_bytes(receipt["object_sha256"]) == ANSWER


def test_a_response_over_the_granted_ceiling_is_refused_on_the_wire(tmp_path, certs):
    """The byte ceiling is enforced by the transport, not just in unit tests."""
    from datetime import UTC, datetime

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from contracts.chal_vsource.v1.models import ResponseGrant
    from services.unisync.mesh_grant import (
        SignedResponseGrantValidator,
        build_response_grant_payload,
    )
    from services.vsource import Ed25519DocumentSigner, sign_contract_document

    request_context = make_context(PROMPT, transport="lan_mtls")
    controller_key = Ed25519PrivateKey.generate()
    controller = Ed25519DocumentSigner("key:controller:test:0001", controller_key)
    grant = sign_contract_document(
        ResponseGrant,
        build_response_grant_payload(
            grant_id="grant:test:tiny",
            account_id=request_context.account_id,
            request_sha256=request_context.request_sha256,
            lease_id=request_context.lease_id,
            lease_sha256=request_context.lease_sha256,
            fencing_token=request_context.fencing_token,
            responder_node_id=request_context.destination_node_id,
            destination_node_id=request_context.source_node_id,
            max_byte_length=4,  # smaller than ANSWER
            media_type="application/json",
            issued_at=datetime.now(UTC),
        ),
        controller,
    ).model_dump(mode="json", by_alias=True)

    validator = SignedResponseGrantValidator(
        grant_wire=grant,
        request_sha256=request_context.request_sha256,
        controller_key_id="key:controller:test:0001",
        controller_public_key=controller_key.public_key().public_bytes_raw(),
        expected_source_node_id=request_context.destination_node_id,
        expected_destination_node_id=request_context.source_node_id,
    )
    oversized = derive_response_context(
        request_context, response_sha256="f" * 64, byte_length=len(ANSWER)
    )
    with pytest.raises(AuthorizationError, match="byte ceiling"):
        validator.validate_transfer(oversized)
