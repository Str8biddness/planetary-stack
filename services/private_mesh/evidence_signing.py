"""Detached node signatures over AIVM execution evidence.

Execution evidence (`aivm.execution.podman.ExecutionEvidence`) records what a
worker actually ran: the manifest digest, the lease it ran under, the immutable
image reference, the entrypoint, the input and output set digests, and host
capability facts such as `rootless` and `seccomp_enabled`. It has always been
produced. It has never been **signed**, which means a result carried no
cryptographic claim about its own provenance — the bytes were attributable to a
TLS peer, but the *statement about how they were produced* was not.

This module signs that statement with the node's existing contract identity —
the same ed25519 key that already signs resource inventories and is already
distributed in the mesh trust bundle. No new key, no new trust root.

The signature is DETACHED: the evidence bytes are hashed, and the envelope binds
that digest to an account, a node, and a length. Detaching keeps the evidence
document itself byte-stable (it is already content-addressed and referenced by
digest elsewhere) and keeps this module independent of the evidence schema.

HONEST SCOPE — what a valid signature does and does not mean:
  * It proves the named enrolled node produced this statement. It does NOT
    prove the statement is true: a compromised node holds its own key and can
    sign a false record. This is SELF-attestation, not hardware attestation.
    Every node in this project reports `attestation: unverified` today.
  * Its value is that everything around the output is pinned to owner-signed
    values, so a lie must be told in one narrow place, in a durable
    non-repudiable artifact naming the owner's own approved image and lease.
  * For deterministic profiles the owner can re-execute and compare, which
    turns this from attestation into verification.
See docs/design/PROPOSAL_BOUNDED_RESPONSE_SLOT.md.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SIGNED_EVIDENCE_SCHEMA = "planetary.private_mesh.signed_evidence.v1"

# Domain separation: a signature over this envelope must never verify as any
# other document type, even if the canonical bytes were to collide.
_SIGNING_DOMAIN = b"planetary.private_mesh.signed_evidence.v1\x00"

# Evidence is a bounded machine-generated record, not user content.
MAX_EVIDENCE_BYTES = 256 * 1024

_ENVELOPE_FIELDS = frozenset(
    {
        "schema",
        "account_id",
        "node_id",
        "evidence_sha256",
        "byte_length",
        "signature",
    }
)
_SIGNATURE_FIELDS = frozenset({"algorithm", "key_id", "value"})


class EvidenceSignatureError(ValueError):
    """Evidence could not be signed, or a signature failed verification."""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str, *, expected_bytes: int) -> bytes:
    if not isinstance(value, str):
        raise EvidenceSignatureError("signature value must be a string")
    padding = "=" * (-len(value) % 4)
    try:
        raw = base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        raise EvidenceSignatureError("signature value is not base64url") from exc
    if len(raw) != expected_bytes:
        raise EvidenceSignatureError("signature value has the wrong length")
    return raw


def _signing_bytes(envelope: dict[str, Any]) -> bytes:
    """Canonical bytes signed: the envelope with the signature value zeroed."""

    unsigned = dict(envelope)
    signature = dict(unsigned["signature"])
    signature["value"] = ""
    unsigned["signature"] = signature
    canonical = json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return _SIGNING_DOMAIN + canonical


def sign_evidence(
    evidence_bytes: bytes,
    *,
    account_id: str,
    node_id: str,
    signer: Any,
) -> dict[str, Any]:
    """Return a detached signature envelope over `evidence_bytes`.

    `signer` is the node's contract identity signer (`Ed25519DocumentSigner`),
    the same one that signs resource inventories.
    """

    if not isinstance(evidence_bytes, (bytes, bytearray)):
        raise EvidenceSignatureError("evidence must be bytes")
    evidence_bytes = bytes(evidence_bytes)
    if not evidence_bytes:
        raise EvidenceSignatureError("evidence is empty")
    if len(evidence_bytes) > MAX_EVIDENCE_BYTES:
        raise EvidenceSignatureError("evidence exceeds the bounded size")
    envelope: dict[str, Any] = {
        "schema": SIGNED_EVIDENCE_SCHEMA,
        "account_id": account_id,
        "node_id": node_id,
        "evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
        "byte_length": len(evidence_bytes),
        "signature": {
            "algorithm": "ed25519",
            "key_id": signer.key_id,
            "value": "",
        },
    }
    envelope["signature"]["value"] = _b64url_encode(signer.sign(_signing_bytes(envelope)))
    return envelope


def verify_evidence_signature(
    envelope: Any,
    evidence_bytes: bytes,
    *,
    account_id: str,
    node_id: str,
    public_key: bytes,
    key_id: str | None = None,
) -> None:
    """Fail closed unless `envelope` is a valid signature by `node_id`.

    Raises `EvidenceSignatureError` on any mismatch. Returns None on success.
    """

    if not isinstance(envelope, dict) or set(envelope) != _ENVELOPE_FIELDS:
        raise EvidenceSignatureError("signed evidence envelope has unexpected fields")
    if envelope["schema"] != SIGNED_EVIDENCE_SCHEMA:
        raise EvidenceSignatureError("signed evidence schema is unsupported")
    if envelope["account_id"] != account_id:
        raise EvidenceSignatureError("signed evidence does not bind this account")
    if envelope["node_id"] != node_id:
        raise EvidenceSignatureError("signed evidence does not bind the expected node")
    signature = envelope["signature"]
    if not isinstance(signature, dict) or set(signature) != _SIGNATURE_FIELDS:
        raise EvidenceSignatureError("signature block has unexpected fields")
    if signature["algorithm"] != "ed25519":
        raise EvidenceSignatureError("signature algorithm is not ed25519")
    if key_id is not None and signature["key_id"] != key_id:
        raise EvidenceSignatureError("signature key id is not the enrolled node key")

    if not isinstance(evidence_bytes, (bytes, bytearray)):
        raise EvidenceSignatureError("evidence must be bytes")
    evidence_bytes = bytes(evidence_bytes)
    if len(evidence_bytes) > MAX_EVIDENCE_BYTES:
        raise EvidenceSignatureError("evidence exceeds the bounded size")
    byte_length = envelope["byte_length"]
    if not isinstance(byte_length, int) or isinstance(byte_length, bool):
        raise EvidenceSignatureError("byte_length must be an integer")
    if byte_length != len(evidence_bytes):
        raise EvidenceSignatureError("evidence length does not match the envelope")
    if envelope["evidence_sha256"] != hashlib.sha256(evidence_bytes).hexdigest():
        raise EvidenceSignatureError("evidence digest does not match the envelope")

    raw_signature = _b64url_decode(signature["value"], expected_bytes=64)
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            raw_signature, _signing_bytes(envelope)
        )
    except InvalidSignature as exc:
        raise EvidenceSignatureError("evidence signature is invalid") from exc
    except ValueError as exc:
        raise EvidenceSignatureError("evidence signing key is invalid") from exc
