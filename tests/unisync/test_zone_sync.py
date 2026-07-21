"""Zone-aware expansion-drive sync.

Following the house style, most of these are refusals. The sync loop's job is to
move content-addressed objects between the owner's nodes fast; the whole reason
it is allowed to exist is that it cannot move a byte the zone boundary forbids.
The test that matters most is the one that proves grounding never reaches a
public transport, and that a refused move touches nothing.
"""

from __future__ import annotations

import hashlib

import pytest

from services.storage_zones import (
    PERMITTED_MOVES,
    Transport,
    Zone,
    ZoneViolation,
    promote_to_grounding,
    PromotionLedger,
)
from services.unisync import (
    AuthorizationError,
    BackpressureController,
    BackpressureError,
    CancellationToken,
    ContentAddressedStore,
    InProcessObjectTransport,
)
from services.unisync.zone_sync import (
    MESH_TRANSPORT_IDS,
    SyncItem,
    ZoneAwareObjectSync,
    reconcile_references,
)

from .conftest import StrictValidator, make_context


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _item(zone: Zone, payload: bytes) -> SyncItem:
    return SyncItem(zone=zone, digest=_digest(payload), byte_length=len(payload))


def _context_for(payload: bytes):
    def factory(item: SyncItem):
        return make_context(payload)

    return factory


def _mesh_sync(**kwargs) -> ZoneAwareObjectSync:
    transport = InProcessObjectTransport(validator=StrictValidator(), chunk_size=64)
    return ZoneAwareObjectSync(transport=transport, transport_class=Transport.MESH, **kwargs)


# ---------------------------------------------------- the refusal that matters


def test_sync_refuses_to_push_grounding_over_a_public_transport(tmp_path, payload):
    """The silent-upload failure this whole design exists to prevent.

    A sync loop that forgot the zone boundary would push the owner's private
    grounding corpus to a cloud remote and never error. Here it must raise, and
    it must not have written a single byte to the destination.
    """
    source = ContentAddressedStore(tmp_path / "grounding")
    source.put_bytes(payload)
    destination_root = tmp_path / "public-remote"
    transport = InProcessObjectTransport(validator=StrictValidator(), chunk_size=64)
    sync = ZoneAwareObjectSync(transport=transport, transport_class=Transport.PUBLIC)

    with pytest.raises(ZoneViolation, match="never travel over a public transport"):
        sync.transfer_one(
            _item(Zone.GROUNDING, payload),
            context=make_context(payload),
            source_root=source.root,
            destination_root=destination_root,
        )
    assert not (destination_root / "objects").exists() or not ContentAddressedStore(
        destination_root
    ).has(_digest(payload))


def test_sync_refuses_output_over_a_public_transport(tmp_path, payload):
    source = ContentAddressedStore(tmp_path / "output")
    source.put_bytes(payload)
    sync = ZoneAwareObjectSync(
        transport=InProcessObjectTransport(validator=StrictValidator()),
        transport_class=Transport.PUBLIC,
    )
    with pytest.raises(ZoneViolation, match="never travel over a public transport"):
        sync.transfer_one(
            _item(Zone.OUTPUT, payload),
            context=make_context(payload),
            source_root=source.root,
            destination_root=tmp_path / "remote",
        )


def test_external_still_has_no_object_transport_off_home(tmp_path, payload):
    """EXTERNAL may leave the home, but only through the drive's rclone path.

    require_transport permits EXTERNAL over PUBLIC, so the second gate — binding
    the wire transport — is what refuses an object sync from becoming an egress.
    """
    source = ContentAddressedStore(tmp_path / "external")
    source.put_bytes(payload)
    sync = ZoneAwareObjectSync(
        transport=InProcessObjectTransport(validator=StrictValidator()),
        transport_class=Transport.PUBLIC,
    )
    with pytest.raises(ZoneViolation, match="external egress goes through the drive"):
        sync.transfer_one(
            _item(Zone.EXTERNAL, payload),
            context=make_context(payload),
            source_root=source.root,
            destination_root=tmp_path / "remote",
        )


def test_sync_never_lets_node_state_leave_the_device(tmp_path, payload):
    source = ContentAddressedStore(tmp_path / "node")
    source.put_bytes(payload)
    destination_root = tmp_path / "peer"
    sync = _mesh_sync()
    with pytest.raises(ZoneViolation, match="never leaves its device"):
        sync.transfer_one(
            _item(Zone.NODE, payload),
            context=make_context(payload),
            source_root=source.root,
            destination_root=destination_root,
        )
    assert not (destination_root / "objects").exists() or not ContentAddressedStore(
        destination_root
    ).has(_digest(payload))


def test_a_transport_that_never_leaves_the_device_cannot_be_a_sync():
    with pytest.raises(ZoneViolation, match="cannot move objects between nodes"):
        ZoneAwareObjectSync(
            transport=InProcessObjectTransport(validator=StrictValidator()),
            transport_class=Transport.NONE,
        )


