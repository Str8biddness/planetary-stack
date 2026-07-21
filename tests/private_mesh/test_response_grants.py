"""Controller-side grant issuance.

The interesting cases are the refusals. A controller that signs an
over-permissive grant has created durable authority it cannot take back, so
every bound is asserted here, and the issuer is expected to refuse rather than
silently narrow what it was asked for.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.response_grants import (
    MAX_GRANT_BYTES,
    MAX_GRANT_TTL_SECONDS,
    ResponseGrantError,
    build_grant_issuer,
)
from services.unisync.errors import AuthorizationError
from services.unisync.mesh_grant import SignedResponseGrantValidator, parse_signed_grant
from services.vsource import Ed25519DocumentSigner

ACCOUNT = "account:private-mesh:home"
KEY_ID = "key:controller:desktop"
RESPONDER = "node:private-mesh:worker"
DESTINATION = "node:desktop:001"


@pytest.fixture
def controller():
    private_key = Ed25519PrivateKey.generate()
    return (
        Ed25519DocumentSigner(KEY_ID, private_key),
        private_key.public_key().public_bytes_raw(),
    )


@pytest.fixture
def issue(controller):
    signer, _ = controller
    return build_grant_issuer(signer=signer, account_id=ACCOUNT)


def _args(**overrides):
    args = dict(
        grant_id="grant:desktop:0001",
        request_sha256="a" * 64,
        lease_id="lease:0001",
        lease_sha256="b" * 64,
        fencing_token=3,
        responder_node_id=RESPONDER,
        destination_node_id=DESTINATION,
        max_byte_length=4096,
        media_type="application/json",
    )
    args.update(overrides)
    return args


def test_issued_grant_verifies_against_the_controller_key(controller, issue):
    _, public = controller
    wire = issue(**_args())
    grant = parse_signed_grant(
        wire, controller_key_id=KEY_ID, controller_public_key=public
    )
    assert grant.account_id == ACCOUNT
    assert grant.responder_node_id == RESPONDER
    assert grant.destination_node_id == DESTINATION
    assert grant.max_byte_length == 4096
    assert grant.media_type == "application/json"


def test_issued_grant_is_accepted_by_the_validator(controller, issue):
    """Issuer and verifier agree — the two halves actually fit."""
    _, public = controller
    wire = issue(**_args())
    SignedResponseGrantValidator(
        grant_wire=wire,
        request_sha256="a" * 64,
        controller_key_id=KEY_ID,
        controller_public_key=public,
        expected_source_node_id=RESPONDER,
        expected_destination_node_id=DESTINATION,
    )


def test_another_controllers_key_does_not_verify(issue):
    stranger = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    with pytest.raises(AuthorizationError, match="signature is invalid"):
        parse_signed_grant(
            issue(**_args()), controller_key_id=KEY_ID, controller_public_key=stranger
        )


def test_protocol_ceiling_is_refused_not_clamped(issue):
    """Asking for more than the protocol allows is an error, not a nudge."""
    with pytest.raises(ResponseGrantError, match="protocol ceiling"):
        issue(**_args(max_byte_length=MAX_GRANT_BYTES + 1))
    # At the ceiling exactly is fine.
    assert issue(**_args(max_byte_length=MAX_GRANT_BYTES))["max_byte_length"] == (
        MAX_GRANT_BYTES
    )


def test_wildcard_and_list_media_types_are_refused(issue):
    for media_type in ("*/*", "application/*", "application/json,text/plain"):
        with pytest.raises(ResponseGrantError, match="exact"):
            issue(**_args(media_type=media_type))


def test_self_addressed_grant_is_refused(issue):
    with pytest.raises(ResponseGrantError, match="response to itself"):
        issue(**_args(responder_node_id=RESPONDER, destination_node_id=RESPONDER))


def test_ttl_bounds_are_enforced(issue):
    with pytest.raises(ResponseGrantError, match="ttl_seconds"):
        issue(**_args(ttl_seconds=MAX_GRANT_TTL_SECONDS + 1))
    with pytest.raises(ResponseGrantError, match="ttl_seconds"):
        issue(**_args(ttl_seconds=0))


def test_nonsense_sizes_and_tokens_are_refused(issue):
    with pytest.raises(ResponseGrantError, match="max_byte_length"):
        issue(**_args(max_byte_length=0))
    with pytest.raises(ResponseGrantError, match="max_byte_length must be an integer"):
        issue(**_args(max_byte_length=True))
    with pytest.raises(ResponseGrantError, match="fencing_token"):
        issue(**_args(fencing_token=0))


def test_issuer_uses_the_injected_clock(controller):
    signer, public = controller
    fixed = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)
    issue = build_grant_issuer(signer=signer, account_id=ACCOUNT, clock=lambda: fixed)
    grant = parse_signed_grant(
        issue(**_args()), controller_key_id=KEY_ID, controller_public_key=public
    )
    assert grant.issued_at == fixed


def test_pipeline_exposes_a_grant_issuer(tmp_path, monkeypatch):
    """The desktop controller mints grants for jobs it placed."""
    # Importing this first puts the runtime packages on sys.path.
    from tests.private_mesh.test_remote_pipeline import _DeliveringCarrier, _clock, _config

    import aivm.execution as _aivm

    from services.remote_pipeline import build_remote_pipeline
    from tests.private_mesh.test_execution_wiring import FakeModelRunner

    class _Runner(_aivm.PodmanExecutor):
        def __init__(self, policy, *, authority_verifier, runner=None, **kw):
            super().__init__(
                policy, authority_verifier=authority_verifier, runner=FakeModelRunner(), **kw
            )

    monkeypatch.setattr(_aivm, "PodmanExecutor", _Runner)
    carrier = _DeliveringCarrier()
    pipeline = build_remote_pipeline(
        _config(tmp_path), state_dir=tmp_path / "authority", clock=_clock, carrier=carrier
    )
    assert pipeline is not None
    assert callable(pipeline.issue_response_grant)

    wire = pipeline.issue_response_grant(
        grant_id="grant:desktop:live",
        request_sha256="c" * 64,
        lease_id="lease:live",
        lease_sha256="d" * 64,
        fencing_token=1,
        responder_node_id="node:owner:a",
        destination_node_id="node:desktop:001",
        max_byte_length=4096,
        media_type="application/json",
    )
    assert wire["schema"] == "planetary.chal.response_grant.v1"
    # Signed by the pipeline's persistent controller identity, verifiable with
    # the public half of the key stored on disk.
    controller_key = (tmp_path / "authority" / "controller.key").read_bytes()
    public = Ed25519PrivateKey.from_private_bytes(controller_key).public_key()
    parse_signed_grant(
        wire,
        controller_key_id=wire["signature"]["key_id"],
        controller_public_key=public.public_bytes_raw(),
    )
