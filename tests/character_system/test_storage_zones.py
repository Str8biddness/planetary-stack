"""Storage zones.

Every test here is a refusal. The zone model exists to make two failures
impossible: personal content reaching a public transport, and a worker's output
becoming grounding without the owner. Both would be silent in production — a
misrouted sync does not error, and a self-promoted belief looks exactly like a
correct one.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime

import pytest

from services.storage_zones import (
    PERMITTED_MOVES,
    ZONE_RULES,
    PromotionLedger,
    Transport,
    Zone,
    ZoneViolation,
    promote_to_grounding,
    require_move_permitted,
    require_transport,
    require_worker_may_write,
    zone_of,
)

OWNER = "dakin"
DIGEST = "a" * 64


@pytest.fixture
def roots(tmp_path):
    mapping = {
        Zone.NODE: tmp_path / "node",
        Zone.OUTPUT: tmp_path / "output",
        Zone.GROUNDING: tmp_path / "grounding",
        Zone.EXTERNAL: tmp_path / "external",
    }
    for path in mapping.values():
        path.mkdir(parents=True)
    return mapping


@pytest.fixture
def ledger(tmp_path):
    return PromotionLedger(tmp_path / "state" / "promotions.jsonl")


# --------------------------------------------------- the transport boundary


def test_grounding_may_never_travel_over_a_public_transport():
    """The failure this whole module exists to prevent.

    A misrouted sync does not raise in production — it silently uploads
    someone's private files to a third party.
    """
    with pytest.raises(ZoneViolation, match="never travel over a public transport"):
        require_transport(Zone.GROUNDING, Transport.PUBLIC)


def test_output_may_not_be_published_by_transport_alone():
    with pytest.raises(ZoneViolation, match="never travel over a public transport"):
        require_transport(Zone.OUTPUT, Transport.PUBLIC)


def test_node_state_never_leaves_the_device():
    with pytest.raises(ZoneViolation, match="never leaves its device"):
        require_transport(Zone.NODE, Transport.MESH)
    with pytest.raises(ZoneViolation, match="never travel over a public transport"):
        require_transport(Zone.NODE, Transport.PUBLIC)


def test_the_permitted_paths_are_permitted():
    require_transport(Zone.OUTPUT, Transport.MESH)
    require_transport(Zone.GROUNDING, Transport.MESH)
    require_transport(Zone.EXTERNAL, Transport.PUBLIC)


def test_only_external_is_marked_as_leaving_the_home():
    leaves = {zone for zone, rules in ZONE_RULES.items() if rules.leaves_home}
    assert leaves == {Zone.EXTERNAL}, (
        "exactly one zone may leave the home; changing this changes the product's claim"
    )


# ------------------------------------------------------- the worker boundary


def test_a_worker_cannot_write_directly_into_grounding():
    """Workers produce output. Only the owner turns output into belief."""
    with pytest.raises(ZoneViolation, match="may not write to the grounding zone"):
        require_worker_may_write(Zone.GROUNDING)


def test_a_worker_cannot_write_into_external():
    with pytest.raises(ZoneViolation, match="may not write to the external zone"):
        require_worker_may_write(Zone.EXTERNAL)


def test_a_worker_may_write_output_and_node_state():
    require_worker_may_write(Zone.OUTPUT)
    require_worker_may_write(Zone.NODE)


# --------------------------------------------------------------- moves


def test_moves_are_an_allowlist_not_a_denylist():
    """The dangerous direction is the one nobody thought of."""
    require_move_permitted(Zone.OUTPUT, Zone.GROUNDING)
    require_move_permitted(Zone.OUTPUT, Zone.EXTERNAL)
    require_move_permitted(Zone.NODE, Zone.OUTPUT)

    for forbidden in (
        (Zone.GROUNDING, Zone.EXTERNAL),   # personal data out of the home
        (Zone.GROUNDING, Zone.OUTPUT),
        (Zone.EXTERNAL, Zone.GROUNDING),   # untrusted external content believed
        (Zone.NODE, Zone.EXTERNAL),
        (Zone.EXTERNAL, Zone.NODE),
    ):
        with pytest.raises(ZoneViolation, match="is not permitted"):
            require_move_permitted(*forbidden)


def test_grounding_to_external_is_the_move_that_must_never_exist():
    assert (Zone.GROUNDING, Zone.EXTERNAL) not in PERMITTED_MOVES


# ----------------------------------------------------------- the gate


def test_automated_promotion_is_refused(ledger):
    """No flag bypasses this. A system that can promote its own output into its
    own beliefs will eventually believe what a poisoned document told it to."""
    with pytest.raises(ZoneViolation, match="automated promotion is refused"):
        promote_to_grounding(
            digest=DIGEST, ledger=ledger, approved_by=None, reason="looks fine"
        )
    assert ledger.was_approved(DIGEST) is False


def test_owner_approval_promotes_and_is_recorded(ledger):
    entry = promote_to_grounding(
        digest=DIGEST,
        ledger=ledger,
        approved_by=OWNER,
        reason="checked the source myself",
        produced_by_node="node:private-mesh:dakin-ms-7c95",
        evidence_status="verified",
    )
    assert entry["approved_by"] == OWNER
    assert entry["produced_by_node"] == "node:private-mesh:dakin-ms-7c95"
    assert entry["evidence_status"] == "verified"
    assert ledger.was_approved(DIGEST) is True


def test_unapproved_content_is_not_grounding(ledger):
    promote_to_grounding(
        digest=DIGEST, ledger=ledger, approved_by=OWNER, reason="ok"
    )
    assert ledger.was_approved("b" * 64) is False


def test_the_ledger_survives_reopening(tmp_path):
    path = tmp_path / "state" / "promotions.jsonl"
    promote_to_grounding(
        digest=DIGEST, ledger=PromotionLedger(path), approved_by=OWNER, reason="ok"
    )
    assert PromotionLedger(path).was_approved(DIGEST) is True


def test_the_ledger_is_owner_only(ledger):
    promote_to_grounding(digest=DIGEST, ledger=ledger, approved_by=OWNER, reason="ok")
    assert stat.S_IMODE(os.lstat(ledger.path).st_mode) == 0o600


def test_approval_records_who_and_why(ledger):
    with pytest.raises(ZoneViolation, match="who approved"):
        promote_to_grounding(digest=DIGEST, ledger=ledger, approved_by="  ", reason="x")
    with pytest.raises(ZoneViolation, match="reason is required"):
        promote_to_grounding(
            digest=DIGEST, ledger=ledger, approved_by=OWNER, reason="x" * 5000
        )


def test_ledger_keeps_provenance_for_after_the_fact_questions(ledger):
    """When something turns out to be wrong, the useful question is which node
    produced it and whether its evidence verified."""
    promote_to_grounding(
        digest=DIGEST, ledger=ledger, approved_by=OWNER, reason="ok",
        produced_by_node="node:phone:pixel", evidence_status="unsigned",
    )
    record = ledger.approvals()[0]
    assert record["produced_by_node"] == "node:phone:pixel"
    assert record["evidence_status"] == "unsigned"
    assert record["approved_at"].endswith("Z")


# ------------------------------------------------------------ zone_of


def test_zone_of_resolves_real_paths(roots):
    assert zone_of(roots[Zone.OUTPUT] / "x.json", roots) is Zone.OUTPUT
    assert zone_of(roots[Zone.GROUNDING] / "deep" / "y.json", roots) is Zone.GROUNDING


def test_zone_of_refuses_unknown_paths_rather_than_guessing(roots, tmp_path):
    with pytest.raises(ZoneViolation, match="not inside any known zone"):
        zone_of(tmp_path / "somewhere-else" / "z.json", roots)


def test_zone_of_is_not_fooled_by_traversal(roots):
    """`output/../grounding` is grounding, and must be treated as such."""
    sneaky = roots[Zone.OUTPUT] / ".." / "grounding" / "secret.json"
    assert zone_of(sneaky, roots) is Zone.GROUNDING