# ---------------------------------------------------------- the happy paths


def test_output_moves_over_the_mesh_and_the_move_is_idempotent(tmp_path, payload):
    local = ContentAddressedStore(tmp_path / "local")
    digest = local.put_bytes(payload)
    remote_root = tmp_path / "remote"
    sync = _mesh_sync()
    item = _item(Zone.OUTPUT, payload)

    first = sync.transfer_one(
        item, context=make_context(payload), source_root=local.root, destination_root=remote_root
    )
    assert first is not None
    assert ContentAddressedStore(remote_root).read_bytes(digest) == payload

    # Content is immutable and content-addressed: a second push is a no-op.
    second = sync.transfer_one(
        item, context=make_context(payload), source_root=local.root, destination_root=remote_root
    )
    assert second is None


def test_grounding_replicates_between_the_owners_nodes_over_the_mesh(tmp_path, payload):
    """Grounding is mesh-only, not never-sync: the owner's own nodes may hold a
    copy. The boundary forbids public, not mesh."""
    local = ContentAddressedStore(tmp_path / "local")
    digest = local.put_bytes(payload)
    remote_root = tmp_path / "remote"
    sync = _mesh_sync()
    result = sync.transfer_one(
        _item(Zone.GROUNDING, payload),
        context=make_context(payload),
        source_root=local.root,
        destination_root=remote_root,
    )
    assert result is not None
    assert ContentAddressedStore(remote_root).read_bytes(digest) == payload


def test_run_push_moves_offered_objects_and_reports_bytes(tmp_path, payload):
    local = ContentAddressedStore(tmp_path / "local")
    local.put_bytes(payload)
    remote_root = tmp_path / "remote"
    ContentAddressedStore(remote_root)
    sync = _mesh_sync()
    item = _item(Zone.OUTPUT, payload)

    report = sync.run_push(
        (item,),
        context_for=_context_for(payload),
        local_roots={Zone.OUTPUT: local.root},
        remote_roots={Zone.OUTPUT: remote_root},
    )
    assert report.bytes_moved == len(payload)
    assert len(report.transferred) == 1
    assert not report.skipped_present

    again = sync.run_push(
        (item,),
        context_for=_context_for(payload),
        local_roots={Zone.OUTPUT: local.root},
        remote_roots={Zone.OUTPUT: remote_root},
    )
    assert again.bytes_moved == 0
    assert again.skipped_present == (item,)


def test_run_pull_fetches_from_the_peer(tmp_path, payload):
    remote = ContentAddressedStore(tmp_path / "remote")
    remote.put_bytes(payload)
    local_root = tmp_path / "local"
    ContentAddressedStore(local_root)
    sync = _mesh_sync()
    report = sync.run_pull(
        (_item(Zone.OUTPUT, payload),),
        context_for=_context_for(payload),
        local_roots={Zone.OUTPUT: local_root},
        remote_roots={Zone.OUTPUT: remote.root},
    )
    assert report.bytes_moved == len(payload)
    assert ContentAddressedStore(local_root).read_bytes(_digest(payload)) == payload


# -------------------------------------------------------------- planning


def test_plan_diffs_by_digest_and_withholds_node_zone():
    local = {
        Zone.OUTPUT: {"a" * 64: 10},
        Zone.NODE: {"c" * 64: 4},
    }
    remote = {
        Zone.OUTPUT: {"b" * 64: 20},
        Zone.GROUNDING: {"d" * 64: 8},
    }
    plan = ZoneAwareObjectSync(
        transport=InProcessObjectTransport(validator=StrictValidator()),
        transport_class=Transport.MESH,
    ).plan(local=local, remote=remote)

    assert plan.push == (SyncItem(Zone.OUTPUT, "a" * 64, 10),)
    # OUTPUT pull and GROUNDING pull are both mesh-permitted.
    assert SyncItem(Zone.OUTPUT, "b" * 64, 20) in plan.pull
    assert SyncItem(Zone.GROUNDING, "d" * 64, 8) in plan.pull
    # NODE never syncs: it is withheld, not offered.
    withheld_zones = {item.zone for item, _ in plan.withheld}
    assert withheld_zones == {Zone.NODE}
    assert all(item.zone is not Zone.NODE for item in plan.push + plan.pull)


