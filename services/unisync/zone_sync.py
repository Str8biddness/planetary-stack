"""Zone-aware push/pull object sync over the lease-bound mTLS transport.

The expansion drive replicates content-addressed objects between the owner's
nodes. Content is immutable and content-addressed, so there are no write
conflicts on content itself — only on which digests a node considers current
(references). Diffing is therefore a set difference of digests, and every move
is idempotent: an object the destination already holds is skipped, never
re-sent.

This module does exactly one dangerous thing — it moves bytes between nodes —
and it must never do it without first asking `services.storage_zones` whether
the move is allowed. The failure this guards against is silent in production:

    a sync loop that simply forgot to call the zone boundary would happily
    push the owner's private GROUNDING corpus onto a public rclone remote, and
    nothing would error. It would just upload.

So the zone gate here is not advisory and not centralised in one easily-skipped
place. `_gate_zone()` runs as the FIRST statement of every transfer, before any
store is opened or any byte is read, and it raises `ZoneViolation` — the same
type `storage_zones` raises — rather than returning a status a caller might
ignore. A refused move touches nothing.

Authority is still not ours to grant. Bytes move only through an injected
`ObjectTransport` bound to a control-plane `TransferContext` (lease id, fencing
token, signed request). This module never mints a lease and never promotes
content into grounding; promotion remains `storage_zones.promote_to_grounding`
with an owner approval, and there is deliberately no path from here into it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from services.storage_zones import Transport, Zone, ZoneViolation, require_transport

from .contracts import (
    INTERNET_RELAY_TRANSPORT,
    LAN_MTLS_TRANSPORT,
    LOCAL_PROCESS_TRANSPORT,
    BackpressureController,
    CancellationToken,
    Deadline,
    ObjectTransport,
    ProgressCallback,
    TransferContext,
    TransferResult,
)
from .errors import CancellationError
from .storage import ContentAddressedStore

# The unisync object transports are all mesh-class: lease-bound mTLS between the
# owner's own nodes (in-process locally, LAN or relayed over the internet). None
# of them leaves the home. Public egress (git/rclone) is the drive's path with
# its own gate and is intentionally not reachable from an object sync.
MESH_TRANSPORT_IDS = frozenset(
    {LOCAL_PROCESS_TRANSPORT, LAN_MTLS_TRANSPORT, INTERNET_RELAY_TRANSPORT}
)

# A reference manifest: per zone, the digests a node holds and their sizes.
# References are the only thing that can conflict; content cannot.
ZoneInventory = dict[Zone, dict[str, int]]


@dataclass(frozen=True, slots=True)
class SyncItem:
    """One content-addressed object, tagged with the zone it belongs to."""

    zone: Zone
    digest: str
    byte_length: int


@dataclass(frozen=True, slots=True)
class SyncPlan:
    """What a diff decided, before any byte moved."""

    push: tuple[SyncItem, ...]
    pull: tuple[SyncItem, ...]
    already_present: tuple[SyncItem, ...]
    withheld: tuple[tuple[SyncItem, str], ...]


@dataclass(frozen=True, slots=True)
class SyncReport:
    """What actually happened. Skips are idempotent no-ops, not failures."""

    transferred: tuple[TransferResult, ...]
    skipped_present: tuple[SyncItem, ...]
    bytes_moved: int


def reconcile_references(a: ZoneInventory, b: ZoneInventory) -> ZoneInventory:
    """Merge two reference manifests.

    Content is immutable and content-addressed, so a digest present on either
    side is the same bytes on both. The reconciled reference set is therefore
    the per-zone union, which makes reconciliation commutative and idempotent —
    two nodes that fully push and pull converge on the same manifest regardless
    of order.
    """
    merged: ZoneInventory = {}
    for zone in Zone:
        combined: dict[str, int] = {}
        for source in (a.get(zone, {}), b.get(zone, {})):
            for digest, size in source.items():
                existing = combined.get(digest)
                if existing is not None and existing != size:
                    raise ValueError(
                        f"reference conflict: digest {digest} advertised with two sizes"
                    )
                combined[digest] = size
        if combined:
            merged[zone] = combined
    return merged


class ZoneAwareObjectSync:
    """Push/pull loop that cannot move a byte without the zone boundary agreeing."""

    def __init__(
        self,
        *,
        transport: ObjectTransport,
        transport_class: Transport = Transport.MESH,
        backpressure: BackpressureController | None = None,
    ) -> None:
        if transport_class is Transport.NONE:
            raise ZoneViolation(
                "a transport that never leaves the device cannot move objects between nodes"
            )
        self.transport = transport
        self.transport_class = transport_class
        self.backpressure = backpressure

    # -- the gate ---------------------------------------------------------

    def _gate_zone(self, zone: Zone) -> None:
        """The first thing every transfer does. Refuses, never returns a flag.

        For a mesh sync this refuses NODE (never leaves its device). For a
        public sink this refuses NODE, OUTPUT and GROUNDING — the grounding
        case is the silent upload this whole design exists to prevent.
        """
        require_transport(zone, self.transport_class)

    def _bind_wire_transport(self, context: TransferContext) -> None:
        """The context's selected transport must match this sync's transport class.

        Every valid unisync object transport is mesh-class, so a public sink has
        no object transport at all: external content leaves the home through the
        drive's rclone path, never through here.
        """
        if self.transport_class is Transport.MESH:
            if context.selected_transport not in MESH_TRANSPORT_IDS:
                raise ZoneViolation(
                    f"transfer context selects {context.selected_transport!r}, "
                    "which is not a mesh object transport"
                )
            return
        raise ZoneViolation(
            f"{self.transport_class.value} content sync has no object transport; "
            "external egress goes through the drive's rclone path with its own gate"
        )

    # -- planning ---------------------------------------------------------

    def plan(self, *, local: ZoneInventory, remote: ZoneInventory) -> SyncPlan:
        """Diff two reference manifests by digest.

        Zones whose content may not travel over this transport are withheld —
        NODE on the mesh, and NODE/OUTPUT/GROUNDING toward anything public — so
        they are never even offered, let alone sent.
        """
        push: list[SyncItem] = []
        pull: list[SyncItem] = []
        present: list[SyncItem] = []
        withheld: list[tuple[SyncItem, str]] = []
        for zone in Zone:
            local_z = local.get(zone, {})
            remote_z = remote.get(zone, {})
            try:
                self._gate_zone(zone)
            except ZoneViolation as exc:
                for digest in sorted(set(local_z) | set(remote_z)):
                    size = local_z.get(digest, remote_z.get(digest, -1))
                    withheld.append((SyncItem(zone, digest, size), str(exc)))
                continue
            for digest in sorted(set(local_z) - set(remote_z)):
                push.append(SyncItem(zone, digest, local_z[digest]))
            for digest in sorted(set(remote_z) - set(local_z)):
                pull.append(SyncItem(zone, digest, remote_z[digest]))
            for digest in sorted(set(local_z) & set(remote_z)):
                present.append(SyncItem(zone, digest, local_z[digest]))
        return SyncPlan(
            push=tuple(push),
            pull=tuple(pull),
            already_present=tuple(present),
            withheld=tuple(withheld),
        )

    # -- moving one object ------------------------------------------------

    def transfer_one(
        self,
        item: SyncItem,
        *,
        context: TransferContext,
        source_root: Path,
        destination_root: Path,
        cancellation: CancellationToken | None = None,
        deadline: Deadline | None = None,
        progress: ProgressCallback | None = None,
    ) -> TransferResult | None:
        """Move one object after the zone boundary agrees. Returns None if the
        destination already holds it (idempotent skip). A refused move opens no
        store and reads no byte."""
        # 1. Zone boundary FIRST — before any filesystem access. Raises.
        self._gate_zone(item.zone)
        # 2. The wire transport must match the zone's permitted transport class.
        self._bind_wire_transport(context)
        # 3. The context must describe exactly this object; a sync never moves
        #    bytes under a lease minted for something else.
        if context.object_sha256 != item.digest:
            raise ValueError("transfer context object digest does not match the sync item")
        if context.byte_length != item.byte_length:
            raise ValueError("transfer context byte length does not match the sync item")
        # 4. Idempotency: content is immutable, so an object already present is
        #    the same bytes. Skip it; do not re-send.
        if ContentAddressedStore(destination_root).has(item.digest):
            return None
        # 5. Backpressure so a fast node cannot flood a slow one.
        if self.backpressure is not None:
            self.backpressure.acquire(item.byte_length)
        try:
            return self.transport.upload_object(
                context=context,
                source_root=source_root,
                destination_root=destination_root,
                cancellation=cancellation,
                deadline=deadline,
                progress=progress,
            )
        finally:
            if self.backpressure is not None:
                self.backpressure.release(item.byte_length)

    # -- the loops --------------------------------------------------------

    def _run(
        self,
        items: tuple[SyncItem, ...],
        *,
        context_for,
        roots_for,
        cancellation: CancellationToken | None = None,
        deadline: Deadline | None = None,
        progress: ProgressCallback | None = None,
    ) -> SyncReport:
        transferred: list[TransferResult] = []
        skipped: list[SyncItem] = []
        moved = 0
        token = cancellation or CancellationToken()
        for item in items:
            token.raise_if_cancelled()
            source_root, destination_root = roots_for(item)
            result = self.transfer_one(
                item,
                context=context_for(item),
                source_root=source_root,
                destination_root=destination_root,
                cancellation=token,
                deadline=deadline,
                progress=progress,
            )
            if result is None:
                skipped.append(item)
            else:
                transferred.append(result)
                moved += result.bytes_transferred
        return SyncReport(
            transferred=tuple(transferred),
            skipped_present=tuple(skipped),
            bytes_moved=moved,
        )

    def run_push(
        self,
        items: tuple[SyncItem, ...],
        *,
        context_for,
        local_roots: dict[Zone, Path],
        remote_roots: dict[Zone, Path],
        cancellation: CancellationToken | None = None,
        deadline: Deadline | None = None,
        progress: ProgressCallback | None = None,
    ) -> SyncReport:
        """Offer local objects to the peer. Local is the source."""
        return self._run(
            items,
            context_for=context_for,
            roots_for=lambda item: (local_roots[item.zone], remote_roots[item.zone]),
            cancellation=cancellation,
            deadline=deadline,
            progress=progress,
        )

    def run_pull(
        self,
        items: tuple[SyncItem, ...],
        *,
        context_for,
        local_roots: dict[Zone, Path],
        remote_roots: dict[Zone, Path],
        cancellation: CancellationToken | None = None,
        deadline: Deadline | None = None,
        progress: ProgressCallback | None = None,
    ) -> SyncReport:
        """Fetch peer objects into the local node. The peer is the source."""
        return self._run(
            items,
            context_for=context_for,
            roots_for=lambda item: (remote_roots[item.zone], local_roots[item.zone]),
            cancellation=cancellation,
            deadline=deadline,
            progress=progress,
        )


__all__ = [
    "MESH_TRANSPORT_IDS",
    "SyncItem",
    "SyncPlan",
    "SyncReport",
    "ZoneAwareObjectSync",
    "ZoneInventory",
    "reconcile_references",
]
