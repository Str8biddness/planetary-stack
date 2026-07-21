"""Detached node signatures over execution evidence.

Real ed25519 keys, real signatures. These tests exist to pin the fail-closed
behaviour: a signature that does not bind this account, this node, these exact
evidence bytes, and this key must not verify.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.private_mesh.evidence_signing import (
    MAX_EVIDENCE_BYTES,
    SIGNED_EVIDENCE_SCHEMA,
    EvidenceSignatureError,
    sign_evidence,
    verify_evidence_signature,
)
from services.vsource import Ed25519DocumentSigner

ACCOUNT = "account:private-mesh:home"
NODE = "node:private-mesh:worker"
KEY_ID = "key:unisync-mesh:abcdef0123456789abcd"
EVIDENCE = json.dumps(
    {
        "account_id": ACCOUNT,
        "node_id": NODE,
        "immutable_image_ref": "localhost/aivm-text-classify@sha256:" + "4" * 64,
        "entrypoint_id": "aivm.model.text-classify.v1",
        "output_set_sha256": "a" * 64,
        "host": {"rootless": True, "seccomp_enabled": True},
    },
    sort_keys=True,
    separators=(",", ":"),
).encode("ascii")


@pytest.fixture
def keypair():
    private_key = Ed25519PrivateKey.generate()
    signer = Ed25519DocumentSigner(KEY_ID, private_key)
    public = private_key.public_key().public_bytes_raw()
    return signer, public


def _verify(envelope, evidence, public, **overrides):
    kwargs = dict(account_id=ACCOUNT, node_id=NODE, public_key=public)
    kwargs.update(overrides)
    verify_evidence_signature(envelope, evidence, **kwargs)


def test_signed_evidence_verifies(keypair):
    signer, public = keypair
    envelope = sign_evidence(EVIDENCE, account_id=ACCOUNT, node_id=NODE, signer=signer)

    assert envelope["schema"] == SIGNED_EVIDENCE_SCHEMA
    assert envelope["evidence_sha256"] == hashlib.sha256(EVIDENCE).hexdigest()
    assert envelope["byte_length"] == len(EVIDENCE)
    assert envelope["signature"]["algorithm"] == "ed25519"
    assert envelope["signature"]["key_id"] == KEY_ID

    _verify(envelope, EVIDENCE, public)
    _verify(envelope, EVIDENCE, public, key_id=KEY_ID)


def test_tampered_evidence_bytes_fail(keypair):
    signer, public = keypair
    envelope = sign_evidence(EVIDENCE, account_id=ACCOUNT, node_id=NODE, signer=signer)
    tampered = EVIDENCE.replace(b'"rootless":true', b'"rootless":fals')
    assert tampered != EVIDENCE
    with pytest.raises(EvidenceSignatureError, match="length|digest"):
        _verify(envelope, tampered, public)


def test_swapped_digest_in_envelope_fails(keypair):
    """Rewriting the digest to match tampered bytes breaks the signature."""
    signer, public = keypair
    envelope = sign_evidence(EVIDENCE, account_id=ACCOUNT, node_id=NODE, signer=signer)
    forged_evidence = EVIDENCE + b" "
    envelope["evidence_sha256"] = hashlib.sha256(forged_evidence).hexdigest()
    envelope["byte_length"] = len(forged_evidence)
    with pytest.raises(EvidenceSignatureError, match="signature is invalid"):
        _verify(envelope, forged_evidence, public)


def test_another_nodes_key_fails(keypair):
    signer, _ = keypair
    envelope = sign_evidence(EVIDENCE, account_id=ACCOUNT, node_id=NODE, signer=signer)
    attacker_public = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    with pytest.raises(EvidenceSignatureError, match="signature is invalid"):
        _verify(envelope, EVIDENCE, attacker_public)


def test_wrong_node_or_account_binding_fails(keypair):
    signer, public = keypair
    envelope = sign_evidence(EVIDENCE, account_id=ACCOUNT, node_id=NODE, signer=signer)
    with pytest.raises(EvidenceSignatureError, match="expected node"):
        _verify(envelope, EVIDENCE, public, node_id="node:private-mesh:other")
    with pytest.raises(EvidenceSignatureError, match="this account"):
        _verify(envelope, EVIDENCE, public, account_id="account:private-mesh:other")


def test_unexpected_key_id_fails(keypair):
    signer, public = keypair
    envelope = sign_evidence(EVIDENCE, account_id=ACCOUNT, node_id=NODE, signer=signer)
    with pytest.raises(EvidenceSignatureError, match="enrolled node key"):
        _verify(envelope, EVIDENCE, public, key_id="key:unisync-mesh:00000000000000000000")


def test_envelope_shape_is_pinned(keypair):
    signer, public = keypair
    envelope = sign_evidence(EVIDENCE, account_id=ACCOUNT, node_id=NODE, signer=signer)

    extra = dict(envelope, extra_field="x")
    with pytest.raises(EvidenceSignatureError, match="unexpected fields"):
        _verify(extra, EVIDENCE, public)

    missing = dict(envelope)
    missing.pop("byte_length")
    with pytest.raises(EvidenceSignatureError, match="unexpected fields"):
        _verify(missing, EVIDENCE, public)

    wrong_schema = dict(envelope, schema="planetary.private_mesh.something_else.v1")
    with pytest.raises(EvidenceSignatureError, match="schema is unsupported"):
        _verify(wrong_schema, EVIDENCE, public)

    bad_alg = dict(envelope, signature=dict(envelope["signature"], algorithm="rsa"))
    with pytest.raises(EvidenceSignatureError, match="not ed25519"):
        _verify(bad_alg, EVIDENCE, public)


def test_empty_and_oversized_evidence_refuse_to_sign(keypair):
    signer, _ = keypair
    with pytest.raises(EvidenceSignatureError, match="empty"):
        sign_evidence(b"", account_id=ACCOUNT, node_id=NODE, signer=signer)
    with pytest.raises(EvidenceSignatureError, match="bounded size"):
        sign_evidence(
            b"x" * (MAX_EVIDENCE_BYTES + 1),
            account_id=ACCOUNT,
            node_id=NODE,
            signer=signer,
        )


def test_signature_does_not_verify_outside_its_domain(keypair):
    """Domain separation: the raw canonical JSON is not what was signed."""
    import base64

    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    signer, public = keypair
    envelope = sign_evidence(EVIDENCE, account_id=ACCOUNT, node_id=NODE, signer=signer)
    unsigned = dict(envelope, signature=dict(envelope["signature"], value=""))
    undomained = json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    raw = base64.urlsafe_b64decode(
        envelope["signature"]["value"] + "=" * (-len(envelope["signature"]["value"]) % 4)
    )
    with pytest.raises(InvalidSignature):
        Ed25519PublicKey.from_public_bytes(public).verify(raw, undomained)
