"""Subscription entitlements.

Two classes of test matter here. The security ones — a forged or altered
entitlement must not verify. And the *product* ones — grace must not be a
cliff, and a lapse must never hold the customer's own data hostage. The second
group exists so those promises cannot quietly erode into policy later.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.entitlement import (
    ALL_CHARACTERS,
    MAX_TERM_DAYS,
    EntitlementError,
    EntitlementState,
    data_access_after_lapse,
    issue_entitlement,
    may_run_character,
    verify_entitlement,
)
from services.vsource import Ed25519DocumentSigner

KEY_ID = "key:vendor:synthesus:001"
ACCOUNT = "account:customer:0042"
T0 = datetime(2026, 7, 21, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def vendor():
    private_key = Ed25519PrivateKey.generate()
    return (
        Ed25519DocumentSigner(KEY_ID, private_key),
        private_key.public_key().public_bytes_raw(),
    )


def _issue(vendor, **overrides):
    signer, _ = vendor
    args = dict(
        signer=signer,
        account_id=ACCOUNT,
        subscription_id="sub_123",
        plan="personal",
        characters=["synthesus"],
        term_days=7,
        grace_days=14,
        now=lambda: T0,
    )
    args.update(overrides)
    return issue_entitlement(**args)


def _verify(vendor, entitlement, at=T0, **kw):
    _, public = vendor
    return verify_entitlement(
        entitlement, public_key=public, key_id=KEY_ID, now=lambda: at, **kw
    )


# ---------------------------------------------------------------- security


def test_valid_entitlement_verifies_offline(vendor):
    """No network call is involved in checking — only the pinned key."""
    verified = _verify(vendor, _issue(vendor))
    assert verified["state"] == EntitlementState.ACTIVE
    assert verified["plan"] == "personal"
    assert may_run_character(verified, "synthesus") is True


def test_forged_signature_is_refused(vendor):
    entitlement = _issue(vendor)
    attacker = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    with pytest.raises(EntitlementError, match="signature is invalid"):
        verify_entitlement(entitlement, public_key=attacker, key_id=KEY_ID, now=lambda: T0)


def test_extending_the_term_by_hand_is_refused(vendor):
    """The obvious attack: edit not_after and keep using it."""
    entitlement = _issue(vendor)
    entitlement["not_after"] = "2099-01-01T00:00:00Z"
    with pytest.raises(EntitlementError, match="signature is invalid"):
        _verify(vendor, entitlement)


def test_adding_characters_by_hand_is_refused(vendor):
    entitlement = _issue(vendor)
    entitlement["characters"] = [ALL_CHARACTERS]
    with pytest.raises(EntitlementError, match="signature is invalid"):
        _verify(vendor, entitlement)


def test_another_accounts_entitlement_is_refused(vendor):
    """Sharing one subscription across accounts does not work."""
    entitlement = _issue(vendor)
    with pytest.raises(EntitlementError, match="does not bind this account"):
        _verify(vendor, entitlement, account_id="account:customer:9999")


def test_unexpected_fields_are_refused(vendor):
    entitlement = dict(_issue(vendor), telemetry={"prompts": 412})
    with pytest.raises(EntitlementError, match="unexpected fields"):
        _verify(vendor, entitlement)


def test_absurd_terms_are_refused_at_issue(vendor):
    with pytest.raises(EntitlementError, match="term_days"):
        _issue(vendor, term_days=MAX_TERM_DAYS + 1)
    with pytest.raises(EntitlementError, match="grace_days"):
        _issue(vendor, grace_days=9999)


# ----------------------------------------------------------------- product


def test_grace_is_not_a_cliff(vendor):
    """A local-first tool that bricks itself offline is a broken promise."""
    entitlement = _issue(vendor, term_days=7, grace_days=14)

    during = _verify(vendor, entitlement, at=T0 + timedelta(days=3))
    assert during["state"] == EntitlementState.ACTIVE

    just_expired = _verify(vendor, entitlement, at=T0 + timedelta(days=8))
    assert just_expired["state"] == EntitlementState.GRACE
    assert may_run_character(just_expired, "synthesus") is True, (
        "an expired-but-in-grace subscription must keep working"
    )

    long_gone = _verify(vendor, entitlement, at=T0 + timedelta(days=40))
    assert long_gone["state"] == EntitlementState.LAPSED
    assert may_run_character(long_gone, "synthesus") is False


def test_lapse_never_holds_the_customers_data_hostage():
    """A subscription buys the right to RUN a character, never the right to
    withhold what the customer's own machine recorded."""
    access = data_access_after_lapse()
    assert access["identity_chain_readable"] is True
    assert access["identity_chain_exportable"] is True
    assert access["conversation_history_readable"] is True
    assert access["local_files_readable"] is True
    # The only thing a lapse stops:
    assert access["character_may_run"] is False


def test_entitlement_carries_no_usage_data(vendor):
    """An entitlement must never become a telemetry channel."""
    entitlement = _issue(vendor)
    # Check field NAMES, not a substring scan of the whole blob — "count"
    # appears inside "account_id" and would false-positive.
    banned = ("prompt", "message", "usage", "telemetry", "history", "device", "ip_")
    for field in entitlement:
        assert not any(token in field.lower() for token in banned), (
            f"entitlement field looks like telemetry: {field}"
        )
    assert set(entitlement) == {
        "schema", "account_id", "subscription_id", "plan", "characters",
        "issued_at", "not_after", "grace_days", "signature",
    }


def test_plan_scoping_limits_which_characters_run(vendor):
    limited = _verify(vendor, _issue(vendor, characters=["synthesus"]))
    assert may_run_character(limited, "synthesus") is True
    assert may_run_character(limited, "atlas") is False

    everything = _verify(vendor, _issue(vendor, characters=[ALL_CHARACTERS], plan="studio"))
    assert may_run_character(everything, "atlas") is True


def test_future_dated_entitlement_is_refused(vendor):
    """Clock-rolling forward to mint headroom does not help."""
    entitlement = _issue(vendor, now=lambda: T0 + timedelta(days=30))
    with pytest.raises(EntitlementError, match="not yet valid"):
        _verify(vendor, entitlement, at=T0)


def test_short_term_limits_the_value_of_a_stolen_entitlement(vendor):
    """Leaked entitlements expire on their own rather than needing revocation."""
    entitlement = _issue(vendor, term_days=7, grace_days=0)
    assert _verify(vendor, entitlement, at=T0 + timedelta(days=6))["state"] == (
        EntitlementState.ACTIVE
    )
    assert _verify(vendor, entitlement, at=T0 + timedelta(days=8))["state"] == (
        EntitlementState.LAPSED
    )
