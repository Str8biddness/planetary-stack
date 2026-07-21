"""Controller-side issuance of response grants.

`services/unisync/mesh_grant.py` verifies a grant. This mints one. In a
same-account private mesh the desktop controller is the trust root, so the
owner's controller authorizes its own devices to answer it — there is no
external issuer to ask.

A grant is minted only for a placement that already exists: the caller must
supply the forward lease it was issued under, and that lease's digest and
fencing token travel into the grant. Nothing here can invent authority for a
job that was never placed.

PROTOCOL CEILING. `MAX_GRANT_BYTES` bounds every grant regardless of what a
caller asks for. A request may ask for less; it can never ask for more. The
return path is the one direction where the owner has not pre-approved the exact
bytes, so the ceiling is the containment: it bounds how much can ever travel
home under one authorization, and keeps a compromised-but-enrolled node from
turning the answer channel into a bulk egress route.

HONEST SCOPE, against the product claim that *your data stays on your own
machines*: a grant keeps a computed answer inside the mesh — named responder,
named destination, authenticated encrypted transport, one use, bounded size. It
does NOT make a node honest, and does not try to.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from contracts.chal_vsource.v1.models import ResponseGrant
from services.unisync.mesh_grant import build_response_grant_payload
from services.vsource import sign_contract_document

# Hard protocol ceiling for one response, independent of any caller's request.
MAX_GRANT_BYTES = 1 * 1024 * 1024
# A grant must not outlive the placement it answers by any meaningful margin.
MAX_GRANT_TTL_SECONDS = 600

_MEDIA_TYPE_MAX = 128


class ResponseGrantError(ValueError):
    """A grant was requested that the controller will not sign."""


def build_grant_issuer(
    *,
    signer: Any,
    account_id: str,
    clock: Callable[[], datetime] | None = None,
) -> Callable[..., dict[str, Any]]:
    """Return a callable that mints controller-signed response grants.

    The returned callable raises `ResponseGrantError` rather than signing
    anything it considers out of bounds — an unsigned refusal is always
    preferable to a signed over-permission.
    """

    now = clock or (lambda: datetime.now(UTC))

    def issue(
        *,
        grant_id: str,
        request_sha256: str,
        lease_id: str,
        lease_sha256: str,
        fencing_token: int,
        responder_node_id: str,
        destination_node_id: str,
        max_byte_length: int,
        media_type: str,
        ttl_seconds: int = 300,
    ) -> dict[str, Any]:
        if responder_node_id == destination_node_id:
            raise ResponseGrantError("a node cannot be granted a response to itself")
        if not isinstance(max_byte_length, int) or isinstance(max_byte_length, bool):
            raise ResponseGrantError("max_byte_length must be an integer")
        if max_byte_length < 1:
            raise ResponseGrantError("max_byte_length must be positive")
        if max_byte_length > MAX_GRANT_BYTES:
            # Refuse rather than silently clamp: a caller that asked for more
            # than the protocol allows has a bug or a bad assumption, and
            # quietly narrowing it would hide that.
            raise ResponseGrantError(
                f"max_byte_length exceeds the protocol ceiling of {MAX_GRANT_BYTES}"
            )
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool):
            raise ResponseGrantError("ttl_seconds must be an integer")
        if not 1 <= ttl_seconds <= MAX_GRANT_TTL_SECONDS:
            raise ResponseGrantError(
                f"ttl_seconds must be between 1 and {MAX_GRANT_TTL_SECONDS}"
            )
        if not isinstance(media_type, str) or not 3 <= len(media_type) <= _MEDIA_TYPE_MAX:
            raise ResponseGrantError("media_type is required and must be an exact type")
        if "*" in media_type or "," in media_type:
            raise ResponseGrantError("media_type must be exact: no wildcards, no lists")
        if not isinstance(fencing_token, int) or isinstance(fencing_token, bool):
            raise ResponseGrantError("fencing_token must be an integer")
        if fencing_token < 1:
            raise ResponseGrantError("fencing_token must be positive")

        payload = build_response_grant_payload(
            grant_id=grant_id,
            account_id=account_id,
            request_sha256=request_sha256,
            lease_id=lease_id,
            lease_sha256=lease_sha256,
            fencing_token=fencing_token,
            responder_node_id=responder_node_id,
            destination_node_id=destination_node_id,
            max_byte_length=max_byte_length,
            media_type=media_type,
            issued_at=now(),
            ttl_seconds=ttl_seconds,
        )
        try:
            grant = sign_contract_document(ResponseGrant, payload, signer)
        except Exception as exc:
            # The contract model enforces its own bounds; surface a refusal
            # rather than a half-built document.
            raise ResponseGrantError(f"controller refused to sign the grant: {exc}") from exc
        return grant.model_dump(mode="json", by_alias=True)

    return issue
