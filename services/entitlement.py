"""Subscription entitlements: signed, short-lived, offline-verifiable.

A subscription business and a local-first product pull against each other. To
know whether a subscription is active you must ask someone; to keep the privacy
claim you must not send the customer's data anywhere. This module takes the
narrowest resolution available:

    The vendor signs a short-lived entitlement. The client verifies it OFFLINE
    against a pinned public key. Nothing about the customer's use is sent to
    verify it, and the entitlement itself contains no usage data.

The customer's machine contacts the vendor only to *renew* an entitlement, and
that contact discloses exactly one fact: this subscription is still being used.
That is a real disclosure and it must be stated in the privacy copy — it is not
"nothing leaves your machine", it is "nothing about your work leaves your
machine". Do not paper over the difference.

WHAT THIS IS NOT. This is not copy protection. The customer controls the
hardware; a determined user can patch the check out, and no technical measure
on their machine changes that. The purpose here is to make the *legitimate*
path clear and automatic for the overwhelming majority who simply want the
product to work — not to defeat an adversary who owns the computer. Anyone
selling this as DRM is misrepresenting it.

TWO PRODUCT RULES ENCODED HERE, deliberately:

  * **Grace, not a cliff.** An expired entitlement does not stop the product
    dead. A grace window covers travel, outages, and a failed card, because a
    local-first tool that bricks itself offline is a broken promise.
  * **Lapse never holds data hostage.** When an entitlement finally lapses the
    character stops running, but the customer's identity chain, history and
    exports remain fully readable. Their history is their data. A subscription
    buys the right to run a character, never the right to withhold what the
    customer's own machine recorded.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ENTITLEMENT_SCHEMA = "planetary.synthesus.entitlement.v1"

# Domain separation: an entitlement signature must never verify as any other
# document this project signs.
_SIGNING_DOMAIN = b"planetary.synthesus.entitlement.v1\x00"

# Short-lived by design: a stolen entitlement expires quickly, and a cancelled
# subscription stops renewing rather than needing revocation plumbing.
DEFAULT_TERM_DAYS = 7
MAX_TERM_DAYS = 31
# Offline tolerance after expiry, before the character stops running.
DEFAULT_GRACE_DAYS = 14
MAX_GRACE_DAYS = 90

ALL_CHARACTERS = "*"

_FIELDS = frozenset({
    "schema", "account_id", "subscription_id", "plan", "characters",
    "issued_at", "not_after", "grace_days", "signature",
})
_SIGNATURE_FIELDS = frozenset({"algorithm", "key_id", "value"})


class EntitlementError(ValueError):
    """An entitlement is missing, malformed, unsigned, or no longer valid."""


class EntitlementState:
    """Outcome of a check. `active` and `grace` both permit running."""

    ACTIVE = "active"
    GRACE = "grace"
    LAPSED = "lapsed"


def _canonical(payload: Any) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64url(value: str, *, expected: int) -> bytes:
    if not isinstance(value, str):
        raise EntitlementError("signature value must be a string")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise EntitlementError("signature value is not base64url") from exc
    if len(raw) != expected:
        raise EntitlementError("signature value has the wrong length")
    return raw


def _wire_time(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise EntitlementError(f"{field} must be a string timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise EntitlementError(f"{field} is not a valid timestamp") from exc


def _signing_bytes(entitlement: dict[str, Any]) -> bytes:
    unsigned = dict(entitlement)
    signature = dict(unsigned["signature"])
    signature["value"] = ""
    unsigned["signature"] = signature
    return _SIGNING_DOMAIN + _canonical(unsigned)


def issue_entitlement(
    *,
    signer: Any,
    account_id: str,
    subscription_id: str,
    plan: str,
    characters: list[str] | None = None,
    term_days: int = DEFAULT_TERM_DAYS,
    grace_days: int = DEFAULT_GRACE_DAYS,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Vendor side: sign an entitlement for one subscription.

    `characters` lists the character ids covered, or `["*"]` for a plan that
    includes everything. Deliberately carries no usage data — an entitlement
    should never become a channel for telemetry.
    """

    if not isinstance(account_id, str) or not account_id.strip():
        raise EntitlementError("account_id is required")
    if not isinstance(subscription_id, str) or not subscription_id.strip():
        raise EntitlementError("subscription_id is required")
    if not isinstance(plan, str) or not plan.strip():
        raise EntitlementError("plan is required")
    if not isinstance(term_days, int) or isinstance(term_days, bool) or not 1 <= term_days <= MAX_TERM_DAYS:
        raise EntitlementError(f"term_days must be between 1 and {MAX_TERM_DAYS}")
    if not isinstance(grace_days, int) or isinstance(grace_days, bool) or not 0 <= grace_days <= MAX_GRACE_DAYS:
        raise EntitlementError(f"grace_days must be between 0 and {MAX_GRACE_DAYS}")

    covered = list(characters or [ALL_CHARACTERS])
    if not covered or any(not isinstance(c, str) or not c.strip() for c in covered):
        raise EntitlementError("characters must be non-empty strings")

    issued = (now or (lambda: datetime.now(UTC)))().astimezone(UTC).replace(microsecond=0)
    entitlement: dict[str, Any] = {
        "schema": ENTITLEMENT_SCHEMA,
        "account_id": account_id.strip(),
        "subscription_id": subscription_id.strip(),
        "plan": plan.strip(),
        "characters": sorted(set(covered)),
        "issued_at": _wire_time(issued),
        "not_after": _wire_time(issued + timedelta(days=term_days)),
        "grace_days": grace_days,
        "signature": {"algorithm": "ed25519", "key_id": signer.key_id, "value": ""},
    }
    entitlement["signature"]["value"] = _b64url(signer.sign(_signing_bytes(entitlement)))
    return entitlement


