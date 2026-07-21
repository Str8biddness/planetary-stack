"""Response grants: authority for one computed answer to travel home.

The decisive test is `test_the_return_leg_now_authorizes_against_real_documents`
— it uses the genuine signed lease and request from the 2026-07-20 physical pull,
the same documents that previously rejected the return leg outright.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from contracts.chal_vsource.v1.models import ResponseGrant
from services.unisync.contracts import AuthenticatedPeerIdentity, TransferContext
from services.unisync.errors import AuthorizationError
from services.unisync.exchange import derive_response_context
from services.unisync.mesh_common import b64url_decode
from services.unisync.mesh_grant import (
    SignedResponseGrantValidator,
    build_response_grant_payload,
)
from services.vsource import Ed25519DocumentSigner, sign_contract_document

EVIDENCE = (
    Path(__file__).resolve().parents[2]
    / "docs/evidence/F020_DESKTOP_INITIATED_PULL_PHYSICAL_2026-07-20.evidence.json"
)
CONTROLLER_KEY_ID = "key:controller:test:0001"
RESPONSE = b'{"schema":"planetary.aivm.result.text-classification.v1","label":"positive"}'


@pytest.fixture
def controller():
    private_key = Ed25519PrivateKey.generate()
    return (
        Ed25519DocumentSigner(CONTROLLER_KEY_ID, private_key),
        private_key.public_key().public_bytes_raw(),
    )


@pytest.fixture
def physical_context() -> TransferContext:
    """The real forward-leg context from the physical pull evidence."""
    evidence = json.loads(EVIDENCE.read_text())
    return TransferContext.from_wire(evidence["transfer"]["transfer_context"])


def _grant(controller_signer, context, *, now=None, **overrides):
    payload = build_response_grant_payload(
        grant_id="grant:test:0001",
        account_id=context.account_id,
        request_sha256=context.request_sha256,
        lease_id=context.lease_id,
        lease_sha256=context.lease_sha256,
        fencing_token=context.fencing_token,
        responder_node_id=context.destination_node_id,
        destination_node_id=context.source_node_id,
        max_byte_length=4096,
        media_type="application/json",
        issued_at=now or datetime.now(UTC),
    )
    payload.update(overrides)
    signed = sign_contract_document(ResponseGrant, payload, controller_signer)
    return signed.model_dump(mode="json", by_alias=True)


def _validator(controller, context, grant_wire=None, **kwargs):
    signer, public = controller
    return SignedResponseGrantValidator(
        grant_wire=grant_wire if grant_wire is not None else _grant(signer, context),
        request_sha256=context.request_sha256,
        controller_key_id=CONTROLLER_KEY_ID,
        controller_public_key=public,
        expected_source_node_id=context.destination_node_id,
        expected_destination_node_id=context.source_node_id,
        **kwargs,
    )


def _response_context(context, payload=RESPONSE, digest="d" * 64):
    return derive_response_context(
        context, response_sha256=digest, byte_length=len(payload)
    )


def test_the_return_leg_now_authorizes_against_real_documents(
    controller, physical_context
):
    """The exact case that failed before grants existed.

    Previously: AuthorizationError "transfer destination is not the leased node".
    """
    signer, _ = controller
    # The grant must live inside the real lease's window, so anchor to it.
    issued = physical_context.expires_at - timedelta(seconds=60)
    grant_wire = _grant(signer, physical_context, now=issued)
    validator = _validator(
        controller,
        physical_context,
        grant_wire=grant_wire,
        now=lambda: issued + timedelta(seconds=5),
    )
    response = _response_context(physical_context)
    # No exception: the computed answer has authority to travel home.
    validator.validate_transfer(response)


def test_forward_leg_context_is_not_authorized_by_a_grant(controller, physical_context):
    """A grant authorizes the RETURN direction only."""
    validator = _validator(controller, physical_context)
    with pytest.raises(AuthorizationError, match="source is not the granted responder"):
        validator.validate_transfer(physical_context)


def test_response_over_the_byte_ceiling_is_refused(controller, physical_context):
    validator = _validator(controller, physical_context)
    oversized = dataclasses.replace(
        _response_context(physical_context), byte_length=4097
    )
    with pytest.raises(AuthorizationError, match="byte ceiling"):
        validator.validate_transfer(oversized)


def test_grant_for_another_request_is_refused(controller, physical_context):
    signer, public = controller
    other = dataclasses.replace(physical_context, request_sha256="e" * 64)
    with pytest.raises(AuthorizationError, match="does not answer the authorized request"):
        SignedResponseGrantValidator(
            grant_wire=_grant(signer, other),
            request_sha256=physical_context.request_sha256,
            controller_key_id=CONTROLLER_KEY_ID,
            controller_public_key=public,
            expected_source_node_id=physical_context.destination_node_id,
            expected_destination_node_id=physical_context.source_node_id,
        )


def test_grant_naming_another_responder_is_refused(controller, physical_context):
    signer, public = controller
    with pytest.raises(AuthorizationError, match="does not name this responder"):
        SignedResponseGrantValidator(
            grant_wire=_grant(signer, physical_context),
            request_sha256=physical_context.request_sha256,
            controller_key_id=CONTROLLER_KEY_ID,
            controller_public_key=public,
            expected_source_node_id="node:private-mesh:stranger",
            expected_destination_node_id=physical_context.source_node_id,
        )


def test_grant_signed_by_another_key_is_refused(physical_context):
    signer = Ed25519DocumentSigner(CONTROLLER_KEY_ID, Ed25519PrivateKey.generate())
    attacker_public = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    with pytest.raises(AuthorizationError, match="signature is invalid"):
        SignedResponseGrantValidator(
            grant_wire=_grant(signer, physical_context),
            request_sha256=physical_context.request_sha256,
            controller_key_id=CONTROLLER_KEY_ID,
            controller_public_key=attacker_public,
            expected_source_node_id=physical_context.destination_node_id,
            expected_destination_node_id=physical_context.source_node_id,
        )


def test_stale_fencing_token_is_refused(controller, physical_context):
    validator = _validator(controller, physical_context)
    stale = dataclasses.replace(
        _response_context(physical_context),
        fencing_token=physical_context.fencing_token + 1,
    )
    with pytest.raises(AuthorizationError, match="fencing token is stale"):
        validator.validate_transfer(stale)


def test_expired_grant_is_refused(controller, physical_context):
    signer, _ = controller
    issued = datetime.now(UTC) - timedelta(hours=2)
    grant_wire = _grant(signer, physical_context, now=issued, ttl_seconds=60)
    validator = _validator(controller, physical_context, grant_wire=grant_wire)
    with pytest.raises(AuthorizationError, match="expired"):
        validator.validate_transfer(_response_context(physical_context))


def test_a_grant_authorizes_only_one_response(controller, physical_context):
    validator = _validator(controller, physical_context)
    first = _response_context(physical_context, digest="a" * 64)
    validator.validate_transfer(first)
    # Re-validating the SAME object is fine (the transport revalidates frames).
    validator.validate_transfer(first)
    second = _response_context(physical_context, digest="b" * 64)
    with pytest.raises(AuthorizationError, match="already been used"):
        validator.validate_transfer(second)


def test_peer_identity_must_be_a_party_to_the_grant(controller, physical_context):
    """A node outside the exchange cannot ride it in either direction."""
    validator = _validator(controller, physical_context)
    response = _response_context(physical_context)
    impostor = AuthenticatedPeerIdentity(
        account_id=physical_context.account_id,
        node_id="node:private-mesh:stranger",
        sans=frozenset({"stranger.mesh"}),
        certificate_sha256="c" * 64,
        public_key_sha256="d" * 64,
    )
    with pytest.raises(AuthorizationError, match="not a party to the grant"):
        validator.validate_transfer(response, impostor)


def test_grant_endpoints_must_differ(controller, physical_context):
    signer, _ = controller
    payload = build_response_grant_payload(
        grant_id="grant:test:0002",
        account_id=physical_context.account_id,
        request_sha256=physical_context.request_sha256,
        lease_id=physical_context.lease_id,
        lease_sha256=physical_context.lease_sha256,
        fencing_token=physical_context.fencing_token,
        responder_node_id=physical_context.source_node_id,
        destination_node_id=physical_context.source_node_id,
        max_byte_length=4096,
        media_type="application/json",
        issued_at=datetime.now(UTC),
    )
    with pytest.raises(Exception, match="endpoints must differ"):
        sign_contract_document(ResponseGrant, payload, signer)


def test_adding_grants_did_not_change_existing_document_digests():
    """Grants are a SEPARATE document precisely so nothing else re-canonicalizes.

    If this ever fails, every signature and every recorded evidence digest in
    the repository has been invalidated.
    """
    from contracts.chal_vsource.v1.canonical import document_sha256
    from contracts.chal_vsource.v1.models import ChalRequest, LeaseDocument

    evidence = json.loads(EVIDENCE.read_text())
    context = evidence["transfer"]["transfer_context"]
    request = ChalRequest.model_validate_json(json.dumps(evidence["documents"]["request"]))
    lease = LeaseDocument.model_validate_json(
        json.dumps(evidence["documents"]["active_lease"])
    )
    assert document_sha256(request) == context["request_sha256"]
    assert document_sha256(lease) == context["lease_sha256"]
