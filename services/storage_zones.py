"""Storage zones: where content may travel, and what may become believed.

The mesh replicates content faithfully and fast. That is the problem. If a
worker's model is prompt-injected by a poisoned document and writes a poisoned
result, content addressing proves the bytes arrived intact — it says nothing
about whether they are true — and every node then pulls the corruption at full
speed and grounds on it.

Container isolation is not the control at this layer. On a phone inside proot
there is no Podman, and if a worker's only capability is "write output", there
is no shell to sandbox. The control belongs at the ZONE BOUNDARY: what a worker
may write to, what syncs where, and what requires the owner before it becomes
part of what the system believes.

Three zones, three different transports, and one gate:

    NODE      per-node state. Never syncs. Never leaves the device.
    OUTPUT    what workers produce. Syncs freely across the mesh over
              lease-bound mTLS. Circulating here means "available", not
              "believed".
    GROUNDING what the assistant treats as true. Mesh transport only, and
              nothing enters WITHOUT THE OWNER'S APPROVAL.
    EXTERNAL  code and published material. Leaves the home by design
              (git remotes, rclone). Personal content must never land here.

The gate between OUTPUT and GROUNDING is the important one, and it is the
owner's own design: content circulates freely, but nothing becomes believed
without a human saying so. That maps exactly onto the fluid/crystallized split
the consciousness model already uses — fluid is what the mesh moves,
crystallized is what the owner approved.

HONEST SCOPE. This module enforces WHERE content may go. It does not judge
whether content is true, and it cannot detect a poisoned document. What it
guarantees is that a poisoned document cannot become grounding on its own, and
that personal content cannot be routed to an external transport by code alone.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

PROMOTION_SCHEMA = "planetary.synthesus.zone_promotion.v1"
MAX_LEDGER_BYTES = 8 * 1024 * 1024
MAX_REASON_CHARS = 500


class Zone(StrEnum):
    NODE = "node"
    OUTPUT = "output"
    GROUNDING = "grounding"
    EXTERNAL = "external"


class Transport(StrEnum):
    NONE = "none"          # never leaves the device
    MESH = "mesh"          # lease-bound mTLS between the owner's nodes
    PUBLIC = "public"      # git remotes, rclone — leaves the home


class ZoneViolation(PermissionError):
    """A move was refused because it crosses a zone boundary."""


@dataclass(frozen=True)
class ZoneRules:
    """What a zone permits. Deliberately data, so the policy is readable."""

    transport: Transport
    worker_may_write: bool
    leaves_home: bool


# The policy, in one place. Changing any line here changes a security property,
# so each is asserted by test.
ZONE_RULES: dict[Zone, ZoneRules] = {
    Zone.NODE: ZoneRules(
        transport=Transport.NONE, worker_may_write=True, leaves_home=False
    ),
    Zone.OUTPUT: ZoneRules(
        transport=Transport.MESH, worker_may_write=True, leaves_home=False
    ),
    # A worker cannot write here. Only a promotion can, and only with approval.
    Zone.GROUNDING: ZoneRules(
        transport=Transport.MESH, worker_may_write=False, leaves_home=False
    ),
    Zone.EXTERNAL: ZoneRules(
        transport=Transport.PUBLIC, worker_may_write=False, leaves_home=True
    ),
}

# Moves the system will perform. Anything not listed is refused — an allowlist,
# because the dangerous direction is the one nobody thought of.
PERMITTED_MOVES: frozenset[tuple[Zone, Zone]] = frozenset({
    (Zone.OUTPUT, Zone.GROUNDING),   # requires approval; see promote()
    (Zone.OUTPUT, Zone.EXTERNAL),    # publishing a result the owner chose
    (Zone.NODE, Zone.OUTPUT),        # a node offering its work to the mesh
})


def zone_of(path: Path | str, roots: dict[Zone, Path]) -> Zone:
    """Which zone a path belongs to. Unrecognised paths raise rather than guess."""
    target = Path(path).resolve()
    for zone, root in roots.items():
        try:
            target.relative_to(Path(root).resolve())
        except ValueError:
            continue
        return zone
    raise ZoneViolation(f"path is not inside any known zone: {target}")


def require_transport(zone: Zone, transport: Transport) -> None:
    """Fail closed unless this zone may travel over this transport.

    The case that matters: grounding content over a PUBLIC transport. That is
    personal data leaving the home, and it is exactly the failure that would be
    silent — a misrouted sync does not error, it just uploads.
    """
    rules = ZONE_RULES[zone]
    if transport is Transport.PUBLIC and not rules.leaves_home:
        raise ZoneViolation(
            f"{zone.value} content must never travel over a public transport"
        )
    if transport is Transport.MESH and rules.transport is Transport.NONE:
        raise ZoneViolation(f"{zone.value} content never leaves its device")
    if transport is Transport.NONE:
        return
    if rules.transport is Transport.PUBLIC and transport is Transport.MESH:
        return  # external content may also move internally; harmless direction
    if rules.transport is not transport and not (
        rules.transport is Transport.MESH and transport is Transport.MESH
    ):
        raise ZoneViolation(
            f"{zone.value} content may not travel over {transport.value}"
        )


def require_worker_may_write(zone: Zone) -> None:
    """Workers write to output, never straight into what the system believes."""
    if not ZONE_RULES[zone].worker_may_write:
        raise ZoneViolation(
            f"a worker may not write to the {zone.value} zone; "
            "write to output and let the owner promote it"
        )


def require_move_permitted(source: Zone, destination: Zone) -> None:
    if source == destination:
        return
    if (source, destination) not in PERMITTED_MOVES:
        raise ZoneViolation(
            f"moving content from {source.value} to {destination.value} is not permitted"
        )


class PromotionLedger:
    """Durable record of what the owner approved into grounding.

    Append-only and owner-only. Grounding content that is not in this ledger
    was never approved, which is the question worth being able to answer after
    something goes wrong.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)

    def _entries(self) -> list[dict[str, Any]]:
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return []
        if not stat.S_ISREG(info.st_mode):
            raise ZoneViolation("promotion ledger is not a regular file")
        if info.st_size > MAX_LEDGER_BYTES:
            raise ZoneViolation("promotion ledger exceeds its size bound")
        entries = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
        return entries

    def record(
        self,
        *,
        digest: str,
        approved_by: str,
        reason: str,
        produced_by_node: str | None,
        evidence_status: str | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not isinstance(digest, str) or len(digest) != 64:
            raise ZoneViolation("digest must be a sha256 hex digest")
        if not isinstance(approved_by, str) or not approved_by.strip():
            raise ZoneViolation("an approval must name who approved it")
        if not isinstance(reason, str) or len(reason) > MAX_REASON_CHARS:
            raise ZoneViolation("reason is required and bounded")
        entry = {
            "schema": PROMOTION_SCHEMA,
            "digest": digest,
            "approved_by": approved_by.strip(),
            "reason": reason,
            "produced_by_node": produced_by_node,
            "evidence_status": evidence_status,
            "approved_at": (now or datetime.now(UTC))
            .astimezone(UTC)
            .replace(microsecond=0)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        fd = os.open(
            self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return entry

    def was_approved(self, digest: str) -> bool:
        return any(entry.get("digest") == digest for entry in self._entries())

    def approvals(self) -> list[dict[str, Any]]:
        return self._entries()


def promote_to_grounding(
    *,
    digest: str,
    ledger: PromotionLedger,
    approved_by: str | None,
    reason: str,
    produced_by_node: str | None = None,
    evidence_status: str | None = None,
) -> dict[str, Any]:
    """The gate. Content becomes grounding only when the owner says so.

    `approved_by` being None is the automated path, and it is refused. There is
    deliberately no flag to bypass this: a system that can promote its own
    output into its own beliefs will eventually believe something a poisoned
    document told it to.
    """

    if approved_by is None:
        raise ZoneViolation(
            "grounding requires the owner's approval; automated promotion is refused"
        )
    require_move_permitted(Zone.OUTPUT, Zone.GROUNDING)
    return ledger.record(
        digest=digest,
        approved_by=approved_by,
        reason=reason,
        produced_by_node=produced_by_node,
        evidence_status=evidence_status,
    )