def verify_entitlement(
    entitlement: Any,
    *,
    public_key: bytes,
    key_id: str | None = None,
    account_id: str | None = None,
    now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Client side: verify OFFLINE against the pinned vendor key.

    Returns `{state, expires_at, grace_until, characters, plan}`. Raises only
    when the entitlement is malformed or its signature does not verify — an
    expired entitlement is a *state*, not an exception, because the caller
    needs to distinguish grace from lapse.
    """

    if not isinstance(entitlement, dict) or set(entitlement) != _FIELDS:
        raise EntitlementError("entitlement has unexpected fields")
    if entitlement["schema"] != ENTITLEMENT_SCHEMA:
        raise EntitlementError("entitlement schema is unsupported")

    signature = entitlement["signature"]
    if not isinstance(signature, dict) or set(signature) != _SIGNATURE_FIELDS:
        raise EntitlementError("signature block has unexpected fields")
    if signature["algorithm"] != "ed25519":
        raise EntitlementError("signature algorithm is not ed25519")
    if key_id is not None and signature["key_id"] != key_id:
        raise EntitlementError("entitlement is not signed by the pinned vendor key")
    if account_id is not None and entitlement["account_id"] != account_id:
        raise EntitlementError("entitlement does not bind this account")

    grace_days = entitlement["grace_days"]
    if not isinstance(grace_days, int) or isinstance(grace_days, bool) or not 0 <= grace_days <= MAX_GRACE_DAYS:
        raise EntitlementError("grace_days is out of range")
    characters = entitlement["characters"]
    if not isinstance(characters, list) or not characters:
        raise EntitlementError("entitlement covers no characters")

    raw = _unb64url(signature["value"], expected=64)
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(raw, _signing_bytes(entitlement))
    except InvalidSignature as exc:
        raise EntitlementError("entitlement signature is invalid") from exc
    except ValueError as exc:
        raise EntitlementError("entitlement verification key is invalid") from exc

    issued_at = _parse_time(entitlement["issued_at"], "issued_at")
    not_after = _parse_time(entitlement["not_after"], "not_after")
    if not_after <= issued_at:
        raise EntitlementError("entitlement expires before it was issued")

    current = (now or (lambda: datetime.now(UTC)))().astimezone(UTC)
    grace_until = not_after + timedelta(days=grace_days)
    if current < issued_at - timedelta(minutes=5):
        # Clock skew tolerance only; a far-future entitlement is not honoured.
        raise EntitlementError("entitlement is not yet valid")

    if current < not_after:
        state = EntitlementState.ACTIVE
    elif current < grace_until:
        state = EntitlementState.GRACE
    else:
        state = EntitlementState.LAPSED

    return {
        "state": state,
        "plan": entitlement["plan"],
        "characters": list(characters),
        "account_id": entitlement["account_id"],
        "expires_at": _wire_time(not_after),
        "grace_until": _wire_time(grace_until),
    }


def may_run_character(verified: dict[str, Any], character_id: str) -> bool:
    """Whether a verified entitlement permits running this character now."""
    if verified.get("state") not in (EntitlementState.ACTIVE, EntitlementState.GRACE):
        return False
    covered = verified.get("characters") or []
    return ALL_CHARACTERS in covered or character_id in covered


def data_access_after_lapse() -> dict[str, Any]:
    """What a lapsed customer keeps. Encoded so it cannot drift into policy.

    A subscription buys the right to RUN a character. It never buys the right
    to withhold what the customer's own machine recorded. This is asserted by
    test, so a future change has to be deliberate.
    """
    return {
        "identity_chain_readable": True,
        "identity_chain_exportable": True,
        "conversation_history_readable": True,
        "local_files_readable": True,
        "character_may_run": False,
    }