def test_plan_toward_public_withholds_everything_but_external():
    inv = {
        Zone.OUTPUT: {"a" * 64: 1},
        Zone.GROUNDING: {"b" * 64: 1},
        Zone.NODE: {"c" * 64: 1},
        Zone.EXTERNAL: {"d" * 64: 1},
    }
    plan = ZoneAwareObjectSync(
        transport=InProcessObjectTransport(validator=StrictValidator()),
        transport_class=Transport.PUBLIC,
    ).plan(local=inv, remote={})
    withheld_zones = {item.zone for item, _ in plan.withheld}
    assert withheld_zones == {Zone.OUTPUT, Zone.GROUNDING, Zone.NODE}
    # EXTERNAL is the only zone a public plan may even consider offering.
    assert {item.zone for item in plan.push} == {Zone.EXTERNAL}


# ------------------------------------------------------------- backpressure


def test_backpressure_refuses_an_object_over_budget_and_moves_nothing(tmp_path, payload):
    local = ContentAddressedStore(tmp_path / "local")
    local.put_bytes(payload)
    remote_root = tmp_path / "remote"
    sync = _mesh_sync(backpressure=BackpressureController(max_inflight_bytes=8))
    with pytest.raises(BackpressureError, match="in-flight byte budget"):
        sync.transfer_one(
            _item(Zone.OUTPUT, payload),
            context=make_context(payload),
            source_root=local.root,
            destination_root=remote_root,
        )
    assert not ContentAddressedStore(remote_root).has(_digest(payload))


# ------------------------------------------------ authority is still injected


def test_sync_cannot_bypass_the_injected_lease_validator(tmp_path, payload):
    local = ContentAddressedStore(tmp_path / "local")
    local.put_bytes(payload)
    sync = ZoneAwareObjectSync(
        transport=InProcessObjectTransport(validator=None),
        transport_class=Transport.MESH,
    )
    with pytest.raises(AuthorizationError, match="requires an injected"):
        sync.transfer_one(
            _item(Zone.OUTPUT, payload),
            context=make_context(payload),
            source_root=local.root,
            destination_root=tmp_path / "remote",
        )


def test_context_must_describe_the_object_being_synced(tmp_path, payload):
    local = ContentAddressedStore(tmp_path / "local")
    local.put_bytes(payload)
    sync = _mesh_sync()
    wrong = SyncItem(Zone.OUTPUT, "e" * 64, len(payload))
    with pytest.raises(ValueError, match="object digest does not match"):
        sync.transfer_one(
            wrong,
            context=make_context(payload),
            source_root=local.root,
            destination_root=tmp_path / "remote",
        )


def test_cancellation_stops_the_loop_before_the_next_object(tmp_path, payload):
    local = ContentAddressedStore(tmp_path / "local")
    local.put_bytes(payload)
    token = CancellationToken()
    token.cancel()
    sync = _mesh_sync()
    with pytest.raises(Exception, match="cancelled"):
        sync.run_push(
            (_item(Zone.OUTPUT, payload),),
            context_for=_context_for(payload),
            local_roots={Zone.OUTPUT: local.root},
            remote_roots={Zone.OUTPUT: tmp_path / "remote"},
            cancellation=token,
        )


# ------------------------------------------- the sync must not self-promote


def test_sync_offers_no_path_into_grounding_promotion():
    """Replication keeps a zone; it never turns output into belief. There is no
    promote method here, and the only promotion gate still refuses automation."""
    assert not [name for name in dir(ZoneAwareObjectSync) if "promote" in name.lower()]
    assert (Zone.GROUNDING, Zone.EXTERNAL) not in PERMITTED_MOVES


def test_automated_promotion_is_still_refused(tmp_path):
    ledger = PromotionLedger(tmp_path / "promotions.jsonl")
    with pytest.raises(ZoneViolation, match="automated promotion is refused"):
        promote_to_grounding(digest="a" * 64, ledger=ledger, approved_by=None, reason="auto")
    assert ledger.was_approved("a" * 64) is False


# ------------------------------------------------------ reference reconcile


def test_reference_reconciliation_is_commutative_and_idempotent():
    a = {Zone.OUTPUT: {"a" * 64: 1}, Zone.GROUNDING: {"b" * 64: 2}}
    b = {Zone.OUTPUT: {"c" * 64: 3}}
    merged = reconcile_references(a, b)
    assert merged == reconcile_references(b, a)
    assert merged == reconcile_references(merged, merged)
    assert merged[Zone.OUTPUT] == {"a" * 64: 1, "c" * 64: 3}


def test_reference_reconciliation_rejects_a_size_conflict():
    a = {Zone.OUTPUT: {"a" * 64: 1}}
    b = {Zone.OUTPUT: {"a" * 64: 2}}
    with pytest.raises(ValueError, match="reference conflict"):
        reconcile_references(a, b)


def test_all_object_transports_are_mesh_class():
    """A regression fence: if a public-egress object transport is ever added to
    this set, the public-refusal path above would silently stop protecting."""
    assert "internet_mtls_relay" in MESH_TRANSPORT_IDS
    assert "lan_mtls" in MESH_TRANSPORT_IDS
    assert "local_process" in MESH_TRANSPORT_IDS
